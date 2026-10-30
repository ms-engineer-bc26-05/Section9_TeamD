"""Memo list/detail/delete endpoints; application registration belongs to #53."""

from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Query, Response

from app.core.database import get_session_factory
from app.features.memos.read_db_repository import SqlAlchemyMemoReadRepository
from app.features.memos.read_http_errors import MemoReadRoute
from app.features.memos.read_repository import MemoReadRepository
from app.features.memos.read_schemas import MemoDetailResponse, MemoListResponse
from app.features.memos.read_service import MemoReadService, delete_memo
from app.features.memos.repository import StoredMemo
from app.features.memos.router import get_current_user_id, get_memo_cipher


def get_memo_read_repository() -> MemoReadRepository[StoredMemo]:
    return SqlAlchemyMemoReadRepository(get_session_factory())


def get_memo_read_service(
    repository: MemoReadRepository[StoredMemo] = Depends(get_memo_read_repository),
    cipher: Fernet = Depends(get_memo_cipher),
) -> MemoReadService:
    return MemoReadService(repository, cipher)


router = APIRouter(prefix="/api/v1/memos", tags=["memos"], route_class=MemoReadRoute)


@router.get("", response_model=MemoListResponse)
async def list_memos(
    cursor: str | None = Query(default=None, max_length=512),
    user_id: UUID = Depends(get_current_user_id),
    service: MemoReadService = Depends(get_memo_read_service),
) -> MemoListResponse:
    return await service.list(user_id, cursor)


@router.get("/{memo_id}", response_model=MemoDetailResponse)
async def get_memo(
    memo_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: MemoReadService = Depends(get_memo_read_service),
) -> MemoDetailResponse:
    return await service.detail(user_id, memo_id)


@router.delete("/{memo_id}", status_code=204)
async def remove_memo(
    memo_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    repository: MemoReadRepository[StoredMemo] = Depends(get_memo_read_repository),
) -> Response:
    await delete_memo(repository, user_id, memo_id)
    return Response(status_code=204)
