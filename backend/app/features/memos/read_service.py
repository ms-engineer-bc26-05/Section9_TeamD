"""Owner-scoped memo retrieval, bounded decryption and committed deletion."""

from typing import TypeVar
from uuid import UUID

from cryptography.fernet import Fernet

from app.features.memos.payload import decrypt_memo
from app.features.memos.read_cursor import MemoCursor, decode_cursor
from app.features.memos.read_schemas import MemoDetailResponse, MemoListItem, MemoListResponse
from app.features.memos.repository import StoredMemo

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


PAGE_SIZE = 10


class MemoReadService:
    def __init__(self, repository: MemoReadRepository[StoredMemo], cipher: Fernet) -> None:
        self._repository = repository
        self._cipher = cipher

    async def detail(self, user_id: UUID, memo_id: UUID) -> MemoDetailResponse:
        stored = await get_owned_memo(self._repository, user_id, memo_id)
        payload = decrypt_memo(stored, user_id, self._cipher)
        return MemoDetailResponse(
            memo_id=stored.id, created_at=stored.created_at, **payload.model_dump()
        )

    async def list(self, user_id: UUID, cursor: str | None = None) -> MemoListResponse:
        rows = await self._repository.list_owned(user_id, decode_cursor(cursor), PAGE_SIZE + 1)
        items = []
        for stored in rows[:PAGE_SIZE]:
            if stored.user_id != user_id:
                raise MemoNotFound
            payload = decrypt_memo(stored, user_id, self._cipher)
            summary = payload.event_summary
            if len(summary) > 60:
                summary = summary[:59] + "\u2026"
            items.append(MemoListItem(
                memo_id=stored.id, created_at=stored.created_at,
                summary=summary, handling=payload.handling,
            ))
        next_cursor = None
        if len(rows) > PAGE_SIZE:
            last = rows[PAGE_SIZE - 1]
            next_cursor = MemoCursor(created_at=last.created_at, memo_id=last.id).encode()
        return MemoListResponse(memos=items, next_cursor=next_cursor)
