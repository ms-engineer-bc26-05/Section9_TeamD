"""DB共通基盤のテスト。実際のDBには接続しない。"""
import pytest

from sqlalchemy import (
    CheckConstraint,
    Column,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    ForeignKey,
    Index,
)

from app.core.database import Base, make_database_url

from unittest.mock import AsyncMock, Mock

from app.core import database

import subprocess
import sys


def test_composite_unique_name_contains_all_columns():
    metadata = MetaData(
        naming_convention=Base.metadata.naming_convention
    )
    table = Table(
        "approved_memos",
        metadata,
        Column("user_id", Uuid(), nullable=False),
        Column("source_consultation_id", Uuid(), nullable=False),
        UniqueConstraint("user_id", "source_consultation_id"),
    )

    constraint = next(
        item
        for item in table.constraints
        if isinstance(item, UniqueConstraint)
    )

    assert constraint.name == (
        "uq_approved_memos_user_id_source_consultation_id"
    )


def test_primary_key_name_contains_table_name():
    metadata = MetaData(
        naming_convention=Base.metadata.naming_convention
    )
    table = Table(
        "users",
        metadata,
        Column("id", Uuid(), primary_key=True),
    )

    assert table.primary_key.name == "pk_users"


def test_check_constraint_name_contains_explicit_name():
    metadata = MetaData(
        naming_convention=Base.metadata.naming_convention
    )
    condition = CheckConstraint(
        "status IN ('active', 'deleting')",
        name="status_allowed",
    )
    Table(
        "users",
        metadata,
        Column("status", String(20), nullable=False),
        condition,
    )

    assert condition.name == "ck_users_status_allowed"


def test_foreign_key_name_contains_referenced_table():
    metadata = MetaData(
        naming_convention=Base.metadata.naming_convention
    )
    Table(
        "users",
        metadata,
        Column("id", Uuid(), primary_key=True),
    )
    memos = Table(
        "approved_memos",
        metadata,
        Column("user_id", Uuid(), ForeignKey("users.id")),
    )

    constraint = next(iter(memos.foreign_key_constraints))

    assert constraint.name == "fk_approved_memos_user_id_users"


def test_index_name_contains_table_and_column():
    metadata = MetaData(
        naming_convention=Base.metadata.naming_convention
    )
    table = Table(
        "approved_memos",
        metadata,
        Column("user_id", Uuid()),
    )
    index = Index(None, table.c.user_id)

    assert index.name == "ix_approved_memos_user_id"


def test_database_url_changes_only_driver():
    original = "postgresql://dummy:dummy%40pass@db:5432/test_db"

    url = make_database_url(original)

    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "dummy"
    assert url.password == "dummy@pass"
    assert url.host == "db"
    assert url.port == 5432
    assert url.database == "test_db"
    assert original == "postgresql://dummy:dummy%40pass@db:5432/test_db"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "INVALID_DUMMY_MARKER",
        "postgresql://dummy:dummy@db:INVALID_DUMMY_MARKER/test_db",
        "mysql://dummy:dummy@db/test_db",
    ],
)
def test_database_url_rejects_invalid_input_without_echoing_it(value):
    with pytest.raises(ValueError) as caught:
        make_database_url(value)

    assert str(caught.value) in {
        "DB接続先が設定されていません。",
        "DB接続先の形式が不正です。",
        "DB接続先はPostgreSQLを指定してください。",
    }
    assert "INVALID_DUMMY_MARKER" not in str(caught.value)
    assert "dummy" not in str(caught.value)


def test_get_engine_creates_once_and_reuses(monkeypatch):
    fake_engine = Mock()
    create_engine = Mock(return_value=fake_engine)

    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(
        database.config,
        "DATABASE_URL",
        "postgresql://dummy:dummy@db/test_db",
    )
    monkeypatch.setattr(database.config, "CONNECT_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(database, "create_async_engine", create_engine)

    assert create_engine.call_count == 0

    first = database.get_engine()
    second = database.get_engine()

    assert first is fake_engine
    assert second is first
    create_engine.assert_called_once_with(
        database.make_database_url("postgresql://dummy:dummy@db/test_db"),
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
        connect_args={"timeout": 3},
    )


async def test_dispose_engine_closes_and_resets(monkeypatch):
    fake_engine = Mock()
    fake_engine.dispose = AsyncMock()
    monkeypatch.setattr(database, "_engine", fake_engine)

    await database.dispose_engine()

    fake_engine.dispose.assert_awaited_once()
    assert database._engine is None

    await database.dispose_engine()

    fake_engine.dispose.assert_awaited_once()


async def test_dispose_engine_before_creation_does_nothing(monkeypatch):
    create_engine = Mock()
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "create_async_engine", create_engine)

    await database.dispose_engine()

    create_engine.assert_not_called()
    assert database._engine is None


def test_import_does_not_create_engine_or_require_database_url():
    code = """
from unittest.mock import patch
from app.core import config

config.DATABASE_URL = ""

with patch(
    "sqlalchemy.ext.asyncio.create_async_engine",
    side_effect=AssertionError("Engine must not be created during import"),
) as create_engine:
    from app.core import database

    create_engine.assert_not_called()
    assert database._engine is None
"""
    subprocess.run([sys.executable, "-c", code], check=True)
