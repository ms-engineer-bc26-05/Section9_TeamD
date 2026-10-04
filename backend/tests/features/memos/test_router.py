"""メモ保存APIのテスト。

main.py への登録は結合Issue（I-06）で行うため、メモRouterだけを載せたテスト用アプリを使う。
認証は dependency_overrides で固定UUIDのユーザーにし、DBはメモリ上の実装で模す。
テストデータはすべて架空。
"""

import logging
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.consultations.store import get_consultation_store
from app.features.memos.crypto import create_fernet
from app.features.memos.router import (
    get_current_user_id,
    get_memo_cipher,
    get_memo_repository,
    router,
)

from tests.features.consultations.factories import make_save_confirmation_state
from tests.features.memos.fakes import InMemoryMemoRepository

BASE = "/api/v1/consultations"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def store():
    # APIは相談機能の共有ストアを使う。作った一時状態は state フィクスチャの終了時に破棄する
    return get_consultation_store()


@pytest.fixture
def repo():
    return InMemoryMemoRepository()


@pytest.fixture
def app(repo):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    cipher = create_fernet(Fernet.generate_key().decode("ascii"))
    app.dependency_overrides[get_memo_repository] = lambda: repo
    app.dependency_overrides[get_memo_cipher] = lambda: cipher
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def state(store):
    state = make_save_confirmation_state(store, USER_ID)
    yield state
    store.discard(USER_ID, state.consultation_id)


def test_save_returns_201_then_200_on_retry(client, state, store):
    response = client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": "架空の理由"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"memo_id", "created_at", "handling", "reason", "event_summary"}
    assert body["handling"] == "hold"
    assert body["reason"] == "架空の理由"
    assert body["event_summary"] == "架空の出来事の要約"
    assert not store.exists(USER_ID, state.consultation_id)

    retry = client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": None})

    assert retry.status_code == 200
    assert retry.json() == body


def test_blank_reason_is_saved_as_null(client, state):
    response = client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": "   "})

    assert response.status_code == 201
    assert response.json()["reason"] is None


def test_reason_too_long_is_422(client, state, repo):
    response = client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": "あ" * 501})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert repo.rows == {}


def test_server_managed_fields_are_rejected(client, state, repo):
    response = client.post(
        f"{BASE}/{state.consultation_id}/save",
        json={"reason": None, "user_id": str(uuid4()), "approved": True},
    )

    assert response.status_code == 422
    assert repo.rows == {}


def test_unauthenticated_is_401(app, state, repo):
    del app.dependency_overrides[get_current_user_id]

    response = TestClient(app).post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert repo.rows == {}


def test_other_users_state_is_404(app, state, repo):
    app.dependency_overrides[get_current_user_id] = lambda: uuid4()

    response = TestClient(app).post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONSULTATION_NOT_FOUND"
    assert repo.rows == {}


def test_unapproved_state_is_409(client, state, repo):
    state.handling = None

    response = client.post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSULTATION_STATE_CONFLICT"
    assert repo.rows == {}


def test_missing_key_is_500_without_details(app, state, repo, monkeypatch):
    del app.dependency_overrides[get_memo_cipher]
    monkeypatch.delenv("MEMO_ENCRYPTION_KEY", raising=False)

    response = TestClient(app).post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "メモを保存できませんでした。時間をおいてもう一度お試しください。",
        }
    }
    assert repo.rows == {}


def test_commit_failure_is_not_reported_as_saved(app, state, repo, store):
    repo.commit_error = RuntimeError("fake commit failure")

    response = TestClient(app, raise_server_exceptions=False).post(
        f"{BASE}/{state.consultation_id}/save", json={}
    )

    assert response.status_code == 500
    assert "架空" not in response.text
    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)


def test_does_not_log_memo_content_or_ciphertext(client, state, repo, caplog):
    caplog.set_level(logging.DEBUG)

    client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": "架空の理由"})
    client.post(f"{BASE}/{state.consultation_id}/save", json={})
    client.post(f"{BASE}/{uuid4()}/save", json={"reason": "架空の理由"})

    row = next(iter(repo.rows.values()))
    assert "架空" not in caplog.text
    assert row.encrypted_payload.decode("ascii") not in caplog.text
