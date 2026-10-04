"""内部ユーザーを扱う処理。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.users.models import User


async def get_user_by_firebase_uid(
    session: AsyncSession,
    firebase_uid: str,
) -> User | None:
    """検証済みFirebase UIDで検索する。作成・更新は行わない。"""
    statement = select(User).where(User.firebase_uid == firebase_uid)
    result = await session.execute(statement)
    return result.scalar_one_or_none()
