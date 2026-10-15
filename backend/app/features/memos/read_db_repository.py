"""Owner-scoped queries and committed deletion, separate from the save repository."""

from uuid import UUID

from sqlalchemy import delete, select, tuple_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database_errors import is_database_connection_error
from app.core.exceptions import DatabaseUnavailableError
from app.features.memos.exceptions import MemoDatabaseError
from app.features.memos.models import ApprovedMemo
from app.features.memos.read_cursor import MemoCursor
from app.features.memos.repository import StoredMemo, UserNotActive, UserNotFound
from app.features.users.models import User


def _stored(row: ApprovedMemo) -> StoredMemo:
    return StoredMemo(**{name: getattr(row, name) for name in StoredMemo.__dataclass_fields__})


def _translate(error: Exception) -> Exception:
    if is_database_connection_error(error):
        return DatabaseUnavailableError("Database connection unavailable")
    return MemoDatabaseError("Memo database operation failed")


class SqlAlchemyMemoReadRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_owned(self, user_id: UUID, memo_id: UUID) -> StoredMemo | None:
        statement = select(ApprovedMemo).where(
            ApprovedMemo.user_id == user_id, ApprovedMemo.id == memo_id
        )
        try:
            async with self._session_factory() as session:
                row = (await session.execute(statement)).scalar_one_or_none()
                return _stored(row) if row is not None else None
        except (SQLAlchemyError, ConnectionError, OSError) as error:
            raise _translate(error) from None

    async def list_owned(
        self, user_id: UUID, cursor: MemoCursor | None, limit: int
    ) -> list[StoredMemo]:
        statement = select(ApprovedMemo).where(ApprovedMemo.user_id == user_id)
        if cursor is not None:
            statement = statement.where(
                tuple_(ApprovedMemo.created_at, ApprovedMemo.id)
                < tuple_(cursor.created_at, cursor.memo_id)
            )
        statement = statement.order_by(ApprovedMemo.created_at.desc(), ApprovedMemo.id.desc()).limit(limit)
        try:
            async with self._session_factory() as session:
                return [_stored(row) for row in (await session.execute(statement)).scalars().all()]
        except (SQLAlchemyError, ConnectionError, OSError) as error:
            raise _translate(error) from None

    async def delete_owned(self, user_id: UUID, memo_id: UUID) -> bool:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    status = (await session.execute(
                        select(User.status).where(User.id == user_id).with_for_update()
                    )).scalar_one_or_none()
                    if status is None:
                        raise UserNotFound
                    if status != "active":
                        raise UserNotActive
                    result = await session.execute(delete(ApprovedMemo).where(
                        ApprovedMemo.user_id == user_id, ApprovedMemo.id == memo_id
                    ).returning(ApprovedMemo.id))
                    deleted = result.scalar_one_or_none() is not None
                # Returning outside begin() ensures commit failures cannot become 204.
                return deleted
        except (SQLAlchemyError, ConnectionError, OSError) as error:
            raise _translate(error) from None
