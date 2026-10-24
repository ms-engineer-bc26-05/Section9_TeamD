"""決済の設定値（環境ごとのサーバー設定）。

Stripe PriceのIDは、プランの設定値（plans/public.py の PlanSettings.stripe_price_ids）から読む（#59・#95）。
秘密鍵は integrations/stripe/client.py で読む。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.features.plans.public import load_plan_settings


@dataclass(frozen=True)
class CheckoutSettings:
    # plan_code → Stripe PriceのID。未設定のプランは購入できない（無料・無制限として補わない）
    price_ids: Mapping[str, str] = field(repr=False)
    # 決済後・キャンセル後に戻る画面のURL。同じidempotency keyで再試行するときも同じ値を送る
    success_url: str
    cancel_url: str


def load_checkout_settings() -> CheckoutSettings:
    return CheckoutSettings(
        price_ids=dict(load_plan_settings().stripe_price_ids),
        success_url=os.environ.get(
            "CHECKOUT_SUCCESS_URL",
            "http://localhost:3000/plan/success?session_id={CHECKOUT_SESSION_ID}",
        ),
        cancel_url=os.environ.get("CHECKOUT_CANCEL_URL", "http://localhost:3000/plan"),
    )
