"""テスト用のメモリ実装が、DBと同じ前提で動くことを確認する（Serviceのテストの土台）"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.features.memos.repository import DuplicateMemo, NewMemo
from tests.features.memos.fakes import InMemoryMemoRepository

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_USER_ID = UUID("22222222-2222-4222-8222-222222222222")
CONSULTATION_ID = UUID("55555555-5555-4555-8555-555555555555")
FIXED_AT = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def make_new_memo(
    user_id: UUID = USER_ID, consultation_id: UUID = CONSULTATION_ID
) -> NewMemo:
    return NewMemo(
        id=uuid4(),
        user_id=user_id,
        source_consultation_id=consultation_id,
        encrypted_payload=b"fake-ciphertext",
        encryption_version="fernet-v1",
        key_version="test",
        payload_version=1,
        approved_at=FIXED_AT,
        save_consented_at=FIXED_AT,
    )


async def test_insert_is_visible_after_commit():
    repo = InMemoryMemoRepository()
    memo = make_new_memo()

    async with repo.transaction() as tx:
        await tx.lock_user(USER_ID)
        stored = await tx.insert(memo)
        assert await repo.find_by_consultation(USER_ID, CONSULTATION_ID) is None

    assert await repo.find_by_consultation(USER_ID, CONSULTATION_ID) == stored
    assert stored.created_at.tzinfo is not None


async def test_other_users_memo_is_not_found():
    repo = InMemoryMemoRepository()
    async with repo.transaction() as tx:
        await tx.insert(make_new_memo())

    assert await repo.find_by_consultation(OTHER_USER_ID, CONSULTATION_ID) is None


async def test_exception_rolls_back_insert():
    repo = InMemoryMemoRepository()

    with pytest.raises(RuntimeError):
        async with repo.transaction() as tx:
            await tx.insert(make_new_memo())
            raise RuntimeError

    assert repo.rows == {}


async def test_commit_error_rolls_back_and_is_raised_once():
    repo = InMemoryMemoRepository()
    repo.commit_error = RuntimeError("commit failed")

    with pytest.raises(RuntimeError):
        async with repo.transaction() as tx:
            await tx.insert(make_new_memo())

    assert repo.rows == {}
    async with repo.transaction() as tx:
        await tx.insert(make_new_memo())
    assert len(repo.rows) == 1


async def test_duplicate_insert_raises():
    repo = InMemoryMemoRepository()
    async with repo.transaction() as tx:
        await tx.insert(make_new_memo())

    with pytest.raises(DuplicateMemo):
        async with repo.transaction() as tx:
            await tx.insert(make_new_memo())


async def test_lock_user_serializes_transactions_for_same_user():
    repo = InMemoryMemoRepository()
    order: list[str] = []
    first_locked = asyncio.Event()

    async def first() -> None:
        async with repo.transaction() as tx:
            await tx.lock_user(USER_ID)
            first_locked.set()
            await asyncio.sleep(0)
            order.append("first-done")

    async def second() -> None:
        await first_locked.wait()
        async with repo.transaction() as tx:
            await tx.lock_user(USER_ID)
            order.append("second-locked")

    await asyncio.gather(first(), second())

    assert order == ["first-done", "second-locked"]
