"""Repository contracts for memo lookup and deletion; DB adapters are pending."""

from typing import Protocol, TypeVar
from uuid import UUID


class OwnedMemo(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def user_id(self) -> UUID: ...


MemoT_co = TypeVar("MemoT_co", bound=OwnedMemo, covariant=True)


class MemoReadRepository(Protocol[MemoT_co]):
    async def find_owned(self, user_id: UUID, memo_id: UUID) -> MemoT_co | None:
        """Filter by both IDs; return encrypted storage data, not plaintext."""

    async def delete_owned(self, user_id: UUID, memo_id: UUID) -> bool:
        """Delete using both IDs and return True only after a successful commit.

        Return False when no matching row exists. On failure, roll back and
        raise a sanitized DB exception, preserving connection-error semantics.
        """
