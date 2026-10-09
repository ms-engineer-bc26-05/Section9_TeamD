"""内部ユーザー検索のテスト。実DBには接続しない。"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.features.users.models import User

from sqlalchemy import select

from sqlalchemy.dialects import postgresql

from app.features.users.service import mark_notice_seen

from app.core.exceptions import (
    AccountDeletingError,
    AuthenticationRequiredError,
    DatabaseUnavailableError,
)

from app.features.users.service import (
    get_or_create_user,
    get_user_by_firebase_uid,
    update_user_notice,
)
from sqlalchemy.exc import OperationalError


@pytest.mark.parametrize("found", [True, False])
async def test_get_user_by_firebase_uid(found):
    uid = "dummy-firebase-uid"
    user = User(id=uuid4(), firebase_uid=uid) if found else None

    result = Mock()
    result.scalar_one_or_none.return_value = user
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    received = await get_user_by_firebase_uid(session, uid)

    assert received is user
    session.execute.assert_awaited_once()
    result.scalar_one_or_none.assert_called_once_with()
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.close.assert_not_called()


async def test_search_filters_by_firebase_uid():
    uid = "dummy-firebase-uid"
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await get_user_by_firebase_uid(session, uid)

    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    expected = select(User).where(User.firebase_uid == uid)

    assert statement.compare(expected)


async def test_get_or_create_user_returns_new_user():
    user = User(
        id=uuid4(),
        firebase_uid="dummy-firebase-uid",
        status="active",
        has_seen_notice=False,
    )
    result = Mock()
    result.scalar_one_or_none.return_value = user

    session = Mock()
    session.execute = AsyncMock(return_value=result)

    received, created = await get_or_create_user(
        session,
        "dummy-firebase-uid",
    )

    assert received is user
    assert created is True
    session.execute.assert_awaited_once()
    result.scalar_one_or_none.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


@pytest.mark.parametrize("status", ["active", "deleting"])
async def test_get_or_create_user_returns_existing_user(status):
    user = User(
        id=uuid4(),
        firebase_uid="dummy-firebase-uid",
        status=status,
        has_seen_notice=True,
    )

    insert_result = Mock()
    insert_result.scalar_one_or_none.return_value = None

    select_result = Mock()
    select_result.scalar_one_or_none.return_value = user

    session = Mock()
    session.execute = AsyncMock(
        side_effect=[insert_result, select_result]
    )

    received, created = await get_or_create_user(
        session,
        "dummy-firebase-uid",
    )

    assert received is user
    assert created is False
    assert received.status == status
    assert received.has_seen_notice is True
    assert session.execute.await_count == 2
    insert_result.scalar_one_or_none.assert_called_once_with()
    select_result.scalar_one_or_none.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


async def test_get_or_create_user_stops_when_existing_user_disappears():
    insert_result = Mock()
    insert_result.scalar_one_or_none.return_value = None

    select_result = Mock()
    select_result.scalar_one_or_none.return_value = None

    session = Mock()
    session.execute = AsyncMock(
        side_effect=[insert_result, select_result]
    )

    with pytest.raises(
        RuntimeError,
        match="User unavailable after registration conflict",
    ):
        await get_or_create_user(session, "dummy-firebase-uid")

    assert session.execute.await_count == 2
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


async def test_get_or_create_user_uses_conflict_guard_and_locked_lookup():
    uid = "dummy-firebase-uid"
    user = User(id=uuid4(), firebase_uid=uid)

    insert_result = Mock()
    insert_result.scalar_one_or_none.return_value = None
    select_result = Mock()
    select_result.scalar_one_or_none.return_value = user

    session = Mock()
    session.execute = AsyncMock(
        side_effect=[insert_result, select_result]
    )

    await get_or_create_user(session, uid)

    assert session.execute.await_count == 2
    insert_statement = session.execute.await_args_list[0].args[0]
    select_statement = session.execute.await_args_list[1].args[0]

    compiled_insert = insert_statement.compile(
        dialect=postgresql.dialect()
    )
    insert_sql = str(compiled_insert)

    assert "ON CONFLICT (firebase_uid) DO NOTHING" in insert_sql
    assert "RETURNING users.id" in insert_sql
    assert compiled_insert.params["firebase_uid"] == uid

    expected_select = (
        select(User)
        .where(User.firebase_uid == uid)
        .with_for_update()
    )
    compiled_select = select_statement.compile(
        dialect=postgresql.dialect()
    )
    compiled_expected = expected_select.compile(
        dialect=postgresql.dialect()
    )

    assert str(compiled_select) == str(compiled_expected)
    assert compiled_select.params == compiled_expected.params


@pytest.mark.parametrize("has_seen_notice", [False, True])
async def test_mark_notice_seen_updates_active_user(has_seen_notice):
    user_id = uuid4()
    user = User(
        id=user_id,
        firebase_uid="dummy-firebase-uid",
        status="active",
        has_seen_notice=has_seen_notice,
    )

    result = Mock()
    result.scalar_one_or_none.return_value = user
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    received = await mark_notice_seen(session, user_id)

    assert received is user
    assert user.has_seen_notice is True
    session.execute.assert_awaited_once()
    result.scalar_one_or_none.assert_called_once_with()
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.close.assert_not_called()


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (None, AuthenticationRequiredError),
        ("deleting", AccountDeletingError),
        ("unexpected", RuntimeError),
    ],
)
async def test_mark_notice_seen_rejects_unavailable_user(
    status, expected_error
):
    user_id = uuid4()
    user = (
        User(
            id=user_id,
            firebase_uid="dummy-firebase-uid",
            status=status,
            has_seen_notice=False,
        )
        if status is not None
        else None
    )

    result = Mock()
    result.scalar_one_or_none.return_value = user
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    with pytest.raises(expected_error):
        await mark_notice_seen(session, user_id)

    if user is not None:
        assert user.has_seen_notice is False

    session.execute.assert_awaited_once()
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.close.assert_not_called()


async def test_mark_notice_seen_filters_by_user_id_and_locks():
    user_id = uuid4()
    user = User(
        id=user_id,
        firebase_uid="dummy-firebase-uid",
        status="active",
        has_seen_notice=False,
    )
    result = Mock()
    result.scalar_one_or_none.return_value = user
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await mark_notice_seen(session, user_id)

    statement = session.execute.await_args.args[0]
    expected = (
        select(User)
        .where(User.id == user_id)
        .with_for_update()
    )
    dialect = postgresql.dialect()
    actual_sql = statement.compile(dialect=dialect)
    expected_sql = expected.compile(dialect=dialect)

    assert str(actual_sql) == str(expected_sql)
    assert actual_sql.params == expected_sql.params


async def test_update_user_notice_returns_response_after_transaction():
    user_id = uuid4()
    user = User(
        id=user_id,
        firebase_uid="dummy-firebase-uid",
        status="active",
        has_seen_notice=False,
    )
    result = Mock()
    result.scalar_one_or_none.return_value = user

    transaction = AsyncMock()
    transaction.__aexit__.return_value = False
    session = Mock()
    session.begin.return_value = transaction
    session.execute = AsyncMock(return_value=result)

    response = await update_user_notice(session, user_id)

    assert response.user_id == user_id
    assert response.has_seen_notice is True
    session.begin.assert_called_once_with()
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once_with(None, None, None)
    session.execute.assert_awaited_once()
    session.close.assert_not_called()


async def test_update_user_notice_commit_failure_does_not_return_success():
    user_id = uuid4()
    user = User(
        id=user_id,
        firebase_uid="dummy-firebase-uid",
        status="active",
        has_seen_notice=False,
    )
    result = Mock()
    result.scalar_one_or_none.return_value = user

    marker = "DUMMY_DB_ERROR_MARKER"
    error = OperationalError(
        "COMMIT",
        {},
        ConnectionRefusedError(marker),
    )
    transaction = AsyncMock()
    transaction.__aexit__.side_effect = error
    session = Mock()
    session.begin.return_value = transaction
    session.execute = AsyncMock(return_value=result)

    with pytest.raises(DatabaseUnavailableError) as caught:
        await update_user_notice(session, user_id)

    assert str(caught.value) == "Database connection unavailable"
    assert marker not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    session.begin.assert_called_once_with()
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once_with(None, None, None)
    session.execute.assert_awaited_once()
    session.close.assert_not_called()


@pytest.mark.parametrize(
    "error_type",
    [AuthenticationRequiredError, AccountDeletingError, RuntimeError],
)
async def test_update_user_notice_preserves_other_errors(error_type):
    error = error_type("DUMMY_ERROR")
    transaction = AsyncMock()
    transaction.__aexit__.return_value = False
    session = Mock()
    session.begin.return_value = transaction
    session.execute = AsyncMock(side_effect=error)

    with pytest.raises(error_type) as caught:
        await update_user_notice(session, uuid4())

    assert caught.value is error
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()
    exit_args = transaction.__aexit__.await_args.args
    assert exit_args[0] is error_type
    assert exit_args[1] is error
    session.close.assert_not_called()
