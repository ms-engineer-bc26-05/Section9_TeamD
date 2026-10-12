"""SDKの形式チェックを確認する。実通信・実際の認証情報は使わない。"""

from unittest.mock import Mock

import pytest
from firebase_admin import _token_gen, auth

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import register_exception_handlers
from app.features.auth import service
from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.integrations.firebase import client as firebase_client


@pytest.mark.parametrize("token", ["dummy-not-a-token", "a.b.c"])
def test_sdk_rejects_malformed_token_without_network(monkeypatch, token):
    app = Mock()
    app.options = {}
    app.project_id = "dummy-project"

    request = Mock(
        side_effect=AssertionError("Network must not be called")
    )
    monkeypatch.setattr(
        _token_gen,
        "CertificateFetchRequest",
        Mock(return_value=request),
    )
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)

    verifier = _token_gen.TokenVerifier(app)

    with pytest.raises(auth.InvalidIdTokenError):
        verifier.verify_id_token(token)

    request.assert_not_called()


@pytest.mark.parametrize("token", ["dummy-not-a-token", "a.b.c"])
async def test_malformed_token_returns_401(monkeypatch, caplog, token):
    firebase_app = Mock()
    firebase_app.options = {}
    firebase_app.project_id = "dummy-project"
    request = Mock(side_effect=AssertionError("Network must not be called"))
    monkeypatch.setattr(
        _token_gen, "CertificateFetchRequest", Mock(return_value=request)
    )
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    verifier = _token_gen.TokenVerifier(firebase_app)

    def verify_with_sdk(value, *, app, check_revoked):
        assert app is firebase_app
        assert check_revoked is False
        return verifier.verify_id_token(value)

    monkeypatch.setattr(
        firebase_client, "get_firebase_app", Mock(return_value=firebase_app)
    )
    monkeypatch.setattr(auth, "verify_id_token", verify_with_sdk)
    factory = Mock(side_effect=AssertionError("DB must not be called"))
    monkeypatch.setattr(service, "get_session_factory", factory)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/private")
    async def private(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": str(user.user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        response = await http.get(
            "/private", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "ログインしてください。"}
    }
    assert response.headers["www-authenticate"] == "Bearer"
    assert token not in response.text
    assert token not in caplog.text
    request.assert_not_called()
    factory.assert_not_called()
