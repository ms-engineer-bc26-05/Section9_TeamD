"""保存メモの件数の取得（GET /usage の memo_count）。

API設計6.7のとおり、件数はRedisでは数えず、DBの approved_memos を本人の user_id で数える。
保存の上限判定と同じ関数（memos/public.py の count_saved_memos。#94）を使う。
DBで件数を確認できない場合は、0件などと推測せず MemoCountUnavailable（503）とする。
"""

from typing import Protocol
from uuid import UUID

from app.core.exceptions import DatabaseUnavailableError
from app.features.memos.public import MemoDatabaseError, count_saved_memos
from app.features.usage.exceptions import MemoCountUnavailable


class MemoCounter(Protocol):
    async def count(self, user_id: UUID) -> int: ...


class SavedMemoCounter:
    async def count(self, user_id: UUID) -> int:
        try:
            return await count_saved_memos(user_id)
        except (DatabaseUnavailableError, MemoDatabaseError):
            raise MemoCountUnavailable from None


_counter = SavedMemoCounter()


def get_memo_counter() -> MemoCounter:
    """APIで使う件数取得。テストでは dependency_overrides 等で差し替える"""
    return _counter
