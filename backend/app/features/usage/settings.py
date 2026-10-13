"""利用回数制限の設定値（Issue #57）。

- 上限値・期間・Redisのタイムアウトは、コードへ固定せず環境変数から読み込む
- 設定値は共通の config.py ではなく、この機能の中で読み込む（他Issueとの競合を避けるため）
- 上限値に "unlimited" を指定した場合だけ「無制限」（APIでは null）として扱う。
  値の読み込みに失敗した場合を無制限とみなさないよう、不正な値は起動時にエラーにする
- #59の決定により、設定値とプランの判定は将来 backend/app/features/plans/ へ移す
  （F-05で plans/ ができた後、後続のIssueで移す。他の機能は plans/public.py だけを使う）
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

UNLIMITED = "unlimited"

# 既定値（#57 質問①・#59で決定した値。有料プランの値はMVPテスト用の暫定値）
DEFAULT_FREE_CONSULTATION_LIMIT = "3"
DEFAULT_PREMIUM_CONSULTATION_LIMIT = "30"  # #59で決定（暫定値）
DEFAULT_FREE_MEMO_LIMIT = "10"  # API設計6.8.1の仮の値
DEFAULT_PREMIUM_MEMO_LIMIT = "100"  # #59で決定（暫定値）
DEFAULT_PERIOD_SECONDS = str(30 * 24 * 60 * 60)  # 30日

# Redisのタイムアウト（秒）。Issue #57で待ち時間を実測して決定（質問⑧）
DEFAULT_REDIS_CONNECT_TIMEOUT_SECONDS = "0.5"
DEFAULT_REDIS_COMMAND_TIMEOUT_SECONDS = "0.5"


class PlanCode(StrEnum):
    """プランの識別子（API設計6.8.1の plan_code）"""

    FREE = "free"
    PREMIUM = "premium"


@dataclass(frozen=True)
class PlanLimits:
    """プランごとの上限。None は「無制限」"""

    consultation_limit: int | None
    memo_limit: int | None


@dataclass(frozen=True)
class UsageSettings:
    plan_limits: Mapping[PlanCode, PlanLimits]
    period_seconds: int
    redis_url: str
    redis_connect_timeout_seconds: float
    redis_command_timeout_seconds: float

    def limits_for(self, plan_code: PlanCode) -> PlanLimits:
        return self.plan_limits[plan_code]


def _parse_limit(name: str, value: str) -> int | None:
    value = value.strip()
    if value == UNLIMITED:
        return None
    try:
        limit = int(value)
    except ValueError:
        raise ValueError(f"{name} は0以上の整数か {UNLIMITED} を指定してください") from None
    if limit < 0:
        raise ValueError(f"{name} は0以上の整数か {UNLIMITED} を指定してください")
    return limit


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

    plan_limits = {
        PlanCode.FREE: PlanLimits(
            consultation_limit=_parse_limit(
                "USAGE_FREE_CONSULTATION_LIMIT",
                get("USAGE_FREE_CONSULTATION_LIMIT", DEFAULT_FREE_CONSULTATION_LIMIT),
            ),
            memo_limit=_parse_limit(
                "USAGE_FREE_MEMO_LIMIT", get("USAGE_FREE_MEMO_LIMIT", DEFAULT_FREE_MEMO_LIMIT)
            ),
        ),
        PlanCode.PREMIUM: PlanLimits(
            consultation_limit=_parse_limit(
                "USAGE_PREMIUM_CONSULTATION_LIMIT",
                get("USAGE_PREMIUM_CONSULTATION_LIMIT", DEFAULT_PREMIUM_CONSULTATION_LIMIT),
            ),
            memo_limit=_parse_limit(
                "USAGE_PREMIUM_MEMO_LIMIT",
                get("USAGE_PREMIUM_MEMO_LIMIT", DEFAULT_PREMIUM_MEMO_LIMIT),
            ),
        ),
    }
    return UsageSettings(
        plan_limits=plan_limits,
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
