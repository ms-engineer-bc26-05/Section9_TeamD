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

logger = logging.getLogger(__name__)

# locの先頭に入る「どこから来た値か」を表す要素。項目名には含めない
_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}

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


def _field_name(loc: tuple) -> str:
    parts = [str(part) for part in loc]
    if parts and parts[0] in _LOCATION_PREFIXES:
        parts = parts[1:]
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
            "field": _field_name(error.get("loc", ())),
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


def register_exception_handlers(app: FastAPI) -> None:
    """アプリへ共通のエラーハンドラを登録する。"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)