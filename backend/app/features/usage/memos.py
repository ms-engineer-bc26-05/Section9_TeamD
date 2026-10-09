"""保存メモの件数の取得（GET /usage の memo_count）。

API設計6.7のとおり、件数はRedisでは数えず、DBの approved_memos を本人の user_id で数える。
F-01・I-05の件数取得の関数ができたら、get_memo_counter の中身を差し替える。
それまでは、誤って結合しても実際と違う件数を返さないよう、常に MemoCountUnavailable とする。
"""

from typing import Protocol
from uuid import UUID

from app.features.usage.exceptions import MemoCountUnavailable


class MemoCounter(Protocol):
    async def count(self, user_id: UUID) -> int: ...


class UnavailableMemoCounter:
    async def count(self, user_id: UUID) -> int:
        raise MemoCountUnavailable


_counter = UnavailableMemoCounter()


def get_memo_counter() -> MemoCounter:
    """APIで使う件数取得。テストでは dependency_overrides 等で差し替える"""
    return _counter
