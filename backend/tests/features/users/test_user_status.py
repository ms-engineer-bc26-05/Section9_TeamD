"""内部ユーザーの状態の取得（get_user_status。#92）のテスト。実DBには接続しない。"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.features.users.models import User
from app.features.users.service import get_user_status


@pytest.mark.parametrize("status", ["active", "deleting", None])
async def test_get_user_status_returns_status(status):
    result = Mock()
    result.scalar_one_or_none.return_value = status
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    received = await get_user_status(session, uuid4())

    # None（ユーザーがいない）も、そのまま返す（呼び出し元でエラーと区別する）
    assert received == status
    session.execute.assert_awaited_once()
    result.scalar_one_or_none.assert_called_once_with()
    # 状態の取得だけを行い、セッションの終了・commitは呼び出し元に任せる
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


async def test_get_user_status_reads_status_by_user_id_without_lock():
    user_id = uuid4()
    result = Mock()
    result.scalar_one_or_none.return_value = "active"
    session = Mock()
    session.execute = AsyncMock(return_value=result)

    await get_user_status(session, user_id)

    statement = session.execute.await_args.args[0]
    expected = select(User.status).where(User.id == user_id)
    dialect = postgresql.dialect()
    actual_sql = statement.compile(dialect=dialect)
    expected_sql = expected.compile(dialect=dialect)

    assert str(actual_sql) == str(expected_sql)
    assert actual_sql.params == expected_sql.params
    # 読むだけなので、行をロックしない
    assert "FOR UPDATE" not in str(actual_sql)
