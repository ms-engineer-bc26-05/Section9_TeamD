"""共通のエラーハンドラ。

FastAPI既定の422ハンドラは、失敗した項目の送信値（input）をレスポンスへ含めるため、
相談内容などがエラー本文に混入するおそれがある。
そのため独自のハンドラで上書きし、API設計書（ドラフト）§3.5の形式で、
送信値を含まない固定の文言だけを返す。ログにも送信値は出さない。
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AccountDeletingError,
    AuthenticationRequiredError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)

logger = logging.getLogger(__name__)

_SERVICE_ERRORS = {
    AuthenticationRequiredError: (401, "UNAUTHORIZED", "ログインしてください。"),
    AccountDeletingError: (
        403, "ACCOUNT_DELETING", "退会処理中のため利用できません。"
    ),
    AuthServiceUnavailableError: (
        503,
        "AUTH_UNAVAILABLE",
        "認証サービスを利用できません。時間をおいて再度お試しください。",
    ),
    DatabaseUnavailableError: (
        503, "DB_UNAVAILABLE", "データベースに接続できませんでした。"
    ),
}

# locの先頭に入る「どこから来た値か」を表す要素。項目名には含めない
_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}

# 想定外の項目の名前を置き換える固定の表記。
# 想定外の項目はキー名そのものを送信者が自由に決められるため、キー名を返さない
_UNKNOWN_FIELD = "(unknown)"

# Pydanticのエラー種別ごとの固定文言。Pydanticのメッセージ（msg）は使わない
_REASONS = {
    "missing": "必須項目です。",
    "extra_forbidden": "想定外の項目です。",
    "enum": "許可されていない値です。",
    "literal_error": "許可されていない値です。",
    "string_too_short": "入力されていません。",
    "string_too_long": "文字数が上限を超えています。",
    "string_type": "文字列で入力してください。",
    "bool_type": "真偽値で入力してください。",
    "bool_parsing": "真偽値で入力してください。",
    "value_error": "入力内容が条件を満たしていません。",
}
_DEFAULT_REASON = "入力値が正しくありません。"


def _field_name(error: dict) -> str:
    parts = [str(part) for part in error.get("loc", ())]
    if parts and parts[0] in _LOCATION_PREFIXES:
        parts = parts[1:]
    # 想定外の項目は、キー名に送信内容が含まれうるため固定の表記に置き換える
    if error.get("type") == "extra_forbidden" and parts:
        parts[-1] = _UNKNOWN_FIELD
    return ".".join(parts) if parts else "body"


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()

    # JSONの形式そのものが不正な場合は、入力値の誤り（422）ではなく400として扱う（§3.6）
    if any(error.get("type") == "json_invalid" for error in errors):
        logger.info("request body is not valid JSON")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "リクエストの形式が正しくありません。",
                }
            },
        )

    details = [
        {
            "field": _field_name(error),
            "reason": _REASONS.get(error.get("type", ""), _DEFAULT_REASON),
        }
        for error in errors
    ]
    # 送信値やエラーの詳細はログに出さず、件数だけを残す
    logger.info("request validation failed: %d error(s)", len(details))
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "入力内容を確認してください。",
                "details": details,
            }
        },
    )


async def service_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    for exception_type, (status, code, message) in _SERVICE_ERRORS.items():
        if isinstance(exc, exception_type):
            # 例外メッセージ・トレースバックはレスポンスにもログにも含めない。
            return JSONResponse(
                status_code=status,
                content={"error": {"code": code, "message": message}},
                headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
            )
    raise exc


def register_exception_handlers(app: FastAPI) -> None:
    """アプリへ共通のエラーハンドラを登録する。"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    for exception_type in _SERVICE_ERRORS:
        app.add_exception_handler(exception_type, service_exception_handler)
