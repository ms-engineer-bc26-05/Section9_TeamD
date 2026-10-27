"""利用中のプランの判定（get_current_plan。#92）を実際のPostgreSQLで確認する。

通常のテストでは実行しない。マイグレーションを適用したDBに対して、次のように実行する：
  docker compose run --rm -e RUN_DB_TESTS=1 backend python -m pytest tests/features/plans/test_db_current_plan.py
テストで作ったユーザー・利用権限は、終了時に削除する。テストデータはすべて架空。
"""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import config
from app.core.database import make_database_url
from app.features.payments.db_repository import SqlAlchemyPaymentRepository
from app.features.payments.models import PlanRow, UserEntitlementRow
from app.features.plans.public import PlanCode, get_current_plan
from app.features.users.models import User

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="実DBのテストは RUN_DB_TESTS=1 のときだけ実行する"
)

NOW = datetime.now(UTC)
DAY = timedelta(days=1)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(make_database_url(config.DATABASE_URL), hide_parameters=True)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def user_id(session_factory):
    user_id = uuid4()
    async with session_factory() as session, session.begin():
        await session.execute(insert(User).values(id=user_id, firebase_uid=f"test-{user_id}"))
    yield user_id
    async with session_factory() as session, session.begin():
        await session.execute(delete(UserEntitlementRow).where(UserEntitlementRow.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))


async def add_entitlement(session_factory, user_id, plan_code, status, valid_from, valid_until):
    async with session_factory() as session, session.begin():
        plan_id = (
            await session.execute(select(PlanRow.id).where(PlanRow.code == plan_code))
        ).scalar_one()
        await session.execute(
            insert(UserEntitlementRow).values(
                user_id=user_id,
                plan_id=plan_id,
                status=status,
                valid_from=valid_from,
                valid_until=valid_until,
                updated_at=NOW,
            )
        )


async def current_plan(session_factory, user_id):
    async with session_factory() as session:
        return await get_current_plan(session, user_id, NOW)


async def payment_plan(session_factory, user_id):
    # 決済（購入の判定・GET /payments/me）のトランザクションからの判定（#95）
    async with SqlAlchemyPaymentRepository(session_factory).transaction() as tx:
        return await tx.current_plan(user_id, NOW)


async def test_no_entitlement_is_free(session_factory, user_id):
    assert await current_plan(session_factory, user_id) is PlanCode.FREE
    assert await payment_plan(session_factory, user_id) is PlanCode.FREE


@pytest.mark.parametrize(
    ("plan_code", "status", "valid_from", "valid_until", "expected"),
    [
        ("premium", "active", NOW - DAY, None, PlanCode.PREMIUM),  # 買い切り（期限なし）
        ("premium", "active", NOW - DAY, NOW + DAY, PlanCode.PREMIUM),
        ("premium", "active", NOW, None, PlanCode.PREMIUM),  # 開始ちょうど
        ("premium", "suspended", NOW - DAY, None, PlanCode.FREE),
        ("premium", "active", NOW + DAY, None, PlanCode.FREE),  # 開始前
        ("premium", "active", NOW - 2 * DAY, NOW - DAY, PlanCode.FREE),  # 期限切れ
        ("premium", "active", NOW - DAY, NOW, PlanCode.FREE),  # 期限ちょうど
        ("free", "active", NOW - DAY, None, PlanCode.FREE),  # 無料プランの利用権限
    ],
)
async def test_payment_side_gets_same_plan(
    session_factory, user_id, plan_code, status, valid_from, valid_until, expected
):
    await add_entitlement(session_factory, user_id, plan_code, status, valid_from, valid_until)

    plan = await current_plan(session_factory, user_id)

    assert plan is expected
    # 決済の側（F-05）からも同じ結果になる
    assert await payment_plan(session_factory, user_id) is plan


async def test_other_users_entitlement_is_not_used(session_factory, user_id):
    other = uuid4()
    async with session_factory() as session, session.begin():
        await session.execute(insert(User).values(id=other, firebase_uid=f"test-{other}"))
    try:
        await add_entitlement(session_factory, other, "premium", "active", NOW - DAY, None)

        assert await current_plan(session_factory, user_id) is PlanCode.FREE
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(UserEntitlementRow).where(UserEntitlementRow.user_id == other)
            )
            await session.execute(delete(User).where(User.id == other))
