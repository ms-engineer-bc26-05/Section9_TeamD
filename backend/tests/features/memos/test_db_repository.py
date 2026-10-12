"""メモのDB実装のテスト。実際のPostgreSQLに接続する。

通常のテストでは実行しない。マイグレーションを適用したDBに対して、次のように実行する：
  docker compose run --rm -e RUN_DB_TESTS=1 backend python -m pytest tests/features/memos/test_db_repository.py
テストで作ったユーザー・メモは、終了時に削除する。テストデータはすべて架空。
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import config
from app.core.database import make_database_url
from app.features.consultations.public import ConsultationNotFound
from app.features.memos.crypto import create_fernet
from app.features.memos.db_repository import SqlAlchemyMemoRepository
from app.features.memos.models import ApprovedMemo
from app.features.memos.repository import DuplicateMemo, NewMemo, UserNotActive, UserNotFound
from app.features.memos.service import MemoSaveService
from app.features.users.models import User

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1", reason="実DBのテストは RUN_DB_TESTS=1 のときだけ実行する"
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
        await session.execute(delete(ApprovedMemo).where(ApprovedMemo.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))


@pytest.fixture
def repo(session_factory):
    return SqlAlchemyMemoRepository(session_factory)


def make_memo(user_id: UUID, consultation_id: UUID) -> NewMemo:
    now = datetime.now(UTC)
    return NewMemo(
        id=uuid4(),
        user_id=user_id,
        source_consultation_id=consultation_id,
        encrypted_payload=b"fake-ciphertext",
        encryption_version="fernet-v1",
        key_version="v1",
        payload_version=1,
        approved_at=now,
        save_consented_at=now,
    )


async def test_insert_then_find(repo, user_id):
    consultation_id = uuid4()
    memo = make_memo(user_id, consultation_id)

    async with repo.transaction() as tx:
        await tx.lock_user(user_id)
        stored = await tx.insert(memo)

    assert stored.created_at is not None
    found = await repo.find_by_consultation(user_id, consultation_id)
    assert found == stored
    # 本人以外の user_id では見つからない
    assert await repo.find_by_consultation(uuid4(), consultation_id) is None


async def test_duplicate_is_converted_and_rolled_back(repo, user_id, session_factory):
    consultation_id = uuid4()
    async with repo.transaction() as tx:
        await tx.insert(make_memo(user_id, consultation_id))

    with pytest.raises(DuplicateMemo) as raised:
        async with repo.transaction() as tx:
            await tx.insert(make_memo(user_id, consultation_id))

    # 元の例外（SQLのパラメータを含む）を残さない
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
    async with session_factory() as session:
        rows = (await session.execute(select(ApprovedMemo).where(ApprovedMemo.user_id == user_id))).all()
    assert len(rows) == 1


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


@dataclass(frozen=True)
class _Result:
    event_summary: str = "架空の出来事の要約"
    emotion: str = "架空の気持ち"
    true_feeling: str = "架空の本音"
    background: str = "架空の背景"
    wish: str = "架空の望み"

    def model_dump(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class _Handling:
    value: str = "hold"


@dataclass(frozen=True)
class _Approved:
    consultation_id: UUID
    result: _Result = _Result()
    handling: _Handling = _Handling()
    approved_at: datetime = datetime(2026, 10, 10, tzinfo=UTC)


async def test_concurrent_saves_create_one_row_with_ciphertext_only(repo, user_id, session_factory):
    consultation_id = uuid4()
    discarded = False

    async def get_approved(uid: UUID, cid: UUID) -> _Approved:
        if discarded:
            raise ConsultationNotFound
        return _Approved(consultation_id=cid)

    async def discard(uid: UUID, cid: UUID) -> None:
        nonlocal discarded
        discarded = True

    cipher = create_fernet(Fernet.generate_key().decode("ascii"))
    service = MemoSaveService(repo, cipher, get_approved=get_approved, discard=discard)

    (first, _), (second, _) = await asyncio.gather(
        service.save(user_id, consultation_id, "架空の理由"),
        service.save(user_id, consultation_id, "架空の理由"),
    )

    assert first.memo_id == second.memo_id
    async with session_factory() as session:
        rows = (
            await session.execute(select(ApprovedMemo).where(ApprovedMemo.user_id == user_id))
        ).scalars().all()
    assert len(rows) == 1
    # DBには暗号文だけが入っている
    stored = rows[0].encrypted_payload
    for plain in ("架空の出来事の要約", "架空の本音", "架空の理由"):
        assert plain.encode() not in stored
