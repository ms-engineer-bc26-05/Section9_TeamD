"""相談機能の例外を、設計書3.5の形式のエラーレスポンスへ変換する。

共通の errors.py・main.py を変更しないため、Routerごとに route_class=ConsultationRoute を
指定して変換する。I-05（保存API）など、相談機能の例外を受け取る他のRouterでも同じクラスを使える。
エラーの本文・ログに、相談内容やAIの出力を含めない。
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.features.consultations.ai_schemas import AIOutputInvalid
from app.features.consultations.exceptions import (
    ConsultationBusy,
    ConsultationNotFound,
    ConsultationStateConflict,
    GuidedSkipNotAllowed,
    NotAuthenticated,
    ResultNotReady,
)
from app.integrations.openrouter.client import AIClientError

logger = logging.getLogger(__name__)

_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    NotAuthenticated: (401, "UNAUTHORIZED", "ログインしてください。"),
    ConsultationNotFound: (
        404,
        "CONSULTATION_NOT_FOUND",
        "相談が見つかりません。最初からやり直してください。",
    ),
    ConsultationBusy: (409, "CONSULTATION_BUSY", "前の操作を処理しています。"),
    # ResultNotReady は ConsultationStateConflict の一種のため、先に判定する
    ResultNotReady: (409, "RESULT_NOT_READY", "整理結果はまだできていません。"),
    ConsultationStateConflict: (
        409,
        "CONSULTATION_STATE_CONFLICT",
        "現在の相談の状態では、この操作はできません。",
    ),
    AIClientError: (502, "AI_UNAVAILABLE", "AIの応答を取得できませんでした。"),
    AIOutputInvalid: (502, "AI_OUTPUT_INVALID", "AIの応答を取得できませんでした。"),
}


def consultation_error_response(exc: Exception) -> JSONResponse | None:
    if isinstance(exc, GuidedSkipNotAllowed):
        # 状態によって決まる入力値の誤り。共通の422と同じ形式で返す
        logger.info("consultation api error: VALIDATION_ERROR")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "入力内容を確認してください。",
                    "details": [
                        {"field": "skipped", "reason": "この質問では選択できません。"}
                    ],
                }
            },
        )
    for exc_type, (status_code, code, message) in _ERRORS.items():
        if isinstance(exc, exc_type):
            # 例外の種類だけを記録し、メッセージ（内容）は出さない
            logger.info("consultation api error: %s", code)
            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": message}},
            )
    return None


class ConsultationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except Exception as exc:
                response = consultation_error_response(exc)
                if response is None:
                    raise
                return response

        return route_handler
