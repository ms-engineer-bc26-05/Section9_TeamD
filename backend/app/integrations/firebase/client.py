"""Firebase認証との連携。import時には初期化しない。"""

import os
from threading import Lock

import firebase_admin
from firebase_admin import auth


class InvalidTokenError(Exception):
    """認証トークンが無効。"""


class AuthServiceUnavailableError(Exception):
    """認証サービスの設定・通信に問題がある。"""


_app: firebase_admin.App | None = None
_app_lock = Lock()


def get_firebase_app() -> firebase_admin.App:
    """必要になったときだけFirebaseを初期化する。"""
    global _app

    project_id = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
    if not project_id or os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        raise AuthServiceUnavailableError("Authentication service unavailable")

    with _app_lock:
        if _app is None:
            try:
                _app = firebase_admin.initialize_app(
                    options={"projectId": project_id},
                    name="porori-auth",
                )
            except Exception:
                raise AuthServiceUnavailableError(
                    "Authentication service unavailable"
                ) from None

        return _app


def verify_token(token: str, *, check_revoked: bool) -> str:
    """トークンを検証し、Firebase UIDだけを返す。"""
    if not isinstance(token, str) or not token.strip():
        raise InvalidTokenError("Invalid authentication token")

    firebase_app = get_firebase_app()

    try:
        decoded = auth.verify_id_token(
            token,
            app=firebase_app,
            check_revoked=check_revoked,
        )
    except (
        auth.InvalidIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
        ValueError,
    ):
        raise InvalidTokenError("Invalid authentication token") from None
    except Exception:
        raise AuthServiceUnavailableError(
            "Authentication service unavailable"
        ) from None

    uid = decoded.get("uid") if isinstance(decoded, dict) else None
    if not isinstance(uid, str) or not uid.strip() or len(uid) > 128:
        raise InvalidTokenError("Invalid authentication token")

    return uid
