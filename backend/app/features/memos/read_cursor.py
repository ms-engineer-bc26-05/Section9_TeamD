"""Bounded, validated pagination positions; ownership is always enforced by SQL."""

import base64
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


class InvalidMemoCursor(Exception):
    pass


class MemoCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    created_at: AwareDatetime
    memo_id: UUID

    def encode(self) -> str:
        return base64.urlsafe_b64encode(self.model_dump_json().encode()).decode("ascii")


def decode_cursor(value: str | None) -> MemoCursor | None:
    if value is None:
        return None
    if not value or len(value) > 512:
        raise InvalidMemoCursor
    try:
        data = base64.b64decode(value, altchars=b"-_", validate=True)
        return MemoCursor.model_validate_json(data)
    except ValueError:
        raise InvalidMemoCursor from None
