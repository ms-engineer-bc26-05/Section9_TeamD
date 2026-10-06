"""メモ保存APIのリクエスト・レスポンス（docs/api-design.md 6.5.2）。"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.memos.service import MemoHandling

# 文字数上限（仮置き。Issue #52で相談中）
REASON_MAX_LENGTH = 500


class SaveMemoRequest(BaseModel):
    """POST /consultations/{id}/save"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=REASON_MAX_LENGTH)

    @field_validator("reason")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        # 任意入力のため、空白だけの値は未入力（null）として扱う
        return value or None


class SavedMemoView(BaseModel):
    memo_id: UUID
    created_at: datetime
    handling: MemoHandling
    reason: str | None
    event_summary: str
