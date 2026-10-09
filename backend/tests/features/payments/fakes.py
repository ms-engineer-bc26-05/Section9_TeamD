"""テスト用のメモリ上のPaymentRepositoryと、Stripeの偽物。DB・Stripeを使わずにServiceのテストを書くために使う。

InMemoryPaymentRepository：
- transaction() はブロックを正常に抜けたときだけ反映（commit）し、例外なら破棄（rollback）する
- lock_user はユーザーごとの asyncio.Lock を取り、トランザクション終了まで保持する
  （未設定のユーザーは active、None は不在）
- 「同じユーザーの creating・pending は1件まで」を insert と commit で確認する（部分UNIQUE索引の再現）
- 検索・更新・commit では await asyncio.sleep(0) で処理を譲り、実DBの通信待ちを再現する

FakeStripe：
- 同じ idempotency key・同じ内容なら、作成済みのSessionを返す（Stripeの動きの再現）
- 同じ idempotency key の作成がまだ終わっていないときは StripeIdempotencyInProgress を送出する
- 同じ idempotency key で内容が違うときは StripeIdempotencyMismatch を送出する
- create_gate を設定すると、作成の途中でそのイベントを待つ（同時リクエストの再現用）
- create_errors に例外を入れると、次の作成でその例外を送出する（Stripeには作成されない）
- lose_next_response を True にすると、次の作成ではStripe側に作成したうえで StripeUnavailable を送出する
  （作成されたのに、タイムアウトで応答を受け取れなかった場合の再現）
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import AsyncIterator
from uuid import UUID, uuid4

from app.features.payments.repository import (
    UNFINISHED_STATUSES,
    DuplicateUnfinishedPayment,
    NewPayment,
    Plan,
    StoredPayment,
    UserNotActive,
    UserNotFound,
)
from app.integrations.stripe.client import (
    CheckoutSession,
    StripeIdempotencyInProgress,
    StripeIdempotencyMismatch,
    StripePrice,
    StripeSessionNotFound,
    StripeUnavailable,
)

PREMIUM_PLAN = Plan(id=UUID("00000000-0000-0000-0000-00000000c001"), code="premium", is_active=True)


class InMemoryPaymentRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, StoredPayment] = {}
        self.plans: dict[str, Plan] = {PREMIUM_PLAN.code: PREMIUM_PLAN}
        # 現在有効な有料の利用権限を持つユーザー
        self.paid_users: set[UUID] = set()
        self.user_statuses: dict[UUID, str | None] = {}
        self._user_locks: dict[UUID, asyncio.Lock] = {}

    async def find_unfinished(self, user_id: UUID) -> StoredPayment | None:
        await asyncio.sleep(0)
        return _find_unfinished(self.rows.values(), user_id)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["_InMemoryTransaction"]:
        tx = _InMemoryTransaction(self)
        try:
            yield tx
            await asyncio.sleep(0)
            merged = {**self.rows, **tx.pending}
            for row in tx.pending.values():
                if _count_unfinished(merged.values(), row.user_id) > 1:
                    raise DuplicateUnfinishedPayment
            self.rows = merged
        finally:
            tx.release_locks()

    def user_lock(self, user_id: UUID) -> asyncio.Lock:
        return self._user_locks.setdefault(user_id, asyncio.Lock())


class _InMemoryTransaction:
    def __init__(self, repo: InMemoryPaymentRepository) -> None:
        self._repo = repo
        self.pending: dict[UUID, StoredPayment] = {}
        self._held: list[asyncio.Lock] = []

    async def lock_user(self, user_id: UUID, *, require_active: bool = True) -> str:
        lock = self._repo.user_lock(user_id)
        if lock not in self._held:
            await lock.acquire()
            self._held.append(lock)
        status = self._repo.user_statuses.get(user_id, "active")
        if status is None:
            raise UserNotFound
        if require_active and status != "active":
            raise UserNotActive
        return status

    async def has_paid_entitlement(self, user_id: UUID, now: datetime) -> bool:
        await asyncio.sleep(0)
        return user_id in self._repo.paid_users

    async def find_plan(self, code: str) -> Plan | None:
        await asyncio.sleep(0)
        return self._repo.plans.get(code)

    async def find_unfinished(self, user_id: UUID) -> StoredPayment | None:
        await asyncio.sleep(0)
        return _find_unfinished(self._rows().values(), user_id)

    async def insert(self, payment: NewPayment) -> StoredPayment:
        await asyncio.sleep(0)
        if _find_unfinished(self._rows().values(), payment.user_id) is not None:
            raise DuplicateUnfinishedPayment
        stored = StoredPayment(
            id=payment.id,
            user_id=payment.user_id,
            plan_id=payment.plan_id,
            stripe_checkout_session_id=None,
            idempotency_key=payment.idempotency_key,
            status="creating",
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            created_at=datetime.now(UTC),
        )
        self.pending[stored.id] = stored
        return stored

    async def lock_payment(self, payment_id: UUID) -> StoredPayment | None:
        await asyncio.sleep(0)
        return self._rows().get(payment_id)

    async def mark_pending(self, payment_id: UUID, session_id: str) -> None:
        row = self._rows()[payment_id]
        assert row.status == "creating"
        self.pending[payment_id] = replace(
            row, status="pending", stripe_checkout_session_id=session_id
        )

    async def mark_expired(self, payment_id: UUID, verified_at: datetime) -> None:
        self.pending[payment_id] = replace(self._rows()[payment_id], status="expired")

    async def mark_failed(self, payment_id: UUID) -> None:
        self.pending[payment_id] = replace(self._rows()[payment_id], status="failed")

    def _rows(self) -> dict[UUID, StoredPayment]:
        return {**self._repo.rows, **self.pending}

    def release_locks(self) -> None:
        for lock in reversed(self._held):
            lock.release()
        self._held.clear()


def _find_unfinished(rows, user_id: UUID) -> StoredPayment | None:
    for row in rows:
        if row.user_id == user_id and row.status in UNFINISHED_STATUSES:
            return row
    return None


def _count_unfinished(rows, user_id: UUID) -> int:
    return sum(1 for row in rows if row.user_id == user_id and row.status in UNFINISHED_STATUSES)


class FakeStripe:
    def __init__(self) -> None:
        self.price = StripePrice(
            id="price_dummy", active=True, type="one_time", unit_amount=300, currency="jpy"
        )
        self.sessions: dict[str, CheckoutSession] = {}
        self.create_calls: list[dict] = []
        self.create_errors: list[Exception] = []
        self.create_gate: asyncio.Event | None = None
        self.lose_next_response = False
        # idempotency key → (送った内容, 作成したSession ID。作成中は None)
        self._by_key: dict[str, tuple[dict, str | None]] = {}

    async def retrieve_price(self, price_id: str) -> StripePrice:
        await asyncio.sleep(0)
        return self.price

    async def create_checkout_session(self, *, idempotency_key: str, **params) -> CheckoutSession:
        self.create_calls.append({"idempotency_key": idempotency_key, **params})
        await asyncio.sleep(0)
        if self.create_errors:
            raise self.create_errors.pop(0)
        if idempotency_key in self._by_key:
            sent, session_id = self._by_key[idempotency_key]
            if sent != params:
                raise StripeIdempotencyMismatch("架空")
            if session_id is None:
                raise StripeIdempotencyInProgress("架空")
            return self.sessions[session_id]

        self._by_key[idempotency_key] = (params, None)
        if self.create_gate is not None:
            await self.create_gate.wait()
        session_id = f"cs_test_{uuid4().hex}"
        session = CheckoutSession(
            id=session_id,
            url=f"https://checkout.stripe.com/c/pay/{session_id}",
            status="open",
            payment_status="unpaid",
            amount_total=self.price.unit_amount,
            currency=self.price.currency,
            client_reference_id=params["client_reference_id"],
            metadata=dict(params["metadata"]),
        )
        self.sessions[session_id] = session
        self._by_key[idempotency_key] = (params, session_id)
        if self.lose_next_response:
            self.lose_next_response = False
            raise StripeUnavailable("架空")
        return session

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutSession:
        await asyncio.sleep(0)
        if session_id not in self.sessions:
            raise StripeSessionNotFound("架空")
        return self.sessions[session_id]

    @property
    def created_session_count(self) -> int:
        return len(self.sessions)

    def set_session_status(self, session_id: str, status: str) -> None:
        session = self.sessions[session_id]
        url = session.url if status == "open" else None
        self.sessions[session_id] = replace(session, status=status, url=url)
