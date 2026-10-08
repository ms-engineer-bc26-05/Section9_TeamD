"""ユーザーAPIで返すデータの形式。"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    has_seen_notice: bool
