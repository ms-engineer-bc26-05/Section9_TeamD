"""Firebase連携のテスト。実通信・実際の認証情報は使わない。"""

from unittest.mock import Mock

import pytest

from app.integrations.firebase import client

from firebase_admin import exceptions as firebase_exceptions


@pytest.fixture(autouse=True)
def firebase_mocks(monkeypatch):
    app = Mock()
    get_app = Mock(return_value=app)
    verify = Mock(return_value={"uid": "dummy-firebase-uid"})

    monkeypatch.setattr(client, "get_firebase_app", get_app)
    monkeypatch.setattr(client.auth, "verify_id_token", verify)

    return app, get_app, verify


@pytest.mark.parametrize("check_revoked", [False, True])
def test_verify_token_returns_uid(firebase_mocks, check_revoked):
    app, get_app, verify = firebase_mocks

    uid = client.verify_token(
        "dummy-token",
        check_revoked=check_revoked,
    )

    assert uid == "dummy-firebase-uid"
    get_app.assert_called_once_with()
    verify.assert_called_once_with(
        "dummy-token",
        app=app,
        check_revoked=check_revoked,
    )


@pytest.mark.parametrize("token", ["", "   ", None])
def test_empty_token_does_not_call_firebase(firebase_mocks, token):
    _, get_app, verify = firebase_mocks

    with pytest.raises(client.InvalidTokenError):
        client.verify_token(token, check_revoked=False)

    get_app.assert_not_called()
    verify.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        client.auth.InvalidIdTokenError("DUMMY_SECRET_MARKER"),
        client.auth.ExpiredIdTokenError("DUMMY_SECRET_MARKER", None),
        client.auth.RevokedIdTokenError("DUMMY_SECRET_MARKER"),
        client.auth.UserDisabledError("DUMMY_SECRET_MARKER"),
        client.auth.UserNotFoundError("DUMMY_SECRET_MARKER"),
        ValueError("DUMMY_SECRET_MARKER"),
    ],
)
def test_invalid_token_errors_hide_details(firebase_mocks, error, caplog):
    _, _, verify = firebase_mocks
    verify.side_effect = error

    with pytest.raises(client.InvalidTokenError) as caught:
        client.verify_token("dummy-token", check_revoked=True)

    assert str(caught.value) == "Invalid authentication token"
    assert "DUMMY_SECRET_MARKER" not in str(caught.value)
    assert "DUMMY_SECRET_MARKER" not in caplog.text
    assert "dummy-token" not in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        client.auth.CertificateFetchError("DUMMY_SECRET_MARKER", None),
        firebase_exceptions.PermissionDeniedError("DUMMY_SECRET_MARKER"),
        ConnectionError("DUMMY_SECRET_MARKER"),
        RuntimeError("DUMMY_SECRET_MARKER"),
    ],
)
def test_service_errors_hide_details(firebase_mocks, error, caplog):
    _, _, verify = firebase_mocks
    verify.side_effect = error

    with pytest.raises(client.AuthServiceUnavailableError) as caught:
        client.verify_token("dummy-token", check_revoked=True)

    assert str(caught.value) == "Authentication service unavailable"
    assert "DUMMY_SECRET_MARKER" not in str(caught.value)
    assert "DUMMY_SECRET_MARKER" not in caplog.text
    assert "dummy-token" not in caplog.text


@pytest.mark.parametrize(
    "decoded",
    [
        {},
        {"uid": None},
        {"uid": ""},
        {"uid": "   "},
        {"uid": 123},
        {"uid": "x" * 129},
        None,
        [],
    ],
)
def test_invalid_uid_is_rejected(firebase_mocks, decoded):
    _, _, verify = firebase_mocks
    verify.return_value = decoded

    with pytest.raises(client.InvalidTokenError) as caught:
        client.verify_token("dummy-token", check_revoked=False)

    assert str(caught.value) == "Invalid authentication token"
