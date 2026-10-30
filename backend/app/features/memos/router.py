"""メモ保存API（docs/api-design.md 6.5.2）。

- Routerの登録（main.py）は結合Issue（I-06）で行う
- 認証は I-01 の get_current_user を使う。401・403・503 は共通のエラーハンドラで返す
- DBは I-01 のセッション基盤を使う。テストでは dependency_overrides でメモリ上の実装へ差し替える
- エラーの本文・ログに、本文・鍵・暗号文を含めない
"""

import os
from uuid import UUID

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, Response, status

from app.core.database import get_session_factory
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.memos.api_schemas import SavedMemoView, SaveMemoRequest
from app.features.memos.crypto import create_fernet
from app.features.memos.db_repository import SqlAlchemyMemoRepository
from app.features.memos.http_errors import MemoRoute
from app.features.memos.limits import GetMemoLimit, get_memo_limit
from app.features.memos.repository import MemoRepository
from app.features.memos.service import MemoSaveService


# ---------------------------------------------------------------------------
# 認証
# ---------------------------------------------------------------------------


async def get_current_user_id(current_user: CurrentUser = Depends(get_current_user)) -> UUID:
    """I-01の認証依存から内部ユーザーのIDを取り出す。

    テストでは dependency_overrides で固定UUIDを返す。
    """
    return current_user.user_id


# ---------------------------------------------------------------------------
# 依存
# ---------------------------------------------------------------------------


def get_memo_repository() -> MemoRepository:
    return SqlAlchemyMemoRepository(get_session_factory())


def get_memo_cipher() -> Fernet:
    """鍵は環境変数から読む。未設定・不正な場合は MemoEncryptionError（500）"""
    return create_fernet(os.environ.get("MEMO_ENCRYPTION_KEY"))


def get_memo_limit_getter() -> GetMemoLimit:
    """保存件数の上限値の取得。テストでは dependency_overrides で固定値を返す関数へ差し替える"""
    return get_memo_limit


def get_memo_save_service(
    repository: MemoRepository = Depends(get_memo_repository),
    cipher: Fernet = Depends(get_memo_cipher),
    get_limit: GetMemoLimit = Depends(get_memo_limit_getter),
) -> MemoSaveService:
    return MemoSaveService(repository, cipher, get_limit=get_limit)


router = APIRouter(
    prefix="/api/v1/consultations",
    tags=["memos"],
    route_class=MemoRoute,
)


@router.post(
    "/{consultation_id}/save",
    status_code=status.HTTP_201_CREATED,
    response_model=SavedMemoView,
)
async def save_memo(
    consultation_id: UUID,
    body: SaveMemoRequest,
    response: Response,
    user_id: UUID = Depends(get_current_user_id),
    service: MemoSaveService = Depends(get_memo_save_service),
) -> SavedMemoView:
    memo, created = await service.save(user_id, consultation_id, body.reason)
    if not created:
        # 保存済みのメモを返す場合（再試行・同時リクエスト）
        response.status_code = status.HTTP_200_OK
    return SavedMemoView(
        memo_id=memo.memo_id,
        created_at=memo.created_at,
        handling=memo.handling,
        reason=memo.reason,
        event_summary=memo.event_summary,
    )
