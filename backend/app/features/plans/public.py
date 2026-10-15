"""プラン機能の公開インターフェース。他の機能からは、このモジュールだけをimportする（#59の決定）。

- get_current_plan：利用中のプラン（セッションは呼び出し元が渡す。#92でじまさんと合意）
- get_plan_settings / PlanSettings.limits_for：プランごとの上限値（相談回数・保存件数）
"""

from app.features.plans.service import get_current_plan
from app.features.plans.settings import (
    UNLIMITED,
    PlanCode,
    PlanLimits,
    PlanSettings,
    get_plan_settings,
    load_plan_settings,
)

__all__ = [
    "UNLIMITED",
    "PlanCode",
    "PlanLimits",
    "PlanSettings",
    "get_current_plan",
    "get_plan_settings",
    "load_plan_settings",
]
