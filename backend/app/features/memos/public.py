"""メモ機能の公開インターフェース。他の機能からは、このモジュールだけをimportする。"""

from uuid import UUID

from app.core.database import get_session_factory
from app.features.memos.db_repository import SqlAlchemyMemoRepository
from app.features.memos.exceptions import MemoDatabaseError

__all__ = ["MemoDatabaseError", "count_saved_memos"]


async def count_saved_memos(user_id: UUID) -> int:
    """本人の保存済みメモの件数（GET /usage の memo_count。#94）。

    保存の上限判定（service.py）と同じく、DBの approved_memos を user_id で数える。
    DBの失敗は DatabaseUnavailableError（接続障害）か MemoDatabaseError を送出する。
    """
    return await SqlAlchemyMemoRepository(get_session_factory()).count_by_user(user_id)
