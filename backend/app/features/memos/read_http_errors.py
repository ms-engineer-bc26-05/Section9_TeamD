"""Fixed CRUD errors without storage contents or exception messages."""

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
from app.features.memos.read_cursor import InvalidMemoCursor
from app.features.memos.read_service import MemoNotFound
from app.features.memos.repository import UserNotActive, UserNotFound

logger = logging.getLogger(__name__)


class MemoReadRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except (RequestValidationError, HTTPException, AuthenticationRequiredError,
                    AccountDeletingError, AuthServiceUnavailableError, DatabaseUnavailableError):
                raise
            except UserNotFound:
                raise AuthenticationRequiredError from None
            except UserNotActive:
                raise AccountDeletingError from None
            except MemoNotFound:
                return JSONResponse(status_code=404, content={"error": {
                    "code": "MEMO_NOT_FOUND", "message": "メモが見つかりません。",
                }})
            except InvalidMemoCursor:
                return JSONResponse(status_code=422, content={"error": {
                    "code": "VALIDATION_ERROR", "message": "入力内容を確認してください。",
                    "details": [{"field": "cursor", "reason": "入力値が正しくありません。"}],
                }})
            except Exception:
                logger.error("memo read operation failed")
                return JSONResponse(status_code=500, content={"error": {
                    "code": INTERNAL_ERROR_CODE, "message": INTERNAL_ERROR_MESSAGE,
                }})

        return route_handler
