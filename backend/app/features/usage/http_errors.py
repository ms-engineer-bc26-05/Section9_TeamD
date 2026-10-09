"""利用回数制限の例外を、設計書3.5の形式のエラーレスポンスへ変換する。

共通の errors.py・main.py を変更しないため、Routerごとに route_class=UsageRoute を指定して変換する。
相談開始API（consultations）へ組み込むときは、usage_error_response を相談側の変換から呼ぶ。
エラーの本文・ログに、ユーザーID・接続先・相談内容を含めない。
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.features.usage.exceptions import (
    MemoCountUnavailable,
    NotAuthenticated,
    PlanUnavailable,
    UsageLimitExceeded,
)

logger = logging.getLogger(__name__)

# プランを確認できない場合のステータスは、認証基盤の障害時（テスト設計Q-05）の決定にそろえる
_UNAVAILABLE = (
    503,
    "SERVICE_UNAVAILABLE",
    "現在ご利用いただけません。時間をおいてお試しください。",
)

_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    NotAuthenticated: (401, "UNAUTHORIZED", "ログインしてください。"),
    UsageLimitExceeded: (
        403,
        "USAGE_LIMIT_EXCEEDED",
        "現在のプランで利用できる回数に達しました。",
    ),
    PlanUnavailable: _UNAVAILABLE,
    MemoCountUnavailable: _UNAVAILABLE,
}


def usage_error_response(exc: Exception) -> JSONResponse | None:
    for exc_type, (status_code, code, message) in _ERRORS.items():
        if isinstance(exc, exc_type):
            logger.info("usage api error: %s", code)
            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": message}},
            )
    return None


class UsageRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except Exception as exc:
                response = usage_error_response(exc)
                if response is None:
                    raise
                return response

        return route_handler
