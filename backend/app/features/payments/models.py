"""プラン・利用権限・決済のテーブル定義（DB設計 plans・user_entitlements・payments。#59）。

#59の結論で、3つの表はF-05で作る。user_entitlements の判定・付与は plans/public.py の関数で行う（#95）。

- plans の上限値（相談回数・保存件数・集計期間）は、#57で環境変数の設定値にしたため列を作らない
  （使わない列が NULL のまま残ると、#57で決めた「NULL は無制限」と読み違えるため）
- payments.checkout_request は、Stripeへ送るSession作成の内容（#59。repository.CheckoutRequest）。
  秘密情報・相談内容は含めない
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlanRow(Base):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Price IDは今はサーバー設定（STRIPE_PRICE_ID_PREMIUM）で管理する。DBへ移すかは#59で決める
    stripe_price_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserEntitlementRow(Base):
    __tablename__ = "user_entitlements"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended')", name="status_allowed"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from", name="valid_period"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaymentRow(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('creating', 'pending', 'paid', 'expired', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint("amount_minor >= 0", name="amount_minor_not_negative"),
        CheckConstraint(
            "status <> 'paid' OR (stripe_checkout_session_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="paid_has_session_and_verified_at",
        ),
        CheckConstraint(
            "entitlement_applied_at IS NULL OR status = 'paid'",
            name="entitlement_applied_only_when_paid",
        ),
        # 同じユーザーの未決済（creating・pending）は1件まで（ユーザー行のロックに加えた最後の守り）
        Index(
            "uq_payments_user_id_unfinished",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('creating', 'pending')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True
    )
    idempotency_key: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    checkout_request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entitlement_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
