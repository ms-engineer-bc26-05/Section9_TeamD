"""プラン・利用権限・決済のテーブル定義のテスト。実DBには接続しない。

制約が実際に効くこと（部分UNIQUE索引・CHECK・外部キー）は、実DBのRepositoryのテストで確認する。
"""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint

from app.core.database import Base
from app.features.payments.models import PaymentRow, PlanRow, UserEntitlementRow


def checks(table) -> dict[str, str]:
    return {
        item.name: str(item.sqltext)
        for item in table.constraints
        if isinstance(item, CheckConstraint)
    }


def foreign_keys(table) -> dict[str, tuple[str, str | None]]:
    return {
        item.name: (item.elements[0].target_fullname, item.ondelete)
        for item in table.constraints
        if isinstance(item, ForeignKeyConstraint)
    }


def unique_columns(table) -> set[tuple[str, ...]]:
    return {
        tuple(item.columns.keys())
        for item in table.constraints
        if isinstance(item, UniqueConstraint)
    }


def test_tables_use_shared_metadata():
    for model in (PlanRow, UserEntitlementRow, PaymentRow):
        assert model.__table__.metadata is Base.metadata


# --- plans ----------------------------------------------------------------------


def test_plans_has_no_limit_columns():
    """上限値は#57で設定値にしたため、DBには持たない（NULL を無制限と読み違えないため）"""
    assert set(PlanRow.__table__.columns.keys()) == {
        "id",
        "code",
        "name",
        "stripe_price_id",
        "is_active",
        "created_at",
    }


def test_plans_code_and_price_id_are_unique():
    assert unique_columns(PlanRow.__table__) == {("code",), ("stripe_price_id",)}


# --- user_entitlements ----------------------------------------------------------


def test_user_entitlements_one_row_per_user():
    table = UserEntitlementRow.__table__
    assert list(table.primary_key.columns.keys()) == ["user_id"]


def test_user_entitlements_constraints():
    table = UserEntitlementRow.__table__
    assert foreign_keys(table) == {
        "fk_user_entitlements_user_id_users": ("users.id", "RESTRICT"),
        "fk_user_entitlements_plan_id_plans": ("plans.id", "RESTRICT"),
    }
    assert checks(table) == {
        "ck_user_entitlements_status_allowed": "status IN ('active', 'suspended')",
        "ck_user_entitlements_valid_period": "valid_until IS NULL OR valid_until > valid_from",
    }


# --- payments -------------------------------------------------------------------


def test_payments_columns_and_nullability():
    table = PaymentRow.__table__
    nullable = {name for name, column in table.columns.items() if column.nullable}
    assert nullable == {"stripe_checkout_session_id", "verified_at", "entitlement_applied_at"}
    assert "checkout_request" in table.columns


def test_payments_constraints():
    table = PaymentRow.__table__
    assert foreign_keys(table) == {
        "fk_payments_user_id_users": ("users.id", "RESTRICT"),
        "fk_payments_plan_id_plans": ("plans.id", "RESTRICT"),
    }
    assert unique_columns(table) == {("stripe_checkout_session_id",), ("idempotency_key",)}
    assert set(checks(table)) == {
        "ck_payments_status_allowed",
        "ck_payments_amount_minor_not_negative",
        "ck_payments_paid_has_session_and_verified_at",
        "ck_payments_entitlement_applied_only_when_paid",
    }


def test_payments_unfinished_rows_are_unique_per_user():
    [index] = [item for item in PaymentRow.__table__.indexes if isinstance(item, Index)]
    assert index.name == "uq_payments_user_id_unfinished"
    assert index.unique is True
    assert list(index.columns.keys()) == ["user_id"]
    assert str(index.dialect_options["postgresql"]["where"]) == "status IN ('creating', 'pending')"
