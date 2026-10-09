"""Checkout Sessionの作成（docs/api-design.md 6.8.6・#59）。

作成の流れ（PR #37で整理した第一候補。Q-34の案は#59で相談中）：
  1. Stripe Priceを取得し、一回払いの有効なPriceか・金額・通貨を確認する（DBロックなし）
  2. トランザクション1：ユーザー行をロック（active を再確認）→ 有料の権限があれば409
     → 未決済の行（creating・pending）を確認 → なければ creating の行と idempotency key を作る
  3. creating の行：その行の idempotency key でSessionを作成する（DBロックなし）
     → トランザクション2：ユーザー行 → 決済行の順にロックし、creating のままならSession IDを保存して pending にする
  4. pending の行：Session IDでStripeからSessionを取得する（DBロックなし）
     open → そのURLを返す／expired → 行を expired にして2からやり直す／complete → 決済の確認へ進んでもらう

creating の扱い（Q-34の案）：
  - 処理中か停滞しているかをタイムアウトで分けず、どちらも保存済みの同じ idempotency key でStripeを呼び直す
    （Stripeは同じキー・同じ内容なら、作成済みのSessionを返す）
  - 最初のリクエストがまだ処理中なら、Stripeが409を返すので CheckoutInProgress にする
  - 送る内容が前回と違ってStripeが受け付けない場合は、その行を failed にして新しい行で作り直す
  - 通信の失敗・タイムアウトでは failed にしない（creating のまま残し、次のリクエストで同じキーで再試行する）

秘密鍵・Session ID・URLをログ・例外のメッセージに含めない。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.features.payments.exceptions import (
    AlreadyPaid,
    CheckoutInProgress,
    PaymentConfirmationRequired,
    PlanNotAvailable,
    PriceConfigError,
    UnexpectedSessionState,
)
from app.features.payments.repository import (
    DuplicateUnfinishedPayment,
    NewPayment,
    PaymentRepository,
    StoredPayment,
    UserNotActive,
)
from app.features.payments.settings import CheckoutSettings
from app.integrations.stripe.client import (
    CheckoutSession,
    StripeIdempotencyInProgress,
    StripeIdempotencyMismatch,
    StripePrice,
    StripeSessionNotFound,
)

logger = logging.getLogger(__name__)

# 期限切れの行の置き換えや、同時リクエストとの競合でやり直す回数の上限
MAX_ATTEMPTS = 3


class CheckoutClient(Protocol):
    """StripeCheckoutClient のうち、Session作成で使うメソッド。テストでは偽物に差し替える"""

    async def retrieve_price(self, price_id: str) -> StripePrice: ...

    async def create_checkout_session(
        self,
        *,
        price_id: str,
        client_reference_id: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
        idempotency_key: str,
    ) -> CheckoutSession: ...

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutSession: ...


@dataclass(frozen=True)
class CheckoutStarted:
    session_id: str = field(repr=False)
    checkout_url: str = field(repr=False)


class CheckoutService:
    def __init__(
        self,
        repository: PaymentRepository,
        stripe_client: CheckoutClient,
        settings: CheckoutSettings,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._stripe = stripe_client
        self._settings = settings
        self._now = now

    async def create_checkout(self, user_id: UUID, plan_code: str) -> CheckoutStarted:
        price_id = self._settings.price_ids.get(plan_code)
        if price_id is None:
            raise PlanNotAvailable
        price = await self._get_price(price_id)

        for _ in range(MAX_ATTEMPTS):
            payment = await self._reserve(user_id, plan_code, price)
            # MVPの有料プランは1つのため、既存の行のプランと price_id は一致する前提
            if payment.status == "creating":
                started = await self._create_session(user_id, payment, price_id)
            else:
                started = await self._reuse_session(user_id, payment)
            if started is not None:
                return started
        # 期限切れ・競合が続いた。少し待って再試行してもらう
        raise CheckoutInProgress

    async def _get_price(self, price_id: str) -> StripePrice:
        """金額・通貨はStripe Priceを正とする。設定の誤りを無料・別の金額で補わない"""
        price = await self._stripe.retrieve_price(price_id)
        if (
            not price.active
            or price.type != "one_time"
            or price.unit_amount is None
            or price.unit_amount < 0
            or not price.currency
        ):
            raise PriceConfigError("Stripe Priceが一回払いの有効なPriceではありません")
        return price

    async def _reserve(self, user_id: UUID, plan_code: str, price: StripePrice) -> StoredPayment:
        """トランザクション1。未決済の行を返す（なければ creating の行を作る）"""
        try:
            async with self._repository.transaction() as tx:
                # ユーザー不在・active でない場合は例外で抜け、行を作らない
                await tx.lock_user(user_id)
                if await tx.has_paid_entitlement(user_id, self._now()):
                    raise AlreadyPaid
                plan = await tx.find_plan(plan_code)
                if plan is None or not plan.is_active:
                    raise PlanNotAvailable
                existing = await tx.find_unfinished(user_id)
                if existing is not None:
                    return existing
                return await tx.insert(
                    NewPayment(
                        id=uuid4(),
                        user_id=user_id,
                        plan_id=plan.id,
                        idempotency_key=uuid4(),
                        amount_minor=price.unit_amount,
                        currency=price.currency,
                    )
                )
        except DuplicateUnfinishedPayment:
            # ロックをすり抜けた同時リクエストが先に作った（部分UNIQUE索引が最後の守り）
            existing = await self._repository.find_unfinished(user_id)
            if existing is None:
                raise CheckoutInProgress from None
            return existing

    async def _create_session(
        self, user_id: UUID, payment: StoredPayment, price_id: str
    ) -> CheckoutStarted | None:
        """creating の行のSessionを作成する。やり直しが必要なら None を返す"""
        try:
            # 同じ行で再試行したときに同じ内容になるよう、行と設定の値だけから組み立てる
            session = await self._stripe.create_checkout_session(
                price_id=price_id,
                client_reference_id=str(user_id),
                metadata={"payment_id": str(payment.id)},
                success_url=self._settings.success_url,
                cancel_url=self._settings.cancel_url,
                idempotency_key=str(payment.idempotency_key),
            )
        except StripeIdempotencyInProgress:
            raise CheckoutInProgress from None
        except StripeIdempotencyMismatch:
            # このキーでは作成できない。行を failed にして、新しい行で作り直す
            logger.warning("checkout payment marked failed: idempotency key mismatch")
            await self._mark(user_id, payment, "creating", "failed")
            return None
        if session.url is None:
            raise UnexpectedSessionState("作成したSessionにURLがありません")

        async with self._repository.transaction() as tx:
            # Stripeの呼び出し中に退会処理が始まっても、作成したSessionを記録から消さない
            user_status = await tx.lock_user(user_id, require_active=False)
            current = await tx.lock_payment(payment.id)
            if current is None:
                return None
            if current.status == "creating":
                await tx.mark_pending(payment.id, session.id)
            elif current.stripe_checkout_session_id != session.id:
                # 別のリクエストが行を進めた。最初からやり直す
                return None
        if user_status != "active":
            raise UserNotActive
        return CheckoutStarted(session_id=session.id, checkout_url=session.url)

    async def _reuse_session(self, user_id: UUID, payment: StoredPayment) -> CheckoutStarted | None:
        """pending の行のSessionを再利用する。やり直しが必要なら None を返す"""
        session_id = payment.stripe_checkout_session_id
        if session_id is None:
            raise UnexpectedSessionState("pending の行にSession IDがありません")
        try:
            session = await self._stripe.retrieve_checkout_session(session_id)
        except StripeSessionNotFound:
            # Stripe側にSessionがない（テストモードのデータ削除など）。この行では続けられない
            logger.warning("checkout payment marked failed: session not found")
            await self._mark(user_id, payment, "pending", "failed")
            return None

        if session.status == "open" and session.url is not None:
            return CheckoutStarted(session_id=session.id, checkout_url=session.url)
        if session.status == "expired":
            await self._mark(user_id, payment, "pending", "expired")
            return None
        if session.status == "complete":
            # 新しいSessionは作らない。画面から決済の確認へ進んでもらう
            raise PaymentConfirmationRequired(session.id)
        raise UnexpectedSessionState("想定外のSessionの状態です")

    async def _mark(
        self, user_id: UUID, payment: StoredPayment, expected: str, new_status: str
    ) -> None:
        """行がまだ expected の状態のときだけ new_status に変える（別のリクエストが進めていたら何もしない）"""
        async with self._repository.transaction() as tx:
            await tx.lock_user(user_id, require_active=False)
            current = await tx.lock_payment(payment.id)
            if current is None or current.status != expected:
                return
            if new_status == "expired":
                await tx.mark_expired(payment.id, self._now())
            else:
                await tx.mark_failed(payment.id)
