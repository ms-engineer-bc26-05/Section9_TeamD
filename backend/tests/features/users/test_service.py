"""内部ユーザー検索のテスト。実DBには接続しない。"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.features.users.models import User
from app.features.users.service import get_user_by_firebase_uid
from sqlalchemy import select


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
