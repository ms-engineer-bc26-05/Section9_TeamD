"""他機能へ公開する認証済みユーザーの型。"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CurrentUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
