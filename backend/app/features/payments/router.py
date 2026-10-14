"""決済API（docs/api-design.md 6.8.6〜6.8.8。#59で共有した契約）。

- Routerの登録（main.py）は結合Issue（#53）で行う
- 認証は I-01 の get_current_user を使う。401・403・503 は共通のエラーハンドラで返す
- DBは I-01 のセッション基盤を使う。テストでは dependency_overrides でメモリ上の実装へ差し替える
- Stripeはテストモードの鍵だけで呼ぶ（integrations/stripe/client.py）
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends

from app.core.database import get_session_factory
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.payments.api_schemas import (
    CheckoutSessionRequest,
    CheckoutSessionView,
    ConfirmRequest,
    ConfirmView,
    CurrentPlanView,
)
from app.features.payments.confirm import PaymentConfirmService
from app.features.payments.db_repository import SqlAlchemyPaymentRepository
from app.features.payments.http_errors import PaymentRoute
from app.features.payments.repository import PaymentRepository
from app.features.payments.service import CheckoutService
from app.features.payments.settings import CheckoutSettings, load_checkout_settings
from app.integrations.stripe.client import StripeCheckoutClient, get_stripe_client


async def get_current_user_id(current_user: CurrentUser = Depends(get_current_user)) -> UUID:
    """I-01の認証依存から内部ユーザーのIDを取り出す。テストでは固定UUIDを返す"""
    return current_user.user_id


def get_payment_repository() -> PaymentRepository:
    return SqlAlchemyPaymentRepository(get_session_factory())


def get_checkout_settings() -> CheckoutSettings:
    return load_checkout_settings()


def get_checkout_service(
    repository: PaymentRepository = Depends(get_payment_repository),
    stripe_client: StripeCheckoutClient = Depends(get_stripe_client),
    settings: CheckoutSettings = Depends(get_checkout_settings),
) -> CheckoutService:
    return CheckoutService(repository, stripe_client, settings)


def get_confirm_service(
    repository: PaymentRepository = Depends(get_payment_repository),
    stripe_client: StripeCheckoutClient = Depends(get_stripe_client),
) -> PaymentConfirmService:
    return PaymentConfirmService(repository, stripe_client)


router = APIRouter(prefix="/api/v1/payments", tags=["payments"], route_class=PaymentRoute)


@router.post("/checkout-session", response_model=CheckoutSessionView)
async def create_checkout_session(
    body: CheckoutSessionRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckoutService = Depends(get_checkout_service),
) -> CheckoutSessionView:
    started = await service.create_checkout(user_id, body.plan_code)
    return CheckoutSessionView(checkout_url=started.checkout_url, session_id=started.session_id)


@router.post("/confirm", response_model=ConfirmView)
async def confirm_payment(
    body: ConfirmRequest | None = Body(default=None),
    user_id: UUID = Depends(get_current_user_id),
    service: PaymentConfirmService = Depends(get_confirm_service),
) -> ConfirmView:
    result = await service.confirm(user_id, body.session_id if body is not None else None)
    return ConfirmView(status=result.status)


@router.get("/me", response_model=CurrentPlanView)
async def get_my_plan(
    user_id: UUID = Depends(get_current_user_id),
    repository: PaymentRepository = Depends(get_payment_repository),
) -> CurrentPlanView:
    # plans/public.py の get_current_plan ができたら差し替える（#59。GET /usage と同じ判定にする）
    async with repository.transaction() as tx:
        paid = await tx.has_paid_entitlement(user_id, datetime.now(UTC))
    return CurrentPlanView(plan_code="premium" if paid else "free")
