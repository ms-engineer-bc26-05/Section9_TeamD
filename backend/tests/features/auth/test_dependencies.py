"""認証入口のテスト。Firebase・DBには接続しない。"""

from unittest.mock import AsyncMock, Mock

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import register_exception_handlers
from app.features.auth import service
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser

import pytest

from uuid import uuid4
from app.features.auth import dependencies

from app.core.exceptions import AccountDeletingError

from app.core.exceptions import (
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic dummy", "Bearer", "Bearer   "],
)
async def test_missing_token_returns_401_without_firebase_or_db(
    monkeypatch, authorization
):
    verify = AsyncMock(side_effect=AssertionError("Firebase must not be called"))
    factory = Mock(side_effect=AssertionError("DB must not be called"))
    monkeypatch.setattr(service, "to_thread", verify)
    monkeypatch.setattr(service, "get_session_factory", factory)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/private")
    async def private(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": str(user.user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        headers = {}
        if authorization is not None:
            headers["Authorization"] = authorization
        response = await client.get("/private", headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "ログインしてください。",
        }
    }
    assert response.headers["www-authenticate"] == "Bearer"
    verify.assert_not_called()
    factory.assert_not_called()


async def test_authenticated_user_returns_internal_uuid(monkeypatch):
    user = CurrentUser(user_id=uuid4())
    authenticate = AsyncMock(return_value=user)
    monkeypatch.setattr(dependencies, "authenticate_user", authenticate)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/private")
    async def private(current_user: CurrentUser = Depends(get_current_user)):
        return {"user_id": str(current_user.user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/private",
            headers={"Authorization": "Bearer dummy-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.user_id)}
    authenticate.assert_awaited_once_with("dummy-token")


async def test_current_user_can_be_overridden(monkeypatch):
    authenticate = AsyncMock(
        side_effect=AssertionError("Authentication must not be called")
    )
    monkeypatch.setattr(dependencies, "authenticate_user", authenticate)

    user = CurrentUser(user_id=uuid4())
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/private")
    async def private(current_user: CurrentUser = Depends(get_current_user)):
        return {"user_id": str(current_user.user_id)}

    def override_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/private")

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.user_id)}
    authenticate.assert_not_called()


async def test_deleting_user_returns_403_without_details(monkeypatch, caplog):
    marker = "DUMMY_PRIVATE_ERROR_MARKER"
    authenticate = AsyncMock(
        side_effect=AccountDeletingError(marker)
    )
    monkeypatch.setattr(dependencies, "authenticate_user", authenticate)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/private")
    async def private(current_user: CurrentUser = Depends(get_current_user)):
        return {"user_id": str(current_user.user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/private",
            headers={"Authorization": "Bearer dummy-token"},
        )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "ACCOUNT_DELETING",
            "message": "退会処理中のため利用できません。",
        }
    }
    assert "www-authenticate" not in response.headers
    assert marker not in response.text
    assert marker not in caplog.text


@pytest.mark.parametrize(
    ("error_type", "code", "message"),
    [
        (
            AuthServiceUnavailableError,
            "AUTH_UNAVAILABLE",
            "認証サービスを利用できません。時間をおいて再度お試しください。",
        ),
        (
            DatabaseUnavailableError,
            "DB_UNAVAILABLE",
            "データベースに接続できませんでした。",
        ),
    ],
)
async def test_service_unavailable_returns_503_without_details(
    monkeypatch, caplog, error_type, code, message
):
    marker = "DUMMY_PRIVATE_ERROR_MARKER"
    authenticate = AsyncMock(side_effect=error_type(marker))
    monkeypatch.setattr(dependencies, "authenticate_user", authenticate)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/private")
    async def private(current_user: CurrentUser = Depends(get_current_user)):
        return {"user_id": str(current_user.user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/private",
            headers={"Authorization": "Bearer dummy-token"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": code, "message": message}
    }
    assert "www-authenticate" not in response.headers
    assert marker not in response.text
    assert marker not in caplog.text
