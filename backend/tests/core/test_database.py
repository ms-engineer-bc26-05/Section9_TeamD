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
