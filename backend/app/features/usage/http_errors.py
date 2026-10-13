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
    AccountDeleting,
    MemoCountUnavailable,
    NotAuthenticated,
    PlanUnavailable,
    UsageLimitExceeded,
    UserStatusUnavailable,
)

logger = logging.getLogger(__name__)

# プラン・ユーザーの状態・保存件数をDBで確認できない場合。
# I-01（PR #85）の共通のエラー変換と同じcode・文言にそろえる
_DB_UNAVAILABLE = (503, "DB_UNAVAILABLE", "データベースに接続できませんでした。")

_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    NotAuthenticated: (401, "UNAUTHORIZED", "ログインしてください。"),
    UsageLimitExceeded: (
        403,
        "USAGE_LIMIT_EXCEEDED",
        "現在のプランで利用できる回数に達しました。",
    ),
    # 退会処理中（#47で決定済みのコード・文言）
    AccountDeleting: (403, "ACCOUNT_DELETING", "退会処理中のため利用できません。"),
    PlanUnavailable: _DB_UNAVAILABLE,
    MemoCountUnavailable: _DB_UNAVAILABLE,
    UserStatusUnavailable: _DB_UNAVAILABLE,
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
