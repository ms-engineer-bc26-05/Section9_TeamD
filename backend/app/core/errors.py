"""共通のエラーハンドラ。

FastAPI既定の422ハンドラは、失敗した項目の送信値（input）をレスポンスへ含めるため、
相談内容などがエラー本文に混入するおそれがある。
そのため独自のハンドラで上書きし、API設計書（ドラフト）§3.5の形式で、
送信値を含まない固定の文言だけを返す。ログにも送信値は出さない。

想定外の例外（500）は、InternalErrorMiddleware で受け止めて同じ形式で返す（#86）。
FastAPIの add_exception_handler(Exception, ...) を使うと、Starlette がログのために
例外を投げ直し、サーバーのログに例外のメッセージ（入力値を含みうる）が出るため使わない。
"""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# 想定外の例外（500）のときに返す固定の内容
INTERNAL_ERROR_STATUS = 500
INTERNAL_ERROR_CODE = "INTERNAL_SERVER_ERROR"
INTERNAL_ERROR_MESSAGE = "エラーが発生しました。時間をおいてもう一度お試しください。"

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


def _innermost(exc: BaseException) -> BaseException:
    """非同期処理でまとめられた例外（ExceptionGroup）から、元の例外を取り出す"""
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


def _error_location(exc: BaseException) -> str:
    """例外が起きた場所（ファイル名・行番号・関数名）。例外のメッセージや変数の値は含めない"""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    frame = frames[-1]
    return f"{frame.filename}:{frame.lineno} in {frame.name}"


class InternalErrorMiddleware:
    """想定外の例外を受け止め、500の共通エラー形式で返す（#86）。

    - レスポンス本文は固定の内容だけにする（例外のメッセージ・入力値を含めない）
    - ログには例外の種類と、起きた場所だけを出す（例外のメッセージは入力値を含みうるため出さない）
    - 例外を投げ直さないため、サーバー（uvicorn）がトレースバックをログに出さない
    - 各機能の例外ハンドラ（422・404・409・502など）で処理された例外は、ここまで届かない
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            cause = _innermost(exc)
            logger.error(
                "unhandled error: %s at %s (%s %s)",
                type(cause).__name__,
                _error_location(cause),
                scope.get("method"),
                scope.get("path"),
            )
            if response_started:
                # すでに応答を送り始めている場合は、別の応答を送れないため、ここで打ち切る
                return
            response = JSONResponse(
                status_code=INTERNAL_ERROR_STATUS,
                content={
                    "error": {
                        "code": INTERNAL_ERROR_CODE,
                        "message": INTERNAL_ERROR_MESSAGE,
                    }
                },
            )
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    """アプリへ共通のエラーハンドラを登録する。

    main.py では、この関数の後に CORSMiddleware を追加する。後から追加したミドルウェアほど
    外側になるため、500の応答にもCORSのヘッダーが付き、ブラウザ（画面）が本文を読める。
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_middleware(InternalErrorMiddleware)
