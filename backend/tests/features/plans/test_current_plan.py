"""利用中のプランの判定（get_current_plan。#92）のテスト。実DBには接続しない。

「有料」の条件が F-05 の has_paid_entitlement と同じであることを、発行するSQLの比較で確認する。
実DBでの確認は test_db_current_plan.py（RUN_DB_TESTS=1 のときだけ実行）。
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.features.payments.db_repository import _SqlAlchemyPaymentTransaction
from app.features.plans.public import PlanCode, get_current_plan

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


async def test_same_condition_as_has_paid_entitlement():
    # #95で F-05 側を差し替えるまで、2か所の「有料」の条件を同じに保つ
    user_id = uuid4()
    plans_session = mock_session(False)
    payments_session = mock_session(False)

    await get_current_plan(plans_session, user_id, NOW)
    await _SqlAlchemyPaymentTransaction(payments_session).has_paid_entitlement(user_id, NOW)

    dialect = postgresql.dialect()
    ours = plans_session.execute.await_args.args[0].compile(dialect=dialect)
    theirs = payments_session.execute.await_args.args[0].compile(dialect=dialect)
    assert str(ours) == str(theirs)
    assert ours.params == theirs.params
    # 読むだけなので、行をロックしない
    assert "FOR UPDATE" not in str(ours)
