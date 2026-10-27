"""利用中のプランの判定（get_current_plan。#92）と利用権限の付与（grant_paid_entitlement。#95）のテスト。
実DBには接続しない。

F-05（決済）のトランザクションが、同じセッションでこれらの関数を呼ぶことも確認する（#95）。
実DBでの確認は test_db_current_plan.py（RUN_DB_TESTS=1 のときだけ実行）。
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.features.payments.db_repository import _SqlAlchemyPaymentTransaction
from app.features.plans.public import PlanCode, get_current_plan, grant_paid_entitlement

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def mock_session(value):
    result = Mock()
    result.scalar_one.return_value = value
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.parametrize(("paid", "expected"), [(True, PlanCode.PREMIUM), (False, PlanCode.FREE)])
async def test_returns_plan_code(paid, expected):
    session = mock_session(paid)

    assert await get_current_plan(session, uuid4(), NOW) is expected

    session.execute.assert_awaited_once()
    # 状態の取得だけを行い、セッションの終了・commitは呼び出し元に任せる
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.close.assert_not_called()


async def test_payment_transaction_uses_get_current_plan_with_same_session():
    # 決済（購入の判定・GET /payments/me）も GET /usage と同じ判定を、
    # ユーザー行のロックと同じトランザクション（セッション）で行う
    user_id = uuid4()
    plans_session = mock_session(True)
    payments_session = mock_session(True)

    expected = await get_current_plan(plans_session, user_id, NOW)
    actual = await _SqlAlchemyPaymentTransaction(payments_session).current_plan(user_id, NOW)

    assert actual is expected is PlanCode.PREMIUM
    dialect = postgresql.dialect()
    ours = plans_session.execute.await_args.args[0].compile(dialect=dialect)
    theirs = payments_session.execute.await_args.args[0].compile(dialect=dialect)
    assert str(ours) == str(theirs)
    assert ours.params == theirs.params
    # 読むだけなので、行をロックしない
    assert "FOR UPDATE" not in str(ours)


async def test_grant_paid_entitlement_upserts_one_row():
    session = mock_session(None)
    user_id, plan_id = uuid4(), uuid4()

    await grant_paid_entitlement(session, user_id, plan_id, NOW)

    statement = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(statement)
    assert "INSERT INTO user_entitlements" in sql
    assert "ON CONFLICT (user_id) DO UPDATE" in sql
    # 買い切りのため期限なし（#59）
    assert statement.params["status"] == "active"
    assert statement.params["valid_from"] == NOW
    assert statement.params["valid_until"] is None
    # commit・ロックは呼び出し元のトランザクションで行う
    session.commit.assert_not_called()


async def test_payment_transaction_grants_with_same_session():
    session = mock_session(None)

    await _SqlAlchemyPaymentTransaction(session).grant_entitlement(uuid4(), uuid4(), NOW)

    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "INSERT INTO user_entitlements" in sql
