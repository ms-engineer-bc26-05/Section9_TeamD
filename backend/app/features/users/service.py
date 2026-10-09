"""内部ユーザーを扱う処理。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.users.models import User

from sqlalchemy.dialects.postgresql import insert

from uuid import UUID

from app.core.exceptions import (
    AccountDeletingError,
    AuthenticationRequiredError,
)

async def get_user_by_firebase_uid(
    session: AsyncSession,
    firebase_uid: str,
) -> User | None:
    """検証済みFirebase UIDで検索する。作成・更新は行わない。"""
    statement = select(User).where(User.firebase_uid == firebase_uid)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    firebase_uid: str,
) -> tuple[User, bool]:
    """検証済みUIDで作成・取得する。保存の確定は呼び出し元で行う。"""
    statement = (
        insert(User)
        .values(firebase_uid=firebase_uid)
        .on_conflict_do_nothing(index_elements=[User.firebase_uid])
        .returning(User)
    )
    result = await session.execute(statement)
    created_user = result.scalar_one_or_none()

    if created_user is not None:
        return created_user, True

    statement = (
        select(User)
        .where(User.firebase_uid == firebase_uid)
        .with_for_update()
    )
    result = await session.execute(statement)
    existing_user = result.scalar_one_or_none()

    if existing_user is None:
        raise RuntimeError("User unavailable after registration conflict")

    return existing_user, False


async def mark_notice_seen(
    session: AsyncSession,
    user_id: UUID,
) -> User:
    """本人の注意確認状態を更新する。保存の確定は呼び出し元で行う。"""
    statement = (
        select(User)
        .where(User.id == user_id)
        .with_for_update()
    )
    result = await session.execute(statement)
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationRequiredError("Authentication required")
    if user.status == "deleting":
        raise AccountDeletingError("Account is being deleted")
    if user.status != "active":
        raise RuntimeError("Unexpected account status")

    user.has_seen_notice = True
    return user
