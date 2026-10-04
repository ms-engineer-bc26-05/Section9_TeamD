"""ORMの共通基盤。DB接続はimport時に行わない。"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import config
from collections.abc import AsyncIterator


NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_database_url(value: str) -> URL:
    """接続情報を表示せず、SQLAlchemy用のURLへ変換する。"""
    if not value.strip():
        raise ValueError("DB接続先が設定されていません。")

    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("DB接続先の形式が不正です。") from None

    if url.drivername not in (
        "postgres",
        "postgresql",
        "postgresql+asyncpg",
    ):
        raise ValueError("DB接続先はPostgreSQLを指定してください。")

    return url.set(drivername="postgresql+asyncpg")


_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """最初に必要になったときだけEngineを作り、再利用する。"""
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            make_database_url(config.DATABASE_URL),
            echo=False,
            hide_parameters=True,
            pool_pre_ping=True,
            connect_args={
                "timeout": config.CONNECT_TIMEOUT_SECONDS,
            },
        )

    return _engine


async def dispose_engine() -> None:
    """アプリ終了時に、Engineが管理する接続を片付ける。"""
    global _engine

    if _engine is None:
        return

    await _engine.dispose()
    _engine = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """共通Engineを使い、新しいセッションを作るための窓口を返す。"""
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """セッションを渡し、処理終了後に閉じる。自動コミットはしない。"""
    factory = get_session_factory()

    async with factory() as session:
        yield session
