"""内部ユーザーの作成・取得API。"""

from fastapi import APIRouter, Depends, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import AuthenticationRequiredError
from app.features.auth.dependencies import bearer
from app.features.auth.service import register_or_get_user
from app.features.users.schemas import UserResponse

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
