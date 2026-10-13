"""CRUD HTTP tests with real encryption and synthetic, in-memory storage."""

import base64
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.core.exceptions import (
    AccountDeletingError, AuthenticationRequiredError,
    AuthServiceUnavailableError, DatabaseUnavailableError,
)
from app.features.auth.dependencies import get_current_user
from app.features.memos.crypto import encrypt_payload
from app.features.memos.read_router import get_memo_read_repository, router
from app.features.memos.repository import StoredMemo, UserNotActive, UserNotFound
from app.features.memos.router import get_current_user_id, get_memo_cipher

BASE = "/api/v1/memos"
USER = UUID(int=1)
OTHER = UUID(int=2)
NOW = datetime(2026, 10, 13, tzinfo=UTC)
TEXT = "synthetic-private-memo"


def make_row(cipher, *, user_id=USER, memo_id=None, summary=TEXT, created_at=NOW):
    memo_id = memo_id or uuid4()
    payload = dict(event_summary=summary, emotion="synthetic emotion", true_feeling=TEXT,
                   background="", wish=TEXT, handling="hold", reason=None)
    return StoredMemo(
        id=memo_id, user_id=user_id, source_consultation_id=uuid4(),
        encrypted_payload=encrypt_payload(payload, user_id=user_id, memo_id=memo_id, cipher=cipher),
        encryption_version="fernet-v1", key_version="v1", payload_version=1,
        approved_at=NOW, save_consented_at=NOW, created_at=created_at,
    )


class MemoryRepository:
    def __init__(self):
        self.rows = {}
        self.error = None
        self.list_calls = []

    async def find_owned(self, user_id, memo_id):
        if self.error:
            raise self.error
        row = self.rows.get(memo_id)
        return row if row and row.user_id == user_id else None

    async def list_owned(self, user_id, cursor, limit):
        if self.error:
            raise self.error
        self.list_calls.append((user_id, cursor, limit))
        rows = sorted(self.rows.values(), key=lambda row: (row.created_at, row.id), reverse=True)
        return [row for row in rows if row.user_id == user_id and (
            cursor is None or (row.created_at, row.id) < (cursor.created_at, cursor.memo_id)
        )][:limit]

    async def delete_owned(self, user_id, memo_id):
        row = await self.find_owned(user_id, memo_id)
        if row is None:
            return False
        del self.rows[memo_id]
        return True


@pytest.fixture
def setup():
    cipher = Fernet(Fernet.generate_key())
    repo = MemoryRepository()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: USER
    app.dependency_overrides[get_memo_cipher] = lambda: cipher
    app.dependency_overrides[get_memo_read_repository] = lambda: repo
    with TestClient(app) as client:
        yield app, client, repo, cipher


