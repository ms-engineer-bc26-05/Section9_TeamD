"""退会時の未完了の決済の照合（#60で合意した退会用の関数。docs/api-design.md 6.9の手順3）。

退会処理（F-06）がユーザーを deleting にした後に呼ぶ。deleting のユーザーには新しい creating の行が
作られない（Session作成の最初のトランザクションが active を要求する）ため、照合中に未完了の行は増えない。

照合の流れ（#60の結論）：
  - creating の行：状態不明のため PaymentSettlementBlocked（退会は deleting のまま止める）
  - pending の行：Stripeに照会する（DBロックなし）
      open     → Sessionを期限切れにして expired にする。期限切れにできなければ照会し直し、
                 それでも確認できなければ PaymentSettlementBlocked（未確認のまま expired にしない）
      expired  → expired にする
      complete → 支払い済みなら paid の記録だけを残す（利用権限は付与しない。決済の確認の退会処理中と同じ）
      見つからない → PaymentSettlementBlocked（環境の違いの可能性があるため、failed にしない。PR #100のレビュー）
  - Stripeに接続できない場合は StripeUnavailable をそのまま送出する（deleting のまま残し、再実行で再開）
  - 再実行しても安全。未完了の行がなければ何もしない

秘密鍵・Session ID・URLをログ・例外のメッセージに含めない。
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.features.payments.exceptions import (
    PaymentSettlementBlocked,
    PaymentVerificationFailed,
    UnexpectedSessionState,
)
from app.features.payments.repository import PaymentRepository, StoredPayment
from app.integrations.stripe.client import (
    CheckoutSession,
    StripeClientError,
    StripeSessionNotFound,
    StripeUnavailable,
)

logger = logging.getLogger(__name__)

# 未完了の行は1件までだが、照合の間に別の処理が行を進めた場合に備えて数回だけ見直す
MAX_ROUNDS = 3


class SettlementClient(Protocol):
    """StripeCheckoutClient のうち、退会時の照合で使うメソッド。テストでは偽物に差し替える"""

    async def retrieve_checkout_session(self, session_id: str) -> CheckoutSession: ...

    async def expire_checkout_session(self, session_id: str) -> CheckoutSession: ...


class PaymentSettlementService:
    def __init__(
        self,
        repository: PaymentRepository,
        stripe_client: SettlementClient,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._stripe = stripe_client
        self._now = now

    async def settle_unfinished_payments(self, user_id: UUID) -> None:
        for _ in range(MAX_ROUNDS):
            payment = await self._repository.find_unfinished(user_id)
            if payment is None:
                return
            if payment.status == "creating":
                logger.warning("payment settlement blocked: payment_id=%s reason=creating", payment.id)
                raise PaymentSettlementBlocked
            await self._settle_pending(user_id, payment)
        # 見直しても未完了の行が残る。確定できないまま退会を進めない
        raise PaymentSettlementBlocked

    async def _settle_pending(self, user_id: UUID, payment: StoredPayment) -> None:
        session_id = payment.stripe_checkout_session_id
        if session_id is None:
            raise UnexpectedSessionState("pending の行にSession IDがありません")
        try:
            session = await self._stripe.retrieve_checkout_session(session_id)
        except StripeSessionNotFound:
            # 作成時と照会時でアカウント・サンドボックス・鍵が違うと、支払い済みのSessionでも見つからない。
            # 環境の一致を確認できないため、failed にせず退会を止める（Session作成と同じ扱い。PR #100のレビュー）
            logger.warning(
                "payment settlement blocked: payment_id=%s reason=session_not_found", payment.id
            )
            raise PaymentSettlementBlocked from None
        self._check_owner(user_id, payment, session)

        if session.status == "open":
            session = await self._expire(session_id)
        if session.status == "expired":
            await self._mark(user_id, payment, "expired")
        elif session.status == "complete":
            await self._record_paid(user_id, payment, session)
        else:
            raise UnexpectedSessionState("想定外のSessionの状態です")

    async def _expire(self, session_id: str) -> CheckoutSession:
        """open のSessionを期限切れにする。失敗したら照会し直し、まだ open なら止める"""
        try:
            return await self._stripe.expire_checkout_session(session_id)
        except StripeClientError as exc:
            # 期限切れにする直前に支払われた・期限が切れた場合も失敗する。状態を確かめ直す
            logger.warning("payment settlement expire failed: reason=%s", type(exc).__name__)
        try:
            session = await self._stripe.retrieve_checkout_session(session_id)
        except StripeUnavailable:
            raise
        except StripeClientError:
            raise PaymentSettlementBlocked from None
        if session.status == "open":
            raise PaymentSettlementBlocked
        return session

    @staticmethod
    def _check_owner(user_id: UUID, payment: StoredPayment, session: CheckoutSession) -> None:
        if (
            session.client_reference_id != str(user_id)
            or session.metadata.get("payment_id") != str(payment.id)
        ):
            logger.warning("payment settlement rejected: session owner mismatch")
            raise PaymentVerificationFailed("Sessionの本人・決済IDが行と一致しません")

    async def _record_paid(
        self, user_id: UUID, payment: StoredPayment, session: CheckoutSession
    ) -> None:
        if session.payment_status != "paid":
            # 完了したが支払いが確定していない。確定するまで退会を進めない
            raise PaymentSettlementBlocked
        if session.amount_total != payment.amount_minor or session.currency != payment.currency:
            logger.warning("payment settlement rejected: amount or currency mismatch")
            raise PaymentVerificationFailed("Stripeの金額・通貨が購入時の値と一致しません")
        await self._mark(user_id, payment, "paid")

    async def _mark(self, user_id: UUID, payment: StoredPayment, new_status: str) -> None:
        """行がまだ pending のときだけ new_status に変える（別の処理が進めていたら何もしない）"""
        now = self._now()
        async with self._repository.transaction() as tx:
            await tx.lock_user(user_id, require_active=False)
            current = await tx.lock_payment(payment.id)
            if current is None or current.status != "pending":
                return
            if new_status == "paid":
                await tx.mark_paid(current.id, now)
            else:
                await tx.mark_expired(current.id, now)
