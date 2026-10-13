"""Opt-in PostgreSQL CRUD tests; use only an explicitly approved test database."""

import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core import config
from app.core.database import make_database_url
from app.features.memos.models import ApprovedMemo
from app.features.memos.read_cursor import MemoCursor
from app.features.memos.read_db_repository import SqlAlchemyMemoReadRepository
from app.features.memos.read_service import MemoReadService, MemoNotFound, delete_memo
from app.features.users.models import User
from tests.features.memos.test_read_router import make_row

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="Requires an approved PostgreSQL test database"
)


@pytest.fixture
async def database():
    engine = create_async_engine(make_database_url(config.DATABASE_URL), hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    users = [uuid4(), uuid4()]
    try:
        async with factory() as session, session.begin():
            await session.execute(insert(User), [
                {"id": user, "firebase_uid": f"synthetic-read-{user}"} for user in users
            ])
        yield engine, factory, users
    finally:
        async with factory() as session, session.begin():
            await session.execute(delete(ApprovedMemo).where(ApprovedMemo.user_id.in_(users)))
            await session.execute(delete(User).where(User.id.in_(users)))
        await engine.dispose()


async def seed(factory, rows):
    async with factory() as session, session.begin():
        await session.execute(insert(ApprovedMemo), [asdict(row) for row in rows])


async def test_encrypted_detail_delete_and_other_owner(database):
    engine, factory, (owner, other) = database
    cipher = Fernet(Fernet.generate_key())
    row = make_row(cipher, user_id=owner)
    await seed(factory, [row])
    repo = SqlAlchemyMemoReadRepository(factory)
    service = MemoReadService(repo, cipher)
    assert (await service.detail(owner, row.id)).event_summary == "synthetic-private-memo"
    assert await repo.find_owned(other, row.id) is None
    assert not await repo.delete_owned(other, row.id)
    assert await repo.find_owned(owner, row.id) is not None
    await delete_memo(repo, owner, row.id)
    assert await repo.find_owned(owner, row.id) is None
    with pytest.raises(MemoNotFound):
        await delete_memo(repo, owner, row.id)


async def test_database_pagination_orders_ties_and_excludes_other_owner(database):
    engine, factory, (owner, other) = database
    cipher = Fernet(Fernet.generate_key())
    now = datetime.now(UTC)
    rows = [make_row(cipher, user_id=owner, created_at=now) for _ in range(12)]
    foreign = make_row(cipher, user_id=other, created_at=now + timedelta(days=1))
    await seed(factory, rows + [foreign])
    repo = SqlAlchemyMemoReadRepository(factory)
    expected = sorted(rows, key=lambda row: row.id, reverse=True)
    first = await repo.list_owned(owner, None, 10)
    assert [row.id for row in first] == [row.id for row in expected[:10]]
    cursor = MemoCursor(created_at=first[-1].created_at, memo_id=first[-1].id)
    await repo.delete_owned(owner, first[-1].id)
    second = await repo.list_owned(owner, cursor, 10)
    assert [row.id for row in second] == [row.id for row in expected[10:]]


async def test_delete_failure_rolls_back_and_retry_succeeds(database):
    engine, factory, (owner, other) = database
    row = make_row(Fernet(Fernet.generate_key()), user_id=owner)
    await seed(factory, [row])

    class FailingDeleteSession(AsyncSession):
        async def execute(self, statement, *args, **kwargs):
            result = await super().execute(statement, *args, **kwargs)
            if getattr(statement, "is_delete", False):
                raise RuntimeError("synthetic failure after DELETE")
            return result

    failing = SqlAlchemyMemoReadRepository(async_sessionmaker(engine, class_=FailingDeleteSession))
    with pytest.raises(RuntimeError):
        await failing.delete_owned(owner, row.id)
    repo = SqlAlchemyMemoReadRepository(factory)
    assert await repo.find_owned(owner, row.id) is not None
    assert await repo.delete_owned(owner, row.id)
