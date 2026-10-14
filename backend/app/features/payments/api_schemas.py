"""決済APIのリクエスト・レスポンス（docs/api-design.md 6.8.6〜6.8.8。#59で共有した契約）。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckoutSessionRequest(BaseModel):
    """POST /payments/checkout-session。金額・Price IDはクライアントから受け取らない"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plan_code: str = Field(min_length=1, max_length=50)


class CheckoutSessionView(BaseModel):
    checkout_url: str
    session_id: str


class ConfirmRequest(BaseModel):
    """POST /payments/confirm。session_id を省略すると、本人の未確認の決済を確認する"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str | None = Field(default=None, min_length=1, max_length=255)


class ConfirmView(BaseModel):
    status: Literal["paid", "pending", "expired"]


class CurrentPlanView(BaseModel):
    plan_code: Literal["free", "premium"]
