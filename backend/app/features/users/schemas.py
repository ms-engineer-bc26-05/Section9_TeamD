"""ユーザーAPIで扱うデータの形式。"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    has_seen_notice: bool


class UserNoticeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_seen_notice: StrictBool

    @field_validator("has_seen_notice")
    @classmethod
    def require_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("has_seen_notice must be true")
        return value