def test_detail_and_delete_lifecycle(setup, caplog):
    app, client, repo, cipher = setup
    caplog.set_level(logging.DEBUG)
    row = make_row(cipher)
    repo.rows[row.id] = row
    response = client.get(f"{BASE}/{row.id}")
    assert response.status_code == 200
    assert response.json()["event_summary"] == TEXT
    assert response.json()["background"] == ""
    assert response.json()["reason"] is None
    assert "encrypted_payload" not in response.json()
    deleted = client.delete(f"{BASE}/{row.id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f"{BASE}/{row.id}").status_code == 404
    assert client.delete(f"{BASE}/{row.id}").status_code == 404
    assert TEXT not in caplog.text
    assert row.encrypted_payload.decode() not in caplog.text


@pytest.mark.parametrize("method", ["get", "delete"])
def test_other_owner_and_absent_have_identical_404(setup, method):
    app, client, repo, cipher = setup
    row = make_row(cipher, user_id=OTHER)
    repo.rows[row.id] = row
    other = getattr(client, method)(f"{BASE}/{row.id}")
    missing = getattr(client, method)(f"{BASE}/{uuid4()}")
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()
    assert row.id in repo.rows


def test_empty_and_cursor_pagination_survive_boundary_deletion(setup):
    app, client, repo, cipher = setup
    assert client.get(BASE).json() == {"memos": [], "next_cursor": None}
    for i in range(1, 23):
        row = make_row(cipher, memo_id=UUID(int=100 + i))
        repo.rows[row.id] = row
    foreign = make_row(cipher, user_id=OTHER, created_at=NOW + timedelta(days=1))
    repo.rows[foreign.id] = foreign
    first = client.get(BASE, params={"user_id": str(OTHER), "limit": 999}).json()
    assert [x["memo_id"] for x in first["memos"]] == [str(UUID(int=i)) for i in range(122, 112, -1)]
    del repo.rows[UUID(int=113)]
    second = client.get(BASE, params={"cursor": first["next_cursor"]}).json()
    third = client.get(BASE, params={"cursor": second["next_cursor"]}).json()
    assert len(second["memos"]) == 10
    assert [x["memo_id"] for x in third["memos"]] == [str(UUID(int=102)), str(UUID(int=101))]
    assert third["next_cursor"] is None
    assert all(call[0] == USER and call[2] == 11 for call in repo.list_calls)


@pytest.mark.parametrize("length", [0, 59, 60, 61, 100])
def test_summary_boundary(setup, length):
    app, client, repo, cipher = setup
    text = "あ" * length
    row = make_row(cipher, summary=text)
    repo.rows[row.id] = row
    summary = client.get(BASE).json()["memos"][0]["summary"]
    assert summary == (text if length <= 60 else text[:59] + "\u2026")


@pytest.mark.parametrize("cursor", ["", "bad!", "a" * 513,
    base64.urlsafe_b64encode(b'{}').decode(),
    base64.urlsafe_b64encode(b'{"created_at":"2026-10-13","memo_id":"bad"}').decode(),
])
def test_invalid_cursor_is_safe_422(setup, cursor):
    app, client, repo, cipher = setup
    response = client.get(BASE, params={"cursor": cursor})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert repo.list_calls == []


@pytest.mark.parametrize("change", ["ciphertext", "memo_id", "user_id", "payload_version"])
@pytest.mark.parametrize("listing", [True, False])
def test_corrupt_or_moved_ciphertext_fails_whole_response(setup, caplog, change, listing):
    app, client, repo, cipher = setup
    row = make_row(cipher, user_id=OTHER if change == "user_id" else USER)
    changes = {"ciphertext": {"encrypted_payload": b"synthetic-corrupt"},
               "memo_id": {"id": uuid4()}, "user_id": {"user_id": USER},
               "payload_version": {"payload_version": 999}}
    row = replace(row, **changes[change])
    repo.rows[row.id] = row
    response = client.get(BASE if listing else f"{BASE}/{row.id}")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert TEXT not in response.text + caplog.text
    assert "synthetic-corrupt" not in response.text + caplog.text


@pytest.mark.parametrize("error,status,code", [
    (AuthenticationRequiredError, 401, "UNAUTHORIZED"),
    (AccountDeletingError, 403, "ACCOUNT_DELETING"),
    (AuthServiceUnavailableError, 503, "AUTH_UNAVAILABLE"),
    (DatabaseUnavailableError, 503, "DB_UNAVAILABLE"),
])
@pytest.mark.parametrize("method,path", [("get", ""), ("get", "/" + str(UUID(int=3))),
                                         ("delete", "/" + str(UUID(int=3)))])
def test_auth_errors_are_preserved(setup, error, status, code, method, path):
    app, client, repo, cipher = setup
    del app.dependency_overrides[get_current_user_id]
    async def fail():
        raise error("synthetic-hidden-token")
    app.dependency_overrides[get_current_user] = fail
    response = getattr(client, method)(BASE + path)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    assert "synthetic-hidden-token" not in response.text


@pytest.mark.parametrize("error,status", [(DatabaseUnavailableError, 503), (RuntimeError, 500),
                                         (UserNotFound, 401), (UserNotActive, 403)])
def test_failed_delete_keeps_row_and_can_retry(setup, caplog, error, status):
    app, client, repo, cipher = setup
    row = make_row(cipher)
    repo.rows[row.id] = row
    repo.error = error("synthetic-db-parameters")
    response = client.delete(f"{BASE}/{row.id}")
    assert response.status_code == status
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    assert "synthetic-db-parameters" not in response.text + caplog.text
    assert row.id in repo.rows
    repo.error = None
    assert client.delete(f"{BASE}/{row.id}").status_code == 204


def test_delete_does_not_require_decryption_key(setup):
    app, client, repo, cipher = setup
    row = make_row(cipher)
    repo.rows[row.id] = row
    def fail():
        raise RuntimeError("key unavailable")
    app.dependency_overrides[get_memo_cipher] = fail
    assert client.delete(f"{BASE}/{row.id}").status_code == 204


def test_owner_check_happens_before_decryption(setup, monkeypatch):
    app, client, repo, cipher = setup
    decrypt = AsyncMock(side_effect=AssertionError("must not decrypt"))
    monkeypatch.setattr("app.features.memos.read_service.decrypt_memo", decrypt)
    assert client.get(f"{BASE}/{uuid4()}").status_code == 404
    decrypt.assert_not_called()
