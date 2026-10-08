"""ユーザーAPIのテスト。Firebase・DBへは接続しない。"""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import register_exception_handlers
from app.features.users import router as users_router
from app.features.users.schemas import UserResponse

from app.core.exceptions import (
    AccountDeletingError,
    AuthenticationRequiredError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)


@pytest.mark.parametrize(
    ("created", "expected_status"),
    [(True, 201), (False, 200)],
)
async def test_register_user_returns_response(
    monkeypatch, created, expected_status
):
    user_id = UUID("11111111-1111-4111-8111-111111111111")
    user = UserResponse(user_id=user_id, has_seen_notice=False)
    register = AsyncMock(return_value=(user, created))
    monkeypatch.setattr(users_router, "register_or_get_user", register)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer dummy-token"},
        )

    assert response.status_code == expected_status
    assert response.json() == {
        "user_id": str(user_id),
        "has_seen_notice": False,
    }
    register.assert_awaited_once_with("dummy-token")


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic dummy", "Bearer", "Bearer   "],
)
async def test_register_user_rejects_missing_token(
    monkeypatch, authorization
):
    register = AsyncMock(
        side_effect=AssertionError("Registration must not be called")
    )
    monkeypatch.setattr(users_router, "register_or_get_user", register)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")

    headers = {}
    if authorization is not None:
        headers["Authorization"] = authorization

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/users/me",
            headers=headers,
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "ログインしてください。",
        }
    }
    assert response.headers["www-authenticate"] == "Bearer"
    register.assert_not_awaited()
    register.assert_not_called()


@pytest.mark.parametrize(
    ("error_type", "expected_status", "code", "message"),
    [
        (
            AuthenticationRequiredError,
            401,
            "UNAUTHORIZED",
            "ログインしてください。",
        ),
        (
            AccountDeletingError,
            403,
            "ACCOUNT_DELETING",
            "退会処理中のため利用できません。",
        ),
        (
            AuthServiceUnavailableError,
            503,
            "AUTH_UNAVAILABLE",
            "認証サービスを利用できません。時間をおいて再度お試しください。",
        ),
        (
            DatabaseUnavailableError,
            503,
            "DB_UNAVAILABLE",
            "データベースに接続できませんでした。",
        ),
    ],
)
async def test_register_user_returns_safe_error(
    monkeypatch, caplog, error_type, expected_status, code, message
):
    marker = "DUMMY_PRIVATE_ERROR"
    register = AsyncMock(side_effect=error_type(marker))
    monkeypatch.setattr(users_router, "register_or_get_user", register)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer dummy-token"},
        )

    assert response.status_code == expected_status
    assert response.json() == {
        "error": {"code": code, "message": message}
    }
    assert marker not in response.text
    assert marker not in caplog.text
    assert "dummy-token" not in response.text
    assert "dummy-token" not in caplog.text
    register.assert_awaited_once_with("dummy-token")

    if expected_status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
