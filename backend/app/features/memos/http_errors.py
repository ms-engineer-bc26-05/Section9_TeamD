"""メモ保存APIの例外を、設計書3.5の形式のエラーレスポンスへ変換する。

相談機能の例外（404・409）は、継承元の ConsultationRoute で変換する。
エラーの本文・ログに、本文・鍵・暗号文を含めない。

想定外の例外（commit失敗など）も500（INTERNAL_ERROR）へ変換し、上へ送らない。
DBの例外はメッセージにSQLのパラメータ（暗号文）を含みうるため、
トレースバック・メッセージを出さず、例外の種類だけを記録する。
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.features.consultations.public import ConsultationRoute
from app.features.memos.crypto import MemoEncryptionError
from app.features.memos.exceptions import MemoRepositoryUnavailable, NotAuthenticated
from app.features.memos.repository import UserNotActive, UserNotFound

logger = logging.getLogger(__name__)

_SAVE_FAILED = (
    500,
    "INTERNAL_ERROR",
    "メモを保存できませんでした。時間をおいてもう一度お試しください。",
)

_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    NotAuthenticated: (401, "UNAUTHORIZED", "ログインしてください。"),
    # ロック後の再確認（認証後に内部ユーザーが削除された・退会処理が始まった）。I-01と同じcode
    UserNotFound: (401, "UNAUTHORIZED", "ログインしてください。"),
    UserNotActive: (403, "ACCOUNT_DELETING", "退会処理中のため利用できません。"),
    # 鍵の未設定・復号失敗・照合失敗。原因を区別して返さない
    MemoEncryptionError: _SAVE_FAILED,
    MemoRepositoryUnavailable: _SAVE_FAILED,
}


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def memo_error_response(exc: Exception) -> JSONResponse:
    for exc_type, (status_code, code, message) in _ERRORS.items():
        if isinstance(exc, exc_type):
            # 例外の種類だけを記録し、メッセージは出さない
            logger.info("memo api error: %s", code)
            return _error_response(status_code, code, message)
    # 想定外の例外。メッセージ・トレースバックは出さない
    logger.error("memo api unexpected error: %s", type(exc).__name__)
    return _error_response(*_SAVE_FAILED)


class MemoRoute(ConsultationRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except (RequestValidationError, HTTPException):
                # 422・400などは共通のエラーハンドラ（app.core.errors）で変換する
                # I-01（#47）との接続時：#47の認証・DB用の専用例外（401・403・503）も
                # ここで共通ハンドラへ送り、500に変換しないようにする
                raise
            except Exception as exc:
                return memo_error_response(exc)

        return route_handler
