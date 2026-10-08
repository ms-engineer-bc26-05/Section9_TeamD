"""内部ユーザー検索のテスト。実DBには接続しない。"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.features.users.models import User
from app.features.users.service import (
    get_or_create_user,
    get_user_by_firebase_uid,
)
from sqlalchemy import select

from sqlalchemy.dialects import postgresql


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
