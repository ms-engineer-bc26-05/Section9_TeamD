"""ユーザーテーブル定義のテスト。実DBには接続しない。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    UniqueConstraint,
    Uuid,
)

from app.core.database import Base
from app.features.users.models import User


def test_user_has_only_designed_columns():
    table = User.__table__

    assert table.name == "users"
    assert set(table.columns.keys()) == {
        "id",
        "firebase_uid",
        "status",
        "has_seen_notice",
        "created_at",
    }
    assert all(not column.nullable for column in table.columns)


def test_user_uses_shared_metadata():
    assert User.__table__.metadata is Base.metadata


def test_user_id_is_uuid_primary_key():
    table = User.__table__

    assert list(table.primary_key.columns.keys()) == ["id"]
    assert table.primary_key.name == "pk_users"
    assert isinstance(table.c.id.type, Uuid)
    assert table.c.id.type.as_uuid is True


def test_firebase_uid_has_unique_constraint():
    table = User.__table__
    constraints = [
        item
        for item in table.constraints
        if isinstance(item, UniqueConstraint)
    ]

    assert len(constraints) == 1
    constraint = constraints[0]
    assert list(constraint.columns.keys()) == ["firebase_uid"]
    assert constraint.name == "uq_users_firebase_uid"
    assert table.c.firebase_uid.type.length == 128


def test_status_has_allowed_values_constraint():
    constraints = [
        item
        for item in User.__table__.constraints
        if isinstance(item, CheckConstraint)
    ]

    assert len(constraints) == 1
    constraint = constraints[0]
    assert constraint.name == "ck_users_status_allowed"
    assert str(constraint.sqltext) == "status IN ('active', 'deleting')"


def test_user_defaults_and_column_types():
    columns = User.__table__.c

    assert columns.id.default is not None
    assert columns.id.default.is_callable

    assert columns.status.type.length == 20
    assert columns.status.server_default.arg == "active"

    assert isinstance(columns.has_seen_notice.type, Boolean)
    assert str(columns.has_seen_notice.server_default.arg) == "false"

    assert isinstance(columns.created_at.type, DateTime)
    assert columns.created_at.type.timezone is True
    assert str(columns.created_at.server_default.arg) == "now()"
