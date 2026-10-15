"""Repository contracts for encrypted memo lookup and committed deletion."""

from typing import Protocol, TypeVar
from uuid import UUID

from app.features.memos.read_cursor import MemoCursor


class OwnedMemo(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def user_id(self) -> UUID: ...


MemoT_co = TypeVar("MemoT_co", bound=OwnedMemo, covariant=True)


class MemoReadRepository(Protocol[MemoT_co]):
    async def list_owned(
        self, user_id: UUID, cursor: MemoCursor | None, limit: int
    ) -> list[MemoT_co]:
        """Return encrypted rows ordered by created_at DESC, id DESC."""

    async def find_owned(self, user_id: UUID, memo_id: UUID) -> MemoT_co | None:
        """Filter by both IDs; return encrypted storage data, not plaintext."""

    async def delete_owned(self, user_id: UUID, memo_id: UUID) -> bool:
        """Delete using both IDs and return True only after a successful commit.

        Return False when no matching row exists. On failure, roll back and
        raise a sanitized DB exception, preserving connection-error semantics.
        """
