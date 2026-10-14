"""決済APIの例外を、設計書3.5の形式のエラーレスポンスへ変換する。

- code名は#59でF-04（#58）へ共有した契約のとおり
- 想定外の例外も500へ変換し、上へ送らない。500のcodeは共通の想定外エラー（app.core.errors、#86）と同じ
- エラーの本文・ログに、秘密鍵・Session ID・URL・例外のメッセージを含めない（例外の種類だけを記録する）。
  ただし PAYMENT_CONFIRMATION_REQUIRED は、本人が確認へ進むためにその決済のSession IDを返す
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from app.core.errors import INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE
from app.core.exceptions import (
    AccountDeletingError,
    AuthenticationRequiredError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)
from app.features.payments.exceptions import (
    AlreadyPaid,
    CheckoutInProgress,
    CheckoutNeedsReview,
    PaymentConfirmationRequired,
    PaymentNotFound,
    PlanNotAvailable,
)
from app.features.payments.repository import UserNotActive, UserNotFound
from app.integrations.stripe.client import StripeUnavailable

logger = logging.getLogger(__name__)

_INTERNAL = (500, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE)

# I-01（#47）の認証依存・DB基盤の例外。共通のエラーハンドラ（app.core.errors）で変換する
_COMMON_ERRORS = (
    AuthenticationRequiredError,
    AccountDeletingError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)

_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    PlanNotAvailable: (422, "PLAN_NOT_AVAILABLE", "このプランは現在購入できません。"),
    AlreadyPaid: (409, "ALREADY_PAID", "すでに有料プランをご利用中です。"),
    # 状態不明の creating で止めた場合も、画面では同じ扱い（少し待って再試行）にする（#59）
    CheckoutInProgress: (
        409,
        "CHECKOUT_IN_PROGRESS",
        "決済画面を準備しています。少し待ってから、もう一度お試しください。",
    ),
    CheckoutNeedsReview: (
        409,
        "CHECKOUT_IN_PROGRESS",
        "決済画面を準備しています。少し待ってから、もう一度お試しください。",
    ),
    PaymentNotFound: (404, "PAYMENT_NOT_FOUND", "確認できる決済がありません。"),
    StripeUnavailable: (
        503,
        "PAYMENT_UNAVAILABLE",
        "決済サービスに接続できませんでした。時間をおいてもう一度お試しください。",
    ),
}


def _error_response(status_code: int, code: str, message: str, **extra: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, **extra}},
    )


def payment_error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, PaymentConfirmationRequired):
        logger.info("payment api error: PAYMENT_CONFIRMATION_REQUIRED")
        return _error_response(
            409,
            "PAYMENT_CONFIRMATION_REQUIRED",
            "お支払い済みの決済があります。決済を確認してください。",
            session_id=exc.session_id,
        )
    for exc_type, (status_code, code, message) in _ERRORS.items():
        if isinstance(exc, exc_type):
            logger.info("payment api error: %s", code)
            return _error_response(status_code, code, message)
    # 設定の誤り・Stripeの想定外の応答・金額の不一致・DBの失敗など。原因を区別して返さない
    logger.error("payment api unexpected error: %s", type(exc).__name__)
    return _error_response(*_INTERNAL)


class PaymentRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except (RequestValidationError, HTTPException, *_COMMON_ERRORS):
                # 422・400、認証の401・403・503は共通のエラーハンドラ（app.core.errors）で変換する
                raise
            except UserNotFound:
                # ロック後の再確認（認証後に内部ユーザーが削除された・退会処理が始まった）。
                # I-01の例外へ変換し、文言・WWW-Authenticate ヘッダーも共通のエラーハンドラにそろえる
                raise AuthenticationRequiredError from None
            except UserNotActive:
                raise AccountDeletingError from None
            except Exception as exc:
                return payment_error_response(exc)

        return route_handler
