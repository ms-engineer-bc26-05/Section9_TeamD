"""ユーザーAPIのテスト。Firebase・DBへは接続しない。"""

from unittest.mock import AsyncMock, Mock, call
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

from app.features.auth.schemas import CurrentUser

from app.features.auth import dependencies as auth_dependencies

from firebase_admin import exceptions as firebase_exceptions

from app.features.auth import service as auth_service
from app.integrations.firebase import client as firebase_client

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


async def test_update_notice_returns_response(monkeypatch):
    user_id = UUID("11111111-1111-4111-8111-111111111111")
    session = Mock()
    update = AsyncMock(
        return_value=UserResponse(
            user_id=user_id,
            has_seen_notice=True,
        )
    )
    monkeypatch.setattr(users_router, "update_user_notice", update)

    async def override_current_user():
        return CurrentUser(user_id=user_id)

    async def override_session():
        yield session

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")
    app.dependency_overrides[users_router.get_current_user] = (
        override_current_user
    )
    app.dependency_overrides[users_router.get_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"has_seen_notice": True},
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": str(user_id),
        "has_seen_notice": True,
    }
    update.assert_awaited_once_with(session, user_id)


@pytest.mark.parametrize(
    "payload",
    [
        {"has_seen_notice": False},
        {"has_seen_notice": "true"},
        {"has_seen_notice": 1},
        {"has_seen_notice": None},
        {},
        {
            "has_seen_notice": True,
            "user_id": "22222222-2222-4222-8222-222222222222",
        },
    ],
)
async def test_update_notice_rejects_invalid_input(monkeypatch, payload):
    update = AsyncMock(
        side_effect=AssertionError("Update must not be called")
    )
    monkeypatch.setattr(users_router, "update_user_notice", update)

    async def override_current_user():
        return CurrentUser(
            user_id=UUID("11111111-1111-4111-8111-111111111111")
        )

    async def override_session():
        yield Mock()

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")
    app.dependency_overrides[users_router.get_current_user] = (
        override_current_user
    )
    app.dependency_overrides[users_router.get_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/v1/users/me",
            json=payload,
        )

    assert response.status_code == 422
    update.assert_not_called()


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic dummy", "Bearer", "Bearer   "],
)
async def test_update_notice_rejects_missing_token(
    monkeypatch, authorization
):
    authenticate = AsyncMock(
        side_effect=AssertionError("Authentication service must not be called")
    )
    update = AsyncMock(
        side_effect=AssertionError("Update must not be called")
    )
    monkeypatch.setattr(
        auth_dependencies, "authenticate_user", authenticate
    )
    monkeypatch.setattr(users_router, "update_user_notice", update)

    def reject_session():
        raise AssertionError("DB session must not be requested")

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")
    app.dependency_overrides[users_router.get_session] = reject_session

    headers = {}
    if authorization is not None:
        headers["Authorization"] = authorization

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"has_seen_notice": True},
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
    authenticate.assert_not_called()
    update.assert_not_called()


@pytest.mark.parametrize(
    ("error_type", "status", "code", "message"),
    [
        (
            AuthenticationRequiredError, 401, "UNAUTHORIZED",
            "ログインしてください。",
        ),
        (
            AccountDeletingError, 403, "ACCOUNT_DELETING",
            "退会処理中のため利用できません。",
        ),
        (
            DatabaseUnavailableError, 503, "DB_UNAVAILABLE",
            "データベースに接続できませんでした。",
        ),
    ],
)
async def test_update_notice_returns_safe_error(
    monkeypatch, caplog, error_type, status, code, message
):
    user_id = UUID("11111111-1111-4111-8111-111111111111")
    session = Mock()
    marker = "DUMMY_PRIVATE_ERROR"
    update = AsyncMock(side_effect=error_type(marker))
    monkeypatch.setattr(users_router, "update_user_notice", update)

    async def override_current_user():
        return CurrentUser(user_id=user_id)

    async def override_session():
        yield session

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")
    app.dependency_overrides[users_router.get_current_user] = (
        override_current_user
    )
    app.dependency_overrides[users_router.get_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.patch(
            "/api/v1/users/me",
            json={"has_seen_notice": True},
        )

    assert response.status_code == status
    assert response.json() == {
        "error": {"code": code, "message": message}
    }
    assert marker not in response.text
    assert marker not in caplog.text
    update.assert_awaited_once_with(session, user_id)
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("stage", [0, 1])
async def test_register_permission_denied_returns_503(monkeypatch, caplog, stage):
    marker = "DUMMY_PERMISSION_ERROR"
    firebase_app = Mock()
    verify = Mock(
        side_effect=[{"uid": "dummy-firebase-uid"}] * stage
        + [firebase_exceptions.PermissionDeniedError(marker)]
    )
    factory = Mock(side_effect=AssertionError("DB must not be called"))

    monkeypatch.setattr(
        firebase_client, "get_firebase_app",
        Mock(return_value=firebase_app),
    )
    monkeypatch.setattr(firebase_client.auth, "verify_id_token", verify)
    monkeypatch.setattr(auth_service, "get_session_factory", factory)

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

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "AUTH_UNAVAILABLE",
            "message": (
                "認証サービスを利用できません。"
                "時間をおいて再度お試しください。"
            ),
        }
    }
    assert "www-authenticate" not in response.headers
    assert marker not in response.text
    assert marker not in caplog.text
    assert "dummy-token" not in response.text
    assert "dummy-token" not in caplog.text
    expected_calls = [
        call("dummy-token", app=firebase_app, check_revoked=False),
        call("dummy-token", app=firebase_app, check_revoked=True),
    ]
    assert verify.call_args_list == expected_calls[: stage + 1]
    factory.assert_not_called()
