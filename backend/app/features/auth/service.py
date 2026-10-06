"""通常APIで使う認証処理。内部ユーザーは作成しない。"""

from asyncio import to_thread

from app.core.database import get_session_factory
from app.core.exceptions import (
    AccountDeletingError,
    AuthenticationRequiredError,
    AuthServiceUnavailableError,
)
from app.features.auth.schemas import CurrentUser
from app.features.users.service import get_user_by_firebase_uid
from app.integrations.firebase.client import (
    AuthServiceUnavailableError as FirebaseUnavailableError,
    InvalidTokenError,
    verify_token,
)


async def authenticate_user(token: str) -> CurrentUser:
    """トークンを検証し、利用可能な内部ユーザーを返す。"""
    try:
        firebase_uid = await to_thread(
            verify_token,
            token,
            check_revoked=False,
        )
    except InvalidTokenError:
        raise AuthenticationRequiredError("Authentication required") from None
    except FirebaseUnavailableError:
        raise AuthServiceUnavailableError(
            "Authentication service unavailable"
        ) from None

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_firebase_uid(session, firebase_uid)

        if user is None:
            raise AuthenticationRequiredError("Authentication required")
        if user.status == "deleting":
            raise AccountDeletingError("Account is being deleted")
        if user.status != "active":
            raise RuntimeError("Unexpected account status")

        current_user = CurrentUser(user_id=user.id)

    return current_user
