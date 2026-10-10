"""通常APIが Depends で利用する認証依存。内部ユーザーは作成しない。"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import AuthenticationRequiredError
from app.features.auth.schemas import CurrentUser
from app.features.auth.service import authenticate_user

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    if credentials is None or not credentials.credentials.strip():
        raise AuthenticationRequiredError("Authentication required")

    return await authenticate_user(credentials.credentials)
