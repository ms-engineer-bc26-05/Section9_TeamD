"""ほかの機能から呼ぶ、決済機能の入口。

退会処理（F-06 #60）からは settle_unfinished_payments だけを呼ぶ（#60で合意）。
"""

from uuid import UUID

from app.core.database import get_session_factory
from app.features.payments.db_repository import SqlAlchemyPaymentRepository
from app.features.payments.exceptions import PaymentSettlementBlocked
from app.features.payments.settlement import PaymentSettlementService
from app.integrations.stripe.client import StripeUnavailable, get_stripe_client

__all__ = ["PaymentSettlementBlocked", "StripeUnavailable", "settle_unfinished_payments"]


async def settle_unfinished_payments(user_id: UUID) -> None:
    """退会処理中（deleting）のユーザーの未完了の決済を、Stripeと照合して確定する。

    ユーザーを deleting にした後、Firebaseや関連データを削除する前に呼ぶ。再実行しても安全。
    - 確定できない（状態不明の creating が残っている等）：PaymentSettlementBlocked
    - Stripeに接続できない：StripeUnavailable（503）
    - DBに接続できない：DatabaseUnavailableError（503）
    どの例外でも退会は deleting のまま止め、再実行で再開する。
    """
    service = PaymentSettlementService(
        SqlAlchemyPaymentRepository(get_session_factory()), get_stripe_client()
    )
    await service.settle_unfinished_payments(user_id)
