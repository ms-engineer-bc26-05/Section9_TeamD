"""決済の確認（docs/api-design.md 6.8.8・#59）。

確認の流れ（#59の結論）：
  1. 確認する行を決める（DBロックなし）
     - session_id あり：その行。ない、または本人の行でなければ PaymentNotFound
     - session_id なし：本人の pending の行。なければ「paid だが利用権限へ未反映」の行
     - すでに paid で利用権限へ反映済みなら、Stripeを呼ばずに paid を返す（何度呼んでも同じ結果）
  2. Stripeに照会する（DBロックなし。ロックを持ったままStripeを呼ばない）
     - 本人（client_reference_id）・metadataの決済IDが行と一致するか → 一致しなければ PaymentNotFound
     - payment_status が paid でなければ pending（期限切れなら行を expired にして expired）
     - 金額・通貨が購入時に保存した値と一致するか → 一致しなければ PaymentVerificationFailed
  3. 短いトランザクション：ユーザー行 → 決済行の順にロックして再確認する
     - 行を paid にし、ユーザーが active なら利用権限の付与と反映日時の記録を同じトランザクションで行う
     - 退会処理中なら利用権限は付与せず、paid の記録だけを commit してから UserNotActive（APIでは403）

秘密鍵・Session ID・URLをログ・例外のメッセージに含めない。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from app.features.payments.exceptions import (
    PaymentNotFound,
    PaymentVerificationFailed,
    UnexpectedSessionState,
)
from app.features.payments.repository import (
    PaymentRepository,
    StoredPayment,
    UserNotActive,
)
from app.integrations.stripe.client import CheckoutSession, StripeSessionNotFound

logger = logging.getLogger(__name__)

ConfirmStatus = Literal["paid", "pending", "expired"]


class ConfirmClient(Protocol):
    """StripeCheckoutClient のうち、決済の確認で使うメソッド。テストでは偽物に差し替える"""

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutSession: ...


@dataclass(frozen=True)
class ConfirmResult:
    status: ConfirmStatus


class PaymentConfirmService:
    def __init__(
        self,
        repository: PaymentRepository,
        stripe_client: ConfirmClient,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._stripe = stripe_client
        self._now = now

    async def confirm(self, user_id: UUID, session_id: str | None = None) -> ConfirmResult:
        payment = await self._find_target(user_id, session_id)
        if payment.status == "paid":
            if payment.entitlement_applied_at is not None:
                return ConfirmResult("paid")
            # Stripeでは確認済み。利用権限への反映だけをやり直す
            return await self._apply(user_id, payment)
        if payment.status != "pending" or payment.stripe_checkout_session_id is None:
            # session_id で指定された行が creating・expired・failed（確認できる決済ではない）
            raise PaymentNotFound

        session = await self._retrieve(payment.stripe_checkout_session_id)
        if (
            session.client_reference_id != str(user_id)
            or session.metadata.get("payment_id") != str(payment.id)
        ):
            logger.warning("payment confirm rejected: session owner mismatch")
            raise PaymentNotFound
        if session.payment_status != "paid":
            if session.status == "expired":
                await self._mark_expired(user_id, payment)
                return ConfirmResult("expired")
            if session.status in ("open", "complete"):
                return ConfirmResult("pending")
            raise UnexpectedSessionState("想定外のSessionの状態です")
        if session.amount_total != payment.amount_minor or session.currency != payment.currency:
            logger.warning("payment confirm rejected: amount or currency mismatch")
            raise PaymentVerificationFailed("Stripeの金額・通貨が購入時の値と一致しません")
        return await self._apply(user_id, payment)

    async def _find_target(self, user_id: UUID, session_id: str | None) -> StoredPayment:
        if session_id is None:
            payment = await self._repository.find_confirmable(user_id)
        else:
            payment = await self._repository.find_by_session_id(session_id)
        # 他人の決済は、存在しない場合と同じ扱いにする
        if payment is None or payment.user_id != user_id:
            raise PaymentNotFound
        return payment

    async def _retrieve(self, session_id: str) -> CheckoutSession:
        try:
            return await self._stripe.retrieve_checkout_session(session_id)
        except StripeSessionNotFound:
            raise PaymentNotFound from None

    async def _apply(self, user_id: UUID, payment: StoredPayment) -> ConfirmResult:
        """支払い済みの記録と利用権限の付与を、同じトランザクションで確定する"""
        now = self._now()
        async with self._repository.transaction() as tx:
            user_status = await tx.lock_user(user_id, require_active=False)
            current = await tx.lock_payment(payment.id)
            if current is None:
                raise PaymentNotFound
            if current.status == "pending":
                await tx.mark_paid(current.id, now)
            elif current.status != "paid":
                # 照会の間に、別の処理が行を expired・failed にした
                raise PaymentNotFound
            if current.entitlement_applied_at is None and user_status == "active":
                await tx.grant_entitlement(user_id, current.plan_id, now)
                await tx.mark_entitlement_applied(current.id, now)
        # 退会処理中：paid の記録は commit 済み。利用権限は付与しない
        if user_status != "active":
            raise UserNotActive
        return ConfirmResult("paid")

    async def _mark_expired(self, user_id: UUID, payment: StoredPayment) -> None:
        """Stripeで期限切れと確認できた pending の行を expired にする"""
        async with self._repository.transaction() as tx:
            await tx.lock_user(user_id, require_active=False)
            current = await tx.lock_payment(payment.id)
            if current is not None and current.status == "pending":
                await tx.mark_expired(current.id, self._now())
