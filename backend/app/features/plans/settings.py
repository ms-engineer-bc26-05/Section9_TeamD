"""プランごとの上限値（#57で決定・#59の決定により usage/ から移動。#92）と、Stripe PriceのID（#95）。

- 上限値はコードへ固定せず環境変数から読み込む。DBの plans 表には上限値の列を作らない（#59）
- 環境変数の名前は #57 のときのまま（USAGE_...）。.env.example・compose.yaml を変えずに済むようにする
- 上限値に "unlimited" を指定した場合だけ「無制限」（APIでは null）として扱う。
  値の読み込みに失敗した場合を無制限とみなさないよう、不正な値は起動時にエラーにする
- Stripe PriceのIDは、上限値とは別の項目として持つ（#59の決定。F-05の payments/settings.py から移動）。
  環境変数の名前は F-05 のとき（STRIPE_PRICE_ID_PREMIUM）のまま。未設定のプランは購入できない
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache

UNLIMITED = "unlimited"

# 既定値（#57 質問①・#59で決定した値。有料プランの値はMVPテスト用の暫定値）
DEFAULT_FREE_CONSULTATION_LIMIT = "3"
DEFAULT_PREMIUM_CONSULTATION_LIMIT = "30"  # #59で決定（暫定値）
DEFAULT_FREE_MEMO_LIMIT = "10"  # API設計6.8.1の仮の値
DEFAULT_PREMIUM_MEMO_LIMIT = "100"  # #59で決定（暫定値）


class PlanCode(StrEnum):
    """プランの識別子（API設計6.8.1の plan_code。DBの plans.code と同じ値）"""

    FREE = "free"
    PREMIUM = "premium"


@dataclass(frozen=True)
class PlanLimits:
    """プランごとの上限。None は「無制限」"""

    consultation_limit: int | None
    memo_limit: int | None


@dataclass(frozen=True)
class PlanSettings:
    plan_limits: Mapping[PlanCode, PlanLimits]
    # プラン → Stripe PriceのID。設定されているプランだけを持つ（無料・未設定のプランは入れない）
    stripe_price_ids: Mapping[PlanCode, str] = field(default_factory=dict, repr=False)

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


def load_plan_settings(env: Mapping[str, str] | None = None) -> PlanSettings:
    """環境変数から上限値と Stripe PriceのIDを読み込む。

    不正な値は ValueError（エラーメッセージに値そのものは含めない）。
    """
    env = os.environ if env is None else env

    def limit(name: str, default: str) -> int | None:
        return _parse_limit(name, env.get(name, default))

    stripe_price_ids = {}
    premium_price_id = env.get("STRIPE_PRICE_ID_PREMIUM", "").strip()
    if premium_price_id:
        stripe_price_ids[PlanCode.PREMIUM] = premium_price_id

    return PlanSettings(
        stripe_price_ids=stripe_price_ids,
        plan_limits={
            PlanCode.FREE: PlanLimits(
                consultation_limit=limit(
                    "USAGE_FREE_CONSULTATION_LIMIT", DEFAULT_FREE_CONSULTATION_LIMIT
                ),
                memo_limit=limit("USAGE_FREE_MEMO_LIMIT", DEFAULT_FREE_MEMO_LIMIT),
            ),
            PlanCode.PREMIUM: PlanLimits(
                consultation_limit=limit(
                    "USAGE_PREMIUM_CONSULTATION_LIMIT", DEFAULT_PREMIUM_CONSULTATION_LIMIT
                ),
                memo_limit=limit("USAGE_PREMIUM_MEMO_LIMIT", DEFAULT_PREMIUM_MEMO_LIMIT),
            ),
        }
    )


@lru_cache(maxsize=1)
def get_plan_settings() -> PlanSettings:
    """APIで使う上限値。プロセス内で1回だけ読み込む（値を変えた場合は再起動で反映）"""
    return load_plan_settings()
