"""Opt-in synthetic PostgreSQL tests for deletion transactions."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import config
from app.core.database import make_database_url
from app.core.errors import register_exception_handlers
from app.features.memos.models import ApprovedMemo
from app.features.payments.models import PaymentRow, PlanRow, UserEntitlementRow
from app.features.users.deletion_repository import DeletionBlocked, DeletionRepository
from app.features.users.deletion_service import DeletionService, get_deletion_service
from app.features.users.models import User
from app.features.users.router import router

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="Requires approved disposable database"
)


@pytest.fixture
async def db():
    engine = create_async_engine(make_database_url(config.DATABASE_URL), hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owner, other = uuid4(), uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            insert(User),
            [{"id": uid, "firebase_uid": f"synthetic-{uid}"} for uid in (owner, other)],
        )
        now = datetime.now(UTC)
        await session.execute(
            insert(ApprovedMemo),
            [
                {
                    "id": uuid4(),
                    "user_id": uid,
                    "source_consultation_id": uuid4(),
                    "encrypted_payload": b"synthetic-ciphertext",
                    "encryption_version": "test",
                    "key_version": "test",
                    "payload_version": 1,
                    "approved_at": now,
                    "save_consented_at": now,
                }
                for uid in (owner, other)
            ],
        )
    try:
        yield engine, factory, owner, other
    finally:
        async with factory() as session, session.begin():
            for model in (ApprovedMemo, PaymentRow, UserEntitlementRow):
                await session.execute(delete(model).where(model.user_id.in_((owner, other))))
            await session.execute(delete(User).where(User.id.in_((owner, other))))
        await engine.dispose()


async def seed_payment(factory, owner, status):
    async with factory() as session, session.begin():
        plan = (
            await session.execute(select(PlanRow.id).where(PlanRow.code == "premium"))
        ).scalar_one()
        await session.execute(
            insert(PaymentRow).values(
                id=uuid4(),
                user_id=owner,
                plan_id=plan,
                idempotency_key=uuid4(),
                status=status,
                amount_minor=300,
                currency="jpy",
                checkout_request={},
            )
        )
        await session.execute(
            insert(UserEntitlementRow).values(
                user_id=owner,
                plan_id=plan,
                status="active",
                valid_from=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )


async def test_success_deletes_only_owner_and_related_rows(db):
    _, factory, owner, other = db
    await seed_payment(factory, owner, "expired")
    repo = DeletionRepository(factory)
    service = DeletionService(
        repo,
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(return_value=True),
        AsyncMock(return_value=f"synthetic-{owner}"),
    )
    await service.delete("synthetic-token")
    async with factory() as session:
        assert await session.get(User, owner) is None
        assert (await session.get(User, other)).status == "active"
        for model in (ApprovedMemo, PaymentRow, UserEntitlementRow):
            assert not (await session.execute(select(model).where(model.user_id == owner))).first()
        assert (
            await session.execute(select(ApprovedMemo).where(ApprovedMemo.user_id == other))
        ).first()


async def test_creating_preserves_active_and_memos(db):
    _, factory, owner, _ = db
    await seed_payment(factory, owner, "creating")
    with pytest.raises(DeletionBlocked):
        await DeletionRepository(factory).begin(f"synthetic-{owner}")
    async with factory() as session:
        assert (await session.get(User, owner)).status == "active"
        assert (
            await session.execute(select(ApprovedMemo).where(ApprovedMemo.user_id == owner))
        ).first()


async def test_pending_blocks_final_delete_and_preserves_anchor(db):
    _, factory, owner, _ = db
    await seed_payment(factory, owner, "pending")
    repo = DeletionRepository(factory)
    await repo.begin(f"synthetic-{owner}")
    await repo.delete_memos(owner)
    with pytest.raises(DeletionBlocked):
        await repo.finish(owner)
    async with factory() as session:
        assert (await session.get(User, owner)).status == "deleting"
        assert await session.get(UserEntitlementRow, owner) is not None


async def test_final_failure_rolls_back_and_recovery_retries(db):
    engine, factory, owner, _ = db
    await seed_payment(factory, owner, "expired")
    repo = DeletionRepository(factory)
    await repo.begin(f"synthetic-{owner}")
    await repo.delete_memos(owner)

    class FailingSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            result = await super().execute(statement, *args, **kwargs)
            if getattr(statement, "is_delete", False) and statement.table.name == "users":
                raise RuntimeError("synthetic final failure")
            return result

    broken = DeletionRepository(async_sessionmaker(engine, class_=FailingSession))
    with pytest.raises(RuntimeError):
        await broken.finish(owner)
    async with factory() as session:
        assert (await session.get(User, owner)).status == "deleting"
        assert await session.get(UserEntitlementRow, owner) is not None
        assert (
            await session.execute(select(PaymentRow).where(PaymentRow.user_id == owner))
        ).first()
    service = DeletionService(
        repo,
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(return_value=True),
        AsyncMock(),
    )
    await service.recover(owner)
    async with factory() as session:
        assert await session.get(User, owner) is None
    assert service.clear_usage.await_count == 2


async def test_recovery_rejects_active_user(db):
    _, factory, owner, _ = db
    with pytest.raises(DeletionBlocked):
        await DeletionRepository(factory).recovery_uid(owner)


async def test_http_to_database_success_is_committed(db):
    _, factory, owner, other = db
    repo = DeletionRepository(factory)
    service = DeletionService(
        repo,
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(return_value=True),
        AsyncMock(return_value=f"synthetic-{owner}"),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_deletion_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete(
            "/users/me", headers={"Authorization": "Bearer synthetic-token"}
        )
    assert response.status_code == 204
    assert response.content == b""
    async with factory() as session:
        assert await session.get(User, owner) is None
        assert await session.get(User, other) is not None
