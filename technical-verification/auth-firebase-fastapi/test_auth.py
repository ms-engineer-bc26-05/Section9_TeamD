from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app as target


# 実際の認証情報ではなく、テスト専用のダミー文字列。
TEST_TOKEN = "dummy-token-for-local-test"
HEADERS = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VERIFICATION_OWNER_UID", "fictional-user-a")

    # 実際のFirebase初期化とトークン検証は呼び出さない。
    with patch.object(target, "get_firebase_app", return_value=object()):
        with patch.object(target.auth, "verify_id_token") as verify:
            verify.return_value = {"uid": "fictional-user-a"}
            with TestClient(target.app) as test_client:
                yield test_client, verify


def test_health(client):
    api, verify = client

    response = api.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    verify.assert_not_called()


def test_valid_token(client):
    api, verify = client

    response = api.get("/private", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    assert verify.call_args.args == (TEST_TOKEN,)
    assert verify.call_args.kwargs["check_revoked"] is False
    assert TEST_TOKEN not in response.text


def test_missing_token(client):
    api, verify = client

    response = api.get("/private")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    verify.assert_not_called()


def test_wrong_authentication_scheme(client):
    api, verify = client

    response = api.get(
        "/private",
        headers={"Authorization": "Basic dummy-value"},
    )

    assert response.status_code == 401
    verify.assert_not_called()


@pytest.mark.parametrize("failure", ["invalid", "expired"])
def test_rejected_token(client, caplog, failure):
    api, verify = client

    if failure == "expired":
        error = target.auth.ExpiredIdTokenError(
            f"Expired: {TEST_TOKEN}", None
        )
    else:
        error = target.auth.InvalidIdTokenError(
            f"Invalid: {TEST_TOKEN}"
        )

    verify.side_effect = error

    response = api.get("/private", headers=HEADERS)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert TEST_TOKEN not in response.text
    assert TEST_TOKEN not in caplog.text


@pytest.mark.parametrize("uid", [None, "", 123])
def test_invalid_uid(client, uid):
    api, verify = client
    verify.return_value = {"uid": uid}

    response = api.get("/private", headers=HEADERS)

    assert response.status_code == 401


def test_verification_failure(client, caplog):
    api, verify = client
    verify.side_effect = RuntimeError(
        f"Internal failure: {TEST_TOKEN}"
    )

    response = api.get("/private", headers=HEADERS)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Authentication service unavailable"
    }
    assert TEST_TOKEN not in response.text
    assert TEST_TOKEN not in caplog.text


def test_configuration_failure(client, caplog):
    api, verify = client

    with patch.object(
        target,
        "get_firebase_app",
        side_effect=RuntimeError("private-configuration-marker"),
    ):
        response = api.get("/private", headers=HEADERS)

    assert response.status_code == 503
    assert "private-configuration-marker" not in response.text
    assert "private-configuration-marker" not in caplog.text
    verify.assert_not_called()


def test_owner_can_read_memo(client, caplog):
    api, _ = client

    response = api.get("/memos/sample-memo", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "id": "sample-memo",
        "text": "これは認可確認用の架空メモです。",
    }
    assert "owner_uid" not in response.json()
    assert response.json()["text"] not in caplog.text


def test_other_user_cannot_read_memo(client, caplog):
    api, verify = client
    verify.return_value = {"uid": "fictional-user-b"}

    response = api.get("/memos/sample-memo", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "Memo not found"}
    assert "架空メモ" not in response.text
    assert TEST_TOKEN not in caplog.text


def test_missing_memo(client):
    api, _ = client

    response = api.get("/memos/not-found", headers=HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "Memo not found"}


def test_memo_requires_authentication(client):
    api, verify = client

    response = api.get("/memos/sample-memo")

    assert response.status_code == 401
    verify.assert_not_called()


def test_missing_owner_configuration(client, monkeypatch):
    api, _ = client
    monkeypatch.delenv("VERIFICATION_OWNER_UID")

    response = api.get("/memos/sample-memo", headers=HEADERS)

    assert response.status_code == 503