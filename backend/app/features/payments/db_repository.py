"""PaymentRepository のDB実装（SQLAlchemy）。契約は repository.py を正とする。

- 検索と transaction() は、それぞれ新しいセッションを使う（memos/db_repository.py と同じ）
- 「同じユーザーの creating・pending は1件まで」の部分UNIQUE索引に違反した場合は、
  flush・commit のどちらで起きても DuplicateUnfinishedPayment へ変換する
- 接続障害は DatabaseUnavailableError（503）、それ以外のDBの例外は PaymentDatabaseError（500）へ
  包み直す。DBの例外のメッセージはSQLのパラメータ（Session IDなど）を含みうるため、from None で捨てる
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database_errors import is_database_connection_error
from app.core.exceptions import DatabaseUnavailableError
from app.features.payments.exceptions import PaymentDatabaseError
from app.features.payments.models import PaymentRow, PlanRow
from app.features.payments.repository import (
    UNFINISHED_STATUSES,
    CheckoutRequest,
    DuplicateUnfinishedPayment,
    NewPayment,
    Plan,
    StoredPayment,
    UserNotActive,
    UserNotFound,
)
from app.features.plans.public import PlanCode, get_current_plan, grant_paid_entitlement
from app.features.users.models import User

_UNFINISHED_INDEX = "uq_payments_user_id_unfinished"


def _request_to_json(request: CheckoutRequest) -> dict[str, Any]:
    return {
        "price_id": request.price_id,
        "expires_at": request.expires_at.isoformat(),
        "success_url": request.success_url,
        "cancel_url": request.cancel_url,
        "client_reference_id": request.client_reference_id,
        "metadata": dict(request.metadata),
    }


def _request_from_json(data: dict[str, Any]) -> CheckoutRequest:
    return CheckoutRequest(
        price_id=data["price_id"],
        expires_at=datetime.fromisoformat(data["expires_at"]),
        success_url=data["success_url"],
        cancel_url=data["cancel_url"],
        client_reference_id=data["client_reference_id"],
        metadata=dict(data["metadata"]),
    )


def _to_stored(row: PaymentRow) -> StoredPayment:
    return StoredPayment(
        id=row.id,
        user_id=row.user_id,
        plan_id=row.plan_id,
        stripe_checkout_session_id=row.stripe_checkout_session_id,
        idempotency_key=row.idempotency_key,
        status=row.status,
        amount_minor=row.amount_minor,
        currency=row.currency,
        checkout_request=_request_from_json(row.checkout_request),
        created_at=row.created_at,
        verified_at=row.verified_at,
        entitlement_applied_at=row.entitlement_applied_at,
    )


def _violated_constraint(error: IntegrityError) -> str | None:
    # asyncpg の元の例外（UniqueViolationError など）が制約名を持つ
    return getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)


def _translate(error: SQLAlchemyError) -> Exception:
    if isinstance(error, IntegrityError) and _violated_constraint(error) == _UNFINISHED_INDEX:
        return DuplicateUnfinishedPayment()
    if is_database_connection_error(error):
        return DatabaseUnavailableError("Database connection unavailable")
    return PaymentDatabaseError("Payment database operation failed")


async def _find_one(session: AsyncSession, *conditions) -> StoredPayment | None:
    row = (await session.execute(select(PaymentRow).where(*conditions))).scalar_one_or_none()
    return _to_stored(row) if row is not None else None


def _unfinished_of(user_id: UUID):
    return (PaymentRow.user_id == user_id, PaymentRow.status.in_(UNFINISHED_STATUSES))


class _SqlAlchemyPaymentTransaction:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user(self, user_id: UUID, *, require_active: bool = True) -> str:
        statement = select(User.status).where(User.id == user_id).with_for_update()
        status = (await self._session.execute(statement)).scalar_one_or_none()
        if status is None:
            raise UserNotFound
        if require_active and status != "active":
            raise UserNotActive
        return status

    async def current_plan(self, user_id: UUID, now: datetime) -> PlanCode:
        # GET /usage と同じ判定を、ユーザー行のロックと同じトランザクションで行う（#95）
        return await get_current_plan(self._session, user_id, now)

    async def find_plan(self, code: str) -> Plan | None:
        row = (
            await self._session.execute(select(PlanRow).where(PlanRow.code == code))
        ).scalar_one_or_none()
        return Plan(id=row.id, code=row.code, is_active=row.is_active) if row is not None else None

    async def find_unfinished(self, user_id: UUID) -> StoredPayment | None:
        return await _find_one(self._session, *_unfinished_of(user_id))

    async def insert(self, payment: NewPayment) -> StoredPayment:
        statement = (
            insert(PaymentRow)
            .values(
                id=payment.id,
                user_id=payment.user_id,
                plan_id=payment.plan_id,
                idempotency_key=payment.idempotency_key,
                status="creating",
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                checkout_request=_request_to_json(payment.checkout_request),
            )
            .returning(PaymentRow.created_at)
        )
        try:
            created_at = (await self._session.execute(statement)).scalar_one()
        except SQLAlchemyError as error:
            raise _translate(error) from None
        return StoredPayment(
            id=payment.id,
            user_id=payment.user_id,
            plan_id=payment.plan_id,
            stripe_checkout_session_id=None,
            idempotency_key=payment.idempotency_key,
            status="creating",
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            checkout_request=payment.checkout_request,
            created_at=created_at,
        )

    async def lock_payment(self, payment_id: UUID) -> StoredPayment | None:
        statement = select(PaymentRow).where(PaymentRow.id == payment_id).with_for_update()
        row = (await self._session.execute(statement)).scalar_one_or_none()
        return _to_stored(row) if row is not None else None

    async def mark_pending(self, payment_id: UUID, session_id: str) -> None:
        await self._update(
            payment_id, "creating", status="pending", stripe_checkout_session_id=session_id
        )

    async def mark_expired(self, payment_id: UUID, verified_at: datetime) -> None:
        await self._update(payment_id, "pending", status="expired", verified_at=verified_at)

    async def mark_failed(self, payment_id: UUID) -> None:
        await self._update(payment_id, "pending", status="failed")

    async def mark_paid(self, payment_id: UUID, verified_at: datetime) -> None:
        await self._update(payment_id, "pending", status="paid", verified_at=verified_at)

    async def grant_entitlement(self, user_id: UUID, plan_id: UUID, now: datetime) -> None:
        await grant_paid_entitlement(self._session, user_id, plan_id, now)

    async def mark_entitlement_applied(self, payment_id: UUID, applied_at: datetime) -> None:
        await self._update(payment_id, "paid", entitlement_applied_at=applied_at)

    async def _update(self, payment_id: UUID, expected: str, **values) -> None:
        """expected の状態の行だけを更新する（呼び出し側は行をロックし、状態を確認済み）"""
        statement = (
            update(PaymentRow)
            .where(and_(PaymentRow.id == payment_id, PaymentRow.status == expected))
            .values(**values)
        )
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as error:
            raise _translate(error) from None
        if result.rowcount != 1:
            # ロックした行の状態とずれている。呼び出し側の誤りのため、成功扱いにしない
            raise PaymentDatabaseError("Payment row was not in the expected state")


class SqlAlchemyPaymentRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def find_unfinished(self, user_id: UUID) -> StoredPayment | None:
        return await self._find(*_unfinished_of(user_id))

    async def find_by_session_id(self, session_id: str) -> StoredPayment | None:
        return await self._find(PaymentRow.stripe_checkout_session_id == session_id)

    async def find_confirmable(self, user_id: UUID) -> StoredPayment | None:
        pending = await self._find(PaymentRow.user_id == user_id, PaymentRow.status == "pending")
        if pending is not None:
            return pending
        return await self._find(
            PaymentRow.user_id == user_id,
            PaymentRow.status == "paid",
            PaymentRow.entitlement_applied_at.is_(None),
        )

    async def _find(self, *conditions) -> StoredPayment | None:
        try:
            async with self._session_factory() as session:
                # paid だが未反映の行は通常1件まで。複数あっても古い順に1件ずつ確認する
                statement = (
                    select(PaymentRow)
                    .where(*conditions)
                    .order_by(PaymentRow.created_at, PaymentRow.id)
                    .limit(1)
                )
                row = (await session.execute(statement)).scalar_one_or_none()
                return _to_stored(row) if row is not None else None
        except SQLAlchemyError as error:
            raise _translate(error) from None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[_SqlAlchemyPaymentTransaction]:
        try:
            async with self._session_factory() as session:
                # 正常に抜けたら commit、例外なら rollback する
                async with session.begin():
                    yield _SqlAlchemyPaymentTransaction(session)
        except SQLAlchemyError as error:
            raise _translate(error) from None
