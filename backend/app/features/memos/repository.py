"""承認済み整理メモ（approved_memos）を保存・検索する入口。

DBの実装は db_repository.py（SQLAlchemy）。ServiceとテストはこのProtocolに対して書き、
テストではメモリ上の実装を使う。

保存の流れ（DB設計「保存処理」・API設計6.5.2）：
  1. トランザクションの外で find_by_consultation により保存済みを確認する
  2. transaction() の中で lock_user（ユーザーの存在・status=active の再確認を含む）
     → find_by_consultation（再検索）→ count_by_user（保存件数の上限の判定。#94）→ insert
  3. insert または commit が DuplicateMemo を送出した場合は、既存のメモを取得して返す

DBの実装で守ること：
  - トランザクションの外の find_by_consultation と transaction() が同じ AsyncSession を使う場合、
    検索で自動的に始まったトランザクションと session.begin() が衝突しない構成にする
  - 一意制約違反（IntegrityError）は flush・commit のどちらでも DuplicateMemo へ変換する
  - DBの例外はメッセージにSQLのパラメータ（暗号文）を含むため、一意制約違反以外も
    メッセージを持たない例外へ包み直して送出する（from None）
"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


class DuplicateMemo(Exception):
    """UNIQUE (user_id, source_consultation_id) に違反した（同じ相談のメモが保存済み）"""


class UserNotFound(Exception):
    """ロック後の再確認で、内部ユーザーが存在しなかった（認証後に削除された）"""


class UserNotActive(Exception):
    """ロック後の再確認で、ユーザーの status が active でなかった（認証後に退会処理が始まった）"""


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
    """1回のDBトランザクション。正常に抜けたらcommit、例外ならrollbackする

    commit 時に一意制約に違反した場合も DuplicateMemo を送出する。
    """

    async def lock_user(self, user_id: UUID) -> None:
        """対象のユーザー行をロックし、ロック後にユーザーの状態を再確認する

        ロックの取得順序は、保存・退会・利用権限変更でそろえる。
        ユーザーが存在しない場合は UserNotFound、status が active でない場合は
        UserNotActive を送出する（トランザクションは rollback され、INSERT へ進まない）。
        """

    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None: ...

    async def count_by_user(self, user_id: UUID) -> int:
        """本人の保存済みメモの件数。lock_user の後に呼び、同時の保存で上限を超えないようにする"""

    async def insert(self, memo: NewMemo) -> StoredMemo:
        """一意制約に違反した場合は DuplicateMemo を送出する"""


class MemoRepository(Protocol):
    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None:
        """user_id と相談IDの両方で検索する（本人以外のメモは見つからない）"""

    async def count_by_user(self, user_id: UUID) -> int:
        """本人の保存済みメモの件数（GET /usage の memo_count。ロックは取らない）"""

    def transaction(self) -> AbstractAsyncContextManager[MemoTransaction]: ...
