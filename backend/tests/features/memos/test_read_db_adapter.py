"""SQL contract and transaction-failure tests without a database connection."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.exceptions import DatabaseUnavailableError
from app.features.memos.exceptions import MemoDatabaseError
from app.features.memos.read_cursor import MemoCursor
from app.features.memos.read_db_repository import SqlAlchemyMemoReadRepository
from app.features.memos.repository import UserNotActive, UserNotFound

USER, MEMO = UUID(int=1), UUID(int=2)


class Session:
    def __init__(self):
        self.execute = AsyncMock()
        self.committed = False
        self.rolled_back = False
        self.commit_error = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    @asynccontextmanager
    async def begin(self):
        try:
            yield self
            if self.commit_error:
                raise self.commit_error
            self.committed = True
        except BaseException:
            self.rolled_back = True
            raise


def result(value):
    output = MagicMock()
    output.scalar_one_or_none.return_value = value
    return output


def compiled(statement):
    output = statement.compile(dialect=postgresql.dialect())
    return str(output), output.params


async def test_detail_query_always_scopes_both_ids():
    session = Session()
    session.execute.return_value = result(None)
    repo = SqlAlchemyMemoReadRepository(lambda: session)
    assert await repo.find_owned(USER, MEMO) is None
    sql, params = compiled(session.execute.call_args.args[0])
    assert "approved_memos.user_id =" in sql
    assert "approved_memos.id =" in sql
    assert USER in params.values() and MEMO in params.values()


@pytest.mark.parametrize("with_cursor", [False, True])
async def test_list_query_has_owner_stable_order_and_bounded_limit(with_cursor):
    session = Session()
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = SqlAlchemyMemoReadRepository(lambda: session)
    cursor = MemoCursor(created_at=datetime(2026, 10, 13, tzinfo=UTC), memo_id=MEMO) if with_cursor else None
    assert await repo.list_owned(USER, cursor, 11) == []
    sql, params = compiled(session.execute.call_args.args[0])
    assert "approved_memos.user_id =" in sql
    assert "ORDER BY approved_memos.created_at DESC, approved_memos.id DESC" in sql
    assert "LIMIT" in sql and 11 in params.values()
    if with_cursor:
        assert "(approved_memos.created_at, approved_memos.id) <" in sql
        assert cursor.created_at in params.values() and MEMO in params.values()


@pytest.mark.parametrize("deleted", [None, MEMO])
async def test_delete_locks_user_scopes_owner_and_commits_before_return(deleted):
    session = Session()
    session.execute.side_effect = [result("active"), result(deleted)]
    repo = SqlAlchemyMemoReadRepository(lambda: session)
    assert await repo.delete_owned(USER, MEMO) is (deleted is not None)
    assert session.committed
    calls = session.execute.call_args_list
    sql, params = compiled(calls[0].args[0])
    assert "FOR UPDATE" in sql and USER in params.values()
    sql, params = compiled(calls[1].args[0])
    assert "DELETE FROM approved_memos" in sql
    assert "approved_memos.user_id =" in sql and "approved_memos.id =" in sql
    assert "RETURNING" in sql


@pytest.mark.parametrize("status,error", [(None, UserNotFound), ("deleting", UserNotActive)])
async def test_changed_user_rolls_back_before_delete(status, error):
    session = Session()
    session.execute.return_value = result(status)
    repo = SqlAlchemyMemoReadRepository(lambda: session)
    with pytest.raises(error):
        await repo.delete_owned(USER, MEMO)
    assert session.rolled_back and not session.committed
    assert session.execute.await_count == 1


async def test_commit_failure_is_sanitized_and_not_reported_as_success():
    session = Session()
    session.execute.side_effect = [result("active"), result(MEMO)]
    session.commit_error = IntegrityError("synthetic SQL", {"secret": "synthetic"}, Exception("hidden"))
    repo = SqlAlchemyMemoReadRepository(lambda: session)
    with pytest.raises(MemoDatabaseError) as caught:
        await repo.delete_owned(USER, MEMO)
    assert session.rolled_back and not session.committed
    assert caught.value.__suppress_context__
    assert "hidden" not in str(caught.value)


@pytest.mark.parametrize("operation", ["list", "detail", "delete"])
@pytest.mark.parametrize("connection", [True, False])
async def test_database_error_classification(operation, connection):
    session = Session()
    original = ConnectionError("synthetic-secret") if connection else Exception("synthetic-secret")
    session.execute.side_effect = OperationalError("synthetic SQL", {}, original)
    repo = SqlAlchemyMemoReadRepository(lambda: session)
    expected = DatabaseUnavailableError if connection else MemoDatabaseError
    with pytest.raises(expected) as caught:
        if operation == "list":
            await repo.list_owned(USER, None, 11)
        elif operation == "detail":
            await repo.find_owned(USER, MEMO)
        else:
            await repo.delete_owned(USER, MEMO)
    assert caught.value.__suppress_context__
    assert "synthetic-secret" not in str(caught.value)
