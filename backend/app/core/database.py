"""ORMの共通基盤。DB接続はimport時に行わない。"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


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