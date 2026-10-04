"""通常APIで使う認証処理。内部ユーザーは作成しない。"""

from asyncio import to_thread

from app.core.database import get_session_factory
from app.features.auth.schemas import CurrentUser
from app.features.users.service import get_user_by_firebase_uid
from app.integrations.firebase.client import verify_token


class AuthenticationRequiredError(Exception):
    """対応する内部ユーザーが存在しない。"""


class AccountDeletingError(Exception):
    """内部ユーザーが退会処理中。"""


async def authenticate_user(token: str) -> CurrentUser:
    """トークンを検証し、利用可能な内部ユーザーを返す。"""
    firebase_uid = await to_thread(
        verify_token,
        token,
        check_revoked=False,
    )

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
