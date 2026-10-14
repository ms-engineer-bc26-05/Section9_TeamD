"""create plans, user_entitlements and payments tables

Revision ID: e193a45a308a
Revises: b7e2c4a91d3f
Create Date: 2026-10-12 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e193a45a308a'
down_revision: Union[str, Sequence[str], None] = 'b7e2c4a91d3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the plans, user_entitlements and payments tables (DB設計・#59)."""
    op.create_table(
        "plans",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("stripe_price_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
        sa.UniqueConstraint("code", name=op.f("uq_plans_code")),
        sa.UniqueConstraint("stripe_price_id", name=op.f("uq_plans_stripe_price_id")),
    )
    # API設計6.8.1の plan_code。id は環境ごとに変わる（APIでは受け渡さない）
    op.execute(
        "INSERT INTO plans (code, name) VALUES ('free', '無料プラン'), ('premium', '有料プラン')"
    )

    op.create_table(
        "user_entitlements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_entitlements")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_entitlements_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name=op.f("fk_user_entitlements_plan_id_plans"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended')",
            name=op.f("ck_user_entitlements_status_allowed"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name=op.f("ck_user_entitlements_valid_period"),
        ),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("stripe_checkout_session_id", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("checkout_request", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entitlement_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_payments_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name=op.f("fk_payments_plan_id_plans"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "stripe_checkout_session_id",
            name=op.f("uq_payments_stripe_checkout_session_id"),
        ),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payments_idempotency_key")),
        sa.CheckConstraint(
            "status IN ('creating', 'pending', 'paid', 'expired', 'failed')",
            name=op.f("ck_payments_status_allowed"),
        ),
        sa.CheckConstraint(
            "amount_minor >= 0",
            name=op.f("ck_payments_amount_minor_not_negative"),
        ),
        sa.CheckConstraint(
            "status <> 'paid' OR (stripe_checkout_session_id IS NOT NULL AND verified_at IS NOT NULL)",
            name=op.f("ck_payments_paid_has_session_and_verified_at"),
        ),
        sa.CheckConstraint(
            "entitlement_applied_at IS NULL OR status = 'paid'",
            name=op.f("ck_payments_entitlement_applied_only_when_paid"),
        ),
    )
    # 同じユーザーの未決済（creating・pending）は1件まで
    op.create_index(
        "uq_payments_user_id_unfinished",
        "payments",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('creating', 'pending')"),
    )


def downgrade() -> None:
    """Drop the payments, user_entitlements and plans tables."""
    op.drop_index("uq_payments_user_id_unfinished", table_name="payments")
    op.drop_table("payments")
    op.drop_table("user_entitlements")
    op.drop_table("plans")
