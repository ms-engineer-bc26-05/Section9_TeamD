"""内部ユーザーの作成・取得API。"""

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import AuthenticationRequiredError
from app.features.auth.dependencies import bearer, get_current_user
from app.features.auth.service import register_or_get_user
from app.features.users.deletion_http import DeletionRoute
from app.features.users.deletion_service import delete_account, get_deletion_service
from app.features.users.schemas import UserNoticeUpdate, UserResponse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.features.auth.schemas import CurrentUser
from app.features.users.service import update_user_notice

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/me",
    response_model=UserResponse,
    status_code=200,
    responses={201: {"model": UserResponse}},
)
async def register_user(
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> UserResponse:
    if credentials is None or not credentials.credentials.strip():
        raise AuthenticationRequiredError("Authentication required")

    user, created = await register_or_get_user(credentials.credentials)

    if created:
        response.status_code = 201

    return user


@router.patch("/me", response_model=UserResponse)
async def update_notice(
    payload: UserNoticeUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    return await update_user_notice(session, current_user.user_id)


async def require_deletion_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None or not credentials.credentials.strip():
        raise AuthenticationRequiredError
    return credentials.credentials


async def withdraw_user(
    token: str = Depends(require_deletion_token),
    service=Depends(get_deletion_service),
) -> Response:
    await delete_account(token, service)
    return Response(status_code=204)


router.add_api_route(
    "/me",
    withdraw_user,
    methods=["DELETE"],
    status_code=204,
    route_class_override=DeletionRoute,
)
