"""Deletion-only error mapping; no exception text or account identifiers."""

import logging

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
from app.features.payments.public import PaymentSettlementBlocked, StripeUnavailable
from app.features.usage.exceptions import UsageStoreUnavailable
from app.features.users.deletion_repository import DeletionBlocked
from app.features.users.lifecycle_lock import DeletionInProgress

logger = logging.getLogger(__name__)


class DeletionRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                return await handler(request)
            except (
                RequestValidationError,
                HTTPException,
                AuthenticationRequiredError,
                AccountDeletingError,
                AuthServiceUnavailableError,
                DatabaseUnavailableError,
            ):
                raise
            except (DeletionBlocked, PaymentSettlementBlocked):
                status, code = 409, "ACCOUNT_DELETION_BLOCKED"
                message = "現在は退会を完了できません。決済状態を確認して再試行してください。"
            except DeletionInProgress:
                status, code = 409, "ACCOUNT_DELETION_IN_PROGRESS"
                message = "退会処理を実行中です。しばらくしてから再試行してください。"
            except StripeUnavailable:
                status, code = 503, "PAYMENT_UNAVAILABLE"
                message = "決済サービスに接続できませんでした。時間をおいて再度お試しください。"
            except UsageStoreUnavailable:
                status, code = 503, "USAGE_UNAVAILABLE"
                message = "利用状況を確認できませんでした。時間をおいて再度お試しください。"
            except Exception:
                logger.error("account deletion failed")
                status, code, message = 500, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE
            return JSONResponse(
                status_code=status, content={"error": {"code": code, "message": message}}
            )

        return handle
