"""承認済み整理メモ（approved_memos）を保存・検索する入口。

DBの実装（SQLAlchemy）はI-01のORM・マイグレーション基盤が届いてから追加する。
それまではServiceとテストをこのProtocolに対して書き、テストではメモリ上の実装を使う。

保存の流れ（DB設計「保存処理」・API設計6.5.2）：
  1. トランザクションの外で find_by_consultation により保存済みを確認する
  2. transaction() の中で lock_user → find_by_consultation（再検索）→ insert
  3. insert が DuplicateMemo を送出した場合は、既存のメモを取得して返す
"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class DuplicateMemo(Exception):
    """UNIQUE (user_id, source_consultation_id) に違反した（同じ相談のメモが保存済み）"""


@dataclass(frozen=True)
class NewMemo:
    """INSERTする行。user_id・日時はサーバー側で設定した値だけを入れる"""

    id: UUID
    user_id: UUID
    source_consultation_id: UUID
    encrypted_payload: bytes
    encryption_version: str
    key_version: str
    payload_version: int
    approved_at: datetime
    save_consented_at: datetime


@dataclass(frozen=True)
class StoredMemo:
    """保存済みの行。created_at はDB側で設定される"""

    id: UUID
    user_id: UUID
    source_consultation_id: UUID
    encrypted_payload: bytes
    encryption_version: str
    key_version: str
    payload_version: int
    approved_at: datetime
    save_consented_at: datetime
    created_at: datetime


class MemoTransaction(Protocol):
    """1回のDBトランザクション。正常に抜けたらcommit、例外ならrollbackする"""

    async def lock_user(self, user_id: UUID) -> None:
        """対象のユーザー行をロックする（保存・退会・利用権限変更で取得順序をそろえる）"""

    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None: ...

    async def insert(self, memo: NewMemo) -> StoredMemo:
        """一意制約に違反した場合は DuplicateMemo を送出する"""


class MemoRepository(Protocol):
    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None:
        """user_id と相談IDの両方で検索する（本人以外のメモは見つからない）"""

    def transaction(self) -> AbstractAsyncContextManager[MemoTransaction]: ...
