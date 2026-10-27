"""決済のDB実装のテスト。実際のPostgreSQLに接続する（Stripeは fakes.py の偽物）。

通常のテストでは実行しない。マイグレーションを適用したDBに対して、次のように実行する：
  docker compose run --rm -e RUN_DB_TESTS=1 backend python -m pytest tests/features/payments/test_db_repository.py
テストで作ったユーザー・決済・利用権限は、終了時に削除する。テストデータはすべて架空。
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import config
from app.core.database import make_database_url
from app.features.payments.confirm import ConfirmResult, PaymentConfirmService
from app.features.payments.db_repository import SqlAlchemyPaymentRepository
from app.features.payments.exceptions import AlreadyPaid, PaymentDatabaseError
from app.features.payments.models import PaymentRow, PlanRow, UserEntitlementRow
from app.features.payments.repository import (
    CheckoutRequest,
    DuplicateUnfinishedPayment,
    NewPayment,
    UserNotActive,
    UserNotFound,
)
from app.features.payments.service import CheckoutService
from app.features.payments.settings import CheckoutSettings
from app.features.payments.settlement import PaymentSettlementService
from app.features.plans.public import PlanCode
from app.features.users.models import User
from tests.features.payments.fakes import FakeStripe

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="実DBのテストは RUN_DB_TESTS=1 のときだけ実行する"
)

SETTINGS = CheckoutSettings(
    price_ids={"premium": "price_dummy"},
    success_url="http://localhost:3000/plan/success?session_id={CHECKOUT_SESSION_ID}",
    cancel_url="http://localhost:3000/plan",
)


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
        await session.execute(delete(PaymentRow).where(PaymentRow.user_id == user_id))
        await session.execute(delete(UserEntitlementRow).where(UserEntitlementRow.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))


@pytest.fixture
def repo(session_factory):
    return SqlAlchemyPaymentRepository(session_factory)


@pytest.fixture
def stripe() -> FakeStripe:
    return FakeStripe()


async def premium_plan_id(session_factory) -> UUID:
    async with session_factory() as session:
        return (
            await session.execute(select(PlanRow.id).where(PlanRow.code == "premium"))
        ).scalar_one()


async def payments_of(session_factory, user_id: UUID) -> list[PaymentRow]:
    async with session_factory() as session:
        return list(
            (await session.execute(select(PaymentRow).where(PaymentRow.user_id == user_id)))
            .scalars()
            .all()
        )


def new_payment(user_id: UUID, plan_id: UUID) -> NewPayment:
    payment_id = uuid4()
    return NewPayment(
        id=payment_id,
        user_id=user_id,
        plan_id=plan_id,
        idempotency_key=uuid4(),
        amount_minor=300,
        currency="jpy",
        checkout_request=CheckoutRequest(
            price_id="price_dummy",
            expires_at=datetime(2026, 10, 12, 12, 35, tzinfo=UTC),
            success_url=SETTINGS.success_url,
            cancel_url=SETTINGS.cancel_url,
            client_reference_id=str(user_id),
            metadata={"payment_id": str(payment_id)},
        ),
    )


# --- Repositoryの契約 ------------------------------------------------------------


async def test_plans_are_seeded(repo):
    async with repo.transaction() as tx:
        free = await tx.find_plan("free")
        premium = await tx.find_plan("premium")
        missing = await tx.find_plan("unknown")
    assert free is not None and free.is_active
    assert premium is not None and premium.is_active
    assert missing is None


async def test_insert_keeps_checkout_request(repo, user_id, session_factory):
    payment = new_payment(user_id, await premium_plan_id(session_factory))
    async with repo.transaction() as tx:
        await tx.lock_user(user_id)
        await tx.insert(payment)

    stored = await repo.find_unfinished(user_id)
    assert stored is not None
    assert stored.status == "creating"
    assert stored.checkout_request == payment.checkout_request
    assert stored.idempotency_key == payment.idempotency_key


async def test_second_unfinished_payment_is_rejected(repo, user_id, session_factory):
    plan_id = await premium_plan_id(session_factory)
    async with repo.transaction() as tx:
        await tx.insert(new_payment(user_id, plan_id))

    with pytest.raises(DuplicateUnfinishedPayment):
        async with repo.transaction() as tx:
            await tx.insert(new_payment(user_id, plan_id))

    assert len(await payments_of(session_factory, user_id)) == 1


async def test_lock_user_rechecks_status(repo, user_id, session_factory):
    with pytest.raises(UserNotFound):
        async with repo.transaction() as tx:
            await tx.lock_user(uuid4())

    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        user.status = "deleting"

    with pytest.raises(UserNotActive):
        async with repo.transaction() as tx:
            await tx.lock_user(user_id)
    async with repo.transaction() as tx:
        assert await tx.lock_user(user_id, require_active=False) == "deleting"


async def test_update_in_unexpected_state_is_not_silent(repo, user_id, session_factory):
    payment = new_payment(user_id, await premium_plan_id(session_factory))
    async with repo.transaction() as tx:
        await tx.insert(payment)

    # creating の行を paid にはできない（呼び出し側の誤りを成功扱いにしない）
    with pytest.raises(PaymentDatabaseError):
        async with repo.transaction() as tx:
            await tx.mark_paid(payment.id, datetime.now(UTC))

    [row] = await payments_of(session_factory, user_id)
    assert row.status == "creating"


# --- Serviceと組み合わせた流れ -------------------------------------------------------


async def test_checkout_confirm_and_already_paid(repo, user_id, stripe, session_factory):
    started = await CheckoutService(repo, stripe, SETTINGS).create_checkout(user_id, "premium")
    stripe.pay(started.session_id)

    result = await PaymentConfirmService(repo, stripe).confirm(user_id, started.session_id)

    assert result == ConfirmResult("paid")
    [row] = await payments_of(session_factory, user_id)
    assert row.status == "paid"
    assert row.verified_at is not None
    assert row.entitlement_applied_at is not None
    async with session_factory() as session:
        entitlement = await session.get(UserEntitlementRow, user_id)
    assert entitlement is not None
    assert entitlement.status == "active"
    assert entitlement.valid_until is None
    # 有料の利用権限があるので、もう一度は購入できない
    with pytest.raises(AlreadyPaid):
        await CheckoutService(repo, stripe, SETTINGS).create_checkout(user_id, "premium")


async def test_free_entitlement_is_not_paid(repo, user_id, session_factory):
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        free_id = (
            await session.execute(select(PlanRow.id).where(PlanRow.code == "free"))
        ).scalar_one()
        await session.execute(
            insert(UserEntitlementRow).values(
                user_id=user_id,
                plan_id=free_id,
                status="active",
                valid_from=now - timedelta(days=1),
                updated_at=now,
            )
        )
    async with repo.transaction() as tx:
        assert await tx.current_plan(user_id, now) is PlanCode.FREE


async def test_concurrent_checkouts_create_one_session(repo, user_id, stripe, session_factory):
    service = CheckoutService(repo, stripe, SETTINGS)

    first, second = await asyncio.gather(
        service.create_checkout(user_id, "premium"),
        service.create_checkout(user_id, "premium"),
        return_exceptions=True,
    )

    assert stripe.created_session_count == 1
    assert len(await payments_of(session_factory, user_id)) == 1
    started = [r for r in (first, second) if not isinstance(r, Exception)]
    assert started
    assert {s.session_id for s in started} == set(stripe.sessions)


async def test_settlement_expires_open_session(repo, user_id, stripe, session_factory):
    started = await CheckoutService(repo, stripe, SETTINGS).create_checkout(user_id, "premium")
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        user.status = "deleting"

    await PaymentSettlementService(repo, stripe).settle_unfinished_payments(user_id)

    [row] = await payments_of(session_factory, user_id)
    assert row.status == "expired"
    assert stripe.sessions[started.session_id].status == "expired"
