"""利用回数制限の設定値（Issue #57）。

- 期間・Redisのタイムアウトは、コードへ固定せず環境変数から読み込む
- 設定値は共通の config.py ではなく、この機能の中で読み込む（他Issueとの競合を避けるため）
- プランごとの上限値は、#59の決定により plans/ へ移した（#92）。ここでは plans/public.py から読み込み、
  UsageSettings.limits_for で今までどおり使えるようにしている
  （PlanCode・PlanLimits もこのモジュールからimportできる。memos/limits.py は #95 で plans/public.py の
  get_plan_settings から読む形に変えた。GET /usage・相談開始は今までどおりこのモジュールから読む）
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from app.features.plans.public import (
    UNLIMITED,
    PlanCode,
    PlanLimits,
    load_plan_settings,
)

# 移動前と同じ場所からもimportできるようにする（呼び出し元を変えないため）
__all__ = [
    "UNLIMITED",
    "PlanCode",
    "PlanLimits",
    "UsageSettings",
    "get_usage_settings",
    "load_usage_settings",
]

# 期間の既定値（#57 質問①）
DEFAULT_PERIOD_SECONDS = str(30 * 24 * 60 * 60)  # 30日

# Redisのタイムアウト（秒）。Issue #57で待ち時間を実測して決定（質問⑧）
DEFAULT_REDIS_CONNECT_TIMEOUT_SECONDS = "0.5"
DEFAULT_REDIS_COMMAND_TIMEOUT_SECONDS = "0.5"


@dataclass(frozen=True)
class UsageSettings:
    plan_limits: Mapping[PlanCode, PlanLimits]
    period_seconds: int
    redis_url: str
    redis_connect_timeout_seconds: float
    redis_command_timeout_seconds: float

    def limits_for(self, plan_code: PlanCode) -> PlanLimits:
        return self.plan_limits[plan_code]


def _parse_positive_int(name: str, value: str) -> int:
    try:
        number = int(value.strip())
    except ValueError:
        raise ValueError(f"{name} は1以上の整数を指定してください") from None
    if number < 1:
        raise ValueError(f"{name} は1以上の整数を指定してください")
    return number


def _parse_timeout(name: str, value: str) -> float:
    try:
        seconds = float(value.strip())
    except ValueError:
        raise ValueError(f"{name} は0より大きい秒数を指定してください") from None
    if seconds <= 0:
        raise ValueError(f"{name} は0より大きい秒数を指定してください")
    return seconds


def load_usage_settings(env: Mapping[str, str] | None = None) -> UsageSettings:
    """環境変数から設定値を読み込む。

    不正な値は ValueError（エラーメッセージに値そのものは含めない）。
    """
    env = os.environ if env is None else env

    def get(name: str, default: str) -> str:
        return env.get(name, default)

    return UsageSettings(
        plan_limits=load_plan_settings(env).plan_limits,
        period_seconds=_parse_positive_int(
            "USAGE_PERIOD_SECONDS", get("USAGE_PERIOD_SECONDS", DEFAULT_PERIOD_SECONDS)
        ),
        redis_url=get("REDIS_URL", ""),
        redis_connect_timeout_seconds=_parse_timeout(
            "REDIS_CONNECT_TIMEOUT_SECONDS",
            get("REDIS_CONNECT_TIMEOUT_SECONDS", DEFAULT_REDIS_CONNECT_TIMEOUT_SECONDS),
        ),
        redis_command_timeout_seconds=_parse_timeout(
            "REDIS_COMMAND_TIMEOUT_SECONDS",
            get("REDIS_COMMAND_TIMEOUT_SECONDS", DEFAULT_REDIS_COMMAND_TIMEOUT_SECONDS),
        ),
    )


@lru_cache(maxsize=1)
def get_usage_settings() -> UsageSettings:
    """APIで使う設定値。プロセス内で1回だけ読み込む（値を変えた場合は再起動で反映）"""
    return load_usage_settings()
