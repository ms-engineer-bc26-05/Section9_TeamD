"""メモ保存APIのテスト。

main.py への登録は結合Issue（I-06）で行うため、メモRouterだけを載せたテスト用アプリを使う。
認証は dependency_overrides で固定UUIDのユーザーにし、DBはメモリ上の実装で模す。
テストデータはすべて架空。
"""

import dataclasses
import logging
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.core.exceptions import (
    AccountDeletingError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)
from app.features.auth.dependencies import get_current_user
from app.features.consultations.store import get_consultation_store
from app.features.memos.crypto import create_fernet
from app.features.memos.router import (
    get_current_user_id,
    get_memo_cipher,
    get_memo_limit_getter,
    get_memo_repository,
    router,
)
from app.features.usage.exceptions import PlanUnavailable

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


def test_reason_up_to_500_chars_is_saved_without_truncation(client, state):
    response = client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": "あ" * 500})

    assert response.status_code == 201
    assert response.json()["reason"] == "あ" * 500


def test_reason_too_long_is_422_without_sent_value(client, state, repo, store):
    reason = ("架空の理由" * 101)[:501]

    response = client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": reason})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    # 送信値をエラー本文に含めない
    assert "架空" not in response.text
    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)


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


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (AccountDeletingError, 403, "ACCOUNT_DELETING"),
        (AuthServiceUnavailableError, 503, "AUTH_UNAVAILABLE"),
        (DatabaseUnavailableError, 503, "DB_UNAVAILABLE"),
    ],
)
def test_auth_errors_keep_common_code(app, state, repo, store, error, status_code, code):
    # I-01の認証依存の例外を500に変換せず、共通のエラーハンドラのcodeで返す
    del app.dependency_overrides[get_current_user_id]

    async def raise_error():
        raise error("架空の内部情報")

    app.dependency_overrides[get_current_user] = raise_error

    response = TestClient(app).post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert "架空の内部情報" not in response.text
    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)


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


@pytest.mark.parametrize(
    ("status", "status_code", "error"),
    [
        (None, 401, {"code": "UNAUTHORIZED", "message": "ログインしてください。"}),
        (
            "deleting",
            403,
            {"code": "ACCOUNT_DELETING", "message": "退会処理中のため利用できません。"},
        ),
    ],
    ids=["user-missing", "deleting"],
)
def test_user_changed_after_auth_is_rejected(client, state, repo, store, status, status_code, error):
    repo.user_statuses[USER_ID] = status

    response = client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": "架空の理由"})

    assert response.status_code == status_code
    assert response.json() == {"error": error}
    if status_code == 401:
        # 共通のエラーハンドラの401と同じく、WWW-Authenticate ヘッダーを付ける
        assert response.headers["WWW-Authenticate"] == "Bearer"
    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)


def test_missing_key_is_500_without_details(app, state, repo, monkeypatch):
    del app.dependency_overrides[get_memo_cipher]
    monkeypatch.delenv("MEMO_ENCRYPTION_KEY", raising=False)

    response = TestClient(app).post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "メモを保存できませんでした。時間をおいてもう一度お試しください。",
        }
    }
    assert repo.rows == {}


def test_ciphertext_moved_to_another_memo_is_500_without_details(client, state, repo):
    client.post(f"{BASE}/{state.consultation_id}/save", json={"reason": "架空の理由"})
    key = (USER_ID, state.consultation_id)
    repo.rows[key] = dataclasses.replace(repo.rows[key], id=uuid4())

    response = client.post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "架空" not in response.text


def test_commit_failure_is_500_without_details(client, state, repo, store, caplog):
    caplog.set_level(logging.DEBUG)
    # DBの例外はメッセージにSQLのパラメータ（暗号文）を含みうる
    repo.commit_error = RuntimeError("fake commit failure: secret-parameter")

    response = client.post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "メモを保存できませんでした。時間をおいてもう一度お試しください。",
        }
    }
    assert "secret-parameter" not in caplog.text
    assert "Traceback" not in caplog.text
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


def set_limit(app, limit):
    async def get_limit(user_id):
        return limit

    app.dependency_overrides[get_memo_limit_getter] = lambda: get_limit


def test_limit_exceeded_is_403_and_keeps_state(app, repo, store):
    # SV-06：上限を超える保存は403。INSERTせず、一時状態も残す（保存せず終了を選べる）
    set_limit(app, 1)
    client = TestClient(app)
    first = make_save_confirmation_state(store, USER_ID)
    assert client.post(f"{BASE}/{first.consultation_id}/save", json={}).status_code == 201
    second = make_save_confirmation_state(store, USER_ID)
    try:
        response = client.post(f"{BASE}/{second.consultation_id}/save", json={})

        assert response.status_code == 403
        assert response.json() == {
            "error": {
                "code": "MEMO_LIMIT_EXCEEDED",
                "message": "保存できる整理メモの上限に達しました。",
            }
        }
        assert len(repo.rows) == 1
        assert store.exists(USER_ID, second.consultation_id)
    finally:
        store.discard(USER_ID, second.consultation_id)


def test_retry_at_limit_returns_200(app, state, repo):
    set_limit(app, 1)
    client = TestClient(app)
    first = client.post(f"{BASE}/{state.consultation_id}/save", json={})

    retry = client.post(f"{BASE}/{state.consultation_id}/save", json={})

    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert len(repo.rows) == 1


def test_plan_unavailable_is_503(app, state, repo, store):
    # プランを確認できない場合は、無料・無制限とみなさず503
    async def get_limit(user_id):
        raise PlanUnavailable

    app.dependency_overrides[get_memo_limit_getter] = lambda: get_limit

    response = TestClient(app).post(f"{BASE}/{state.consultation_id}/save", json={})

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "DB_UNAVAILABLE", "message": "データベースに接続できませんでした。"}
    }
    assert repo.rows == {}
    assert store.exists(USER_ID, state.consultation_id)
