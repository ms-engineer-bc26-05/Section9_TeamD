"""Ownership checks before detail decryption and committed memo deletion.

HTTP error mapping, authentication, decryption and DB adapters are not wired yet.
"""

from typing import TypeVar
from uuid import UUID

from app.features.memos.read_repository import MemoReadRepository, OwnedMemo


class MemoNotFound(Exception):
    """The memo is absent or unavailable to the requesting user."""


MemoT = TypeVar("MemoT", bound=OwnedMemo)


async def get_owned_memo(
    repository: MemoReadRepository[MemoT], user_id: UUID, memo_id: UUID
) -> MemoT:
    """Return storage data for subsequent decryption, never an HTTP response."""
    memo = await repository.find_owned(user_id, memo_id)
    if memo is None or memo.user_id != user_id or memo.id != memo_id:
        raise MemoNotFound()
    return memo


async def delete_memo(
    repository: MemoReadRepository[MemoT], user_id: UUID, memo_id: UUID
) -> None:
    if not await repository.delete_owned(user_id, memo_id):
        raise MemoNotFound()
