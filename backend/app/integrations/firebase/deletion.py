"""Idempotent deletion and explicit absence checks. Never infer absence on failure."""

from firebase_admin import auth

from app.integrations.firebase.client import AuthServiceUnavailableError, get_firebase_app


def delete_user(uid: str) -> None:
    try:
        auth.delete_user(uid, app=get_firebase_app())
    except auth.UserNotFoundError:
        return
    except Exception:
        raise AuthServiceUnavailableError from None


def user_is_absent(uid: str) -> bool:
    try:
        auth.get_user(uid, app=get_firebase_app())
    except auth.UserNotFoundError:
        return True
    except Exception:
        raise AuthServiceUnavailableError from None
    return False
