"""保存メモの一覧・詳細APIで返すデータの形式。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MemoListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memo_id: UUID
    created_at: datetime
    summary: str
    handling: Literal["tell", "hold", "not_tell"]


class MemoListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memos: list[MemoListItem]
    next_cursor: str | None = None


class MemoDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memo_id: UUID
    created_at: datetime
    event_summary: str
    emotion: str
    true_feeling: str
    background: str
    wish: str
    handling: Literal["tell", "hold", "not_tell"]
    reason: str | None
