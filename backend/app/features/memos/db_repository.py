"""MemoRepository のDB実装（SQLAlchemy）。契約は repository.py を正とする。

- 検索と transaction() は、それぞれ新しいセッションを使う（自動で始まったトランザクションと
  session.begin() が衝突しないようにするため）
- 一意制約違反は、flush・commit のどちらで起きても DuplicateMemo へ変換する
- 接続障害は DatabaseUnavailableError（503）、それ以外のDBの例外は MemoDatabaseError（500）へ
  包み直す。DBの例外のメッセージはSQLのパラメータ（暗号文）を含みうるため、from None で捨てる
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database_errors import is_database_connection_error
from app.core.exceptions import DatabaseUnavailableError
from app.features.memos.exceptions import MemoDatabaseError
from app.features.memos.models import ApprovedMemo
from app.features.memos.repository import (
    DuplicateMemo,
    NewMemo,
    StoredMemo,
    UserNotActive,
    UserNotFound,
)
from app.features.users.models import User

# PostgreSQLの一意制約違反
_UNIQUE_VIOLATION = "23505"


def _to_stored(row: ApprovedMemo) -> StoredMemo:
    return StoredMemo(
        id=row.id,
        user_id=row.user_id,
        source_consultation_id=row.source_consultation_id,
        encrypted_payload=row.encrypted_payload,
        encryption_version=row.encryption_version,
        key_version=row.key_version,
        payload_version=row.payload_version,
        approved_at=row.approved_at,
        save_consented_at=row.save_consented_at,
        created_at=row.created_at,
    )


def _is_unique_violation(error: IntegrityError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)
    return sqlstate == _UNIQUE_VIOLATION


def _translate(error: SQLAlchemyError) -> Exception:
    if isinstance(error, IntegrityError) and _is_unique_violation(error):
        return DuplicateMemo()
    if is_database_connection_error(error):
        return DatabaseUnavailableError("Database connection unavailable")
    return MemoDatabaseError("Memo database operation failed")


async def _find(session: AsyncSession, user_id: UUID, consultation_id: UUID) -> StoredMemo | None:
    statement = select(ApprovedMemo).where(
        ApprovedMemo.user_id == user_id,
        ApprovedMemo.source_consultation_id == consultation_id,
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    return _to_stored(row) if row is not None else None


async def _count(session: AsyncSession, user_id: UUID) -> int:
    statement = (
        select(func.count()).select_from(ApprovedMemo).where(ApprovedMemo.user_id == user_id)
    )
    return (await session.execute(statement)).scalar_one()


class _SqlAlchemyMemoTransaction:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user(self, user_id: UUID) -> None:
        statement = select(User.status).where(User.id == user_id).with_for_update()
        status = (await self._session.execute(statement)).scalar_one_or_none()
        if status is None:
            raise UserNotFound
        if status != "active":
            raise UserNotActive

    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None:
        return await _find(self._session, user_id, consultation_id)

    async def count_by_user(self, user_id: UUID) -> int:
        return await _count(self._session, user_id)

    async def insert(self, memo: NewMemo) -> StoredMemo:
        statement = (
            insert(ApprovedMemo)
            .values(
                id=memo.id,
                user_id=memo.user_id,
                source_consultation_id=memo.source_consultation_id,
                encrypted_payload=memo.encrypted_payload,
                encryption_version=memo.encryption_version,
                key_version=memo.key_version,
                payload_version=memo.payload_version,
                approved_at=memo.approved_at,
                save_consented_at=memo.save_consented_at,
            )
            .returning(ApprovedMemo.created_at)
        )
        try:
            created_at = (await self._session.execute(statement)).scalar_one()
        except SQLAlchemyError as error:
            raise _translate(error) from None
        return StoredMemo(
            id=memo.id,
            user_id=memo.user_id,
            source_consultation_id=memo.source_consultation_id,
            encrypted_payload=memo.encrypted_payload,
            encryption_version=memo.encryption_version,
            key_version=memo.key_version,
            payload_version=memo.payload_version,
            approved_at=memo.approved_at,
            save_consented_at=memo.save_consented_at,
            created_at=created_at,
        )


class SqlAlchemyMemoRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_by_consultation(
        self, user_id: UUID, consultation_id: UUID
    ) -> StoredMemo | None:
        try:
            async with self._session_factory() as session:
                return await _find(session, user_id, consultation_id)
        except SQLAlchemyError as error:
            raise _translate(error) from None

    async def count_by_user(self, user_id: UUID) -> int:
        try:
            async with self._session_factory() as session:
                return await _count(session, user_id)
        except SQLAlchemyError as error:
            raise _translate(error) from None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[_SqlAlchemyMemoTransaction]:
        try:
            async with self._session_factory() as session:
                # 正常に抜けたら commit、例外なら rollback する
                async with session.begin():
                    yield _SqlAlchemyMemoTransaction(session)
        except SQLAlchemyError as error:
            raise _translate(error) from None
