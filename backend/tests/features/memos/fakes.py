"""テスト用のメモリ上のMemoRepository。DBを使わずにServiceのテストを書くために使う。

- transaction() はブロックを正常に抜けたときだけ反映（commit）し、例外なら破棄（rollback）する
- lock_user はユーザーごとの asyncio.Lock を取り、トランザクション終了まで保持する。
  ロック後に user_statuses でユーザーの状態を再確認する（未設定は active、None は不在）
- commit_error を設定すると、次の commit でその例外を送出する（保存失敗の再現用）
- 検索・INSERT・commit では await asyncio.sleep(0) で処理を譲り、実DBの通信待ちを再現する
  （同時リクエストのテストで、もう一方のリクエストが途中に割り込めるようにする）
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import AsyncIterator
from uuid import UUID

from app.features.memos.repository import (
    DuplicateMemo,
    NewMemo,
    StoredMemo,
    UserNotActive,
    UserNotFound,
)

_Key = tuple[UUID, UUID]  # (user_id, source_consultation_id)


class InMemoryMemoRepository:
    def __init__(self) -> None:
        self.rows: dict[_Key, StoredMemo] = {}
        self.commit_error: Exception | None = None
        # ユーザーの状態（未設定は active、None は内部ユーザーが存在しない）
        self.user_statuses: dict[UUID, str | None] = {}
        self._user_locks: dict[UUID, asyncio.Lock] = {}

    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None:
        await asyncio.sleep(0)
        return self.rows.get((user_id, consultation_id))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["_InMemoryTransaction"]:
        tx = _InMemoryTransaction(self)
        try:
            yield tx
            await asyncio.sleep(0)
            if self.commit_error is not None:
                error, self.commit_error = self.commit_error, None
                raise error
            self.rows.update(tx.pending)
        finally:
            tx.release_locks()

    def user_lock(self, user_id: UUID) -> asyncio.Lock:
        return self._user_locks.setdefault(user_id, asyncio.Lock())


class _InMemoryTransaction:
    def __init__(self, repo: InMemoryMemoRepository) -> None:
        self._repo = repo
        self.pending: dict[_Key, StoredMemo] = {}
        self._held: list[asyncio.Lock] = []

    async def lock_user(self, user_id: UUID) -> None:
        lock = self._repo.user_lock(user_id)
        if lock in self._held:
            return
        await lock.acquire()
        self._held.append(lock)
        status = self._repo.user_statuses.get(user_id, "active")
        if status is None:
            raise UserNotFound
        if status != "active":
            raise UserNotActive

    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None:
        await asyncio.sleep(0)
        key = (user_id, consultation_id)
        return self.pending.get(key) or self._repo.rows.get(key)

    async def insert(self, memo: NewMemo) -> StoredMemo:
        await asyncio.sleep(0)
        key = (memo.user_id, memo.source_consultation_id)
        if key in self.pending or key in self._repo.rows:
            raise DuplicateMemo
        stored = StoredMemo(
            id=memo.id,
            user_id=memo.user_id,
            source_consultation_id=memo.source_consultation_id,
            encrypted_payload=memo.encrypted_payload,
            encryption_version=memo.encryption_version,
            key_version=memo.key_version,
            payload_version=memo.payload_version,
            approved_at=memo.approved_at,
            save_consented_at=memo.save_consented_at,
            created_at=datetime.now(UTC),
        )
        self.pending[key] = stored
        return stored

    def release_locks(self) -> None:
        for lock in reversed(self._held):
            lock.release()
        self._held.clear()
