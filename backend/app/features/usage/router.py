"""利用状況API（docs/api-design.md 6.7）。

- Routerの登録（main.py）は結合Issue（I-06）で行う
- 認証は I-01 の get_current_user を使う
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.usage.http_errors import UsageRoute
from app.features.usage.schemas import UsageView
from app.features.usage.service import UsageService, get_usage_service


async def get_current_user_id(
    current_user: CurrentUser = Depends(get_current_user),
) -> UUID:
    """認証済み内部ユーザーのIDを返す。"""
    return current_user.user_id


router = APIRouter(prefix="/api/v1/usage", tags=["usage"], route_class=UsageRoute)


@router.get("", response_model=UsageView)
async def get_usage(
    user_id: UUID = Depends(get_current_user_id),
    service: UsageService = Depends(get_usage_service),
) -> UsageView:
    """利用回数・プランの概況（6.7）"""
    return await service.get_usage(user_id)
