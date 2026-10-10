"""共通エラーハンドラ（422・400）のテスト。

入力を受け取るAPIはまだないため、テスト用の仮APIで確認する。
送信した値がレスポンス・ログに含まれないことを、目印の文字列で確認する。
"""

import logging
from typing import Optional

import pytest

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import register_exception_handlers
from app.core.exceptions import (
    AccountDeletingError,
    AuthenticationRequiredError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)
from app.main import app as main_app

# レスポンス・ログに含まれてはいけない目印（架空の値）
MARKER = "PORORI_TEST_MARKER_001"


class DummyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: str = Field(pattern="^(communication|other)$")
    detail: str = Field(min_length=1, max_length=10)
    note: Optional[str] = None


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/dummy")
    async def dummy(body: DummyInput) -> dict:
        return {"ok": True}

    return app


async def _post(json=None, content=None):
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        if content is not None:
            return await client.post(
                "/dummy", content=content, headers={"Content-Type": "application/json"}
            )
        return await client.post("/dummy", json=json)


def test_main_app_registers_handler():
    assert RequestValidationError in main_app.exception_handlers


async def test_valid_input_passes():
    response = await _post(json={"theme": "other", "detail": "ok"})

    assert response.status_code == 200


async def test_too_long_input_returns_422_without_input(caplog):
    response = await _post(json={"theme": "other", "detail": MARKER})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"] == [
        {"field": "detail", "reason": "文字数が上限を超えています。"}
    ]
    assert MARKER not in response.text
    assert MARKER not in caplog.text


async def test_missing_and_extra_fields_return_422():
    response = await _post(json={"theme": "other", "unexpected": "x"})

    assert response.status_code == 422
    fields = {d["field"]: d["reason"] for d in response.json()["error"]["details"]}
    assert fields["detail"] == "必須項目です。"
    assert fields["(unknown)"] == "想定外の項目です。"
    # 想定外の項目のキー名は返さない
    assert "unexpected" not in response.text


async def test_unknown_key_name_is_not_returned(caplog):
    # キー名そのものに目印を入れても、レスポンス・ログに含まれないこと
    response = await _post(json={"theme": "other", "detail": "ok", MARKER: "x"})

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"field": "(unknown)", "reason": "想定外の項目です。"}
    ]
    assert MARKER not in response.text
    assert MARKER not in caplog.text


async def test_invalid_json_returns_400_without_input(caplog):
    response = await _post(content='{"detail": "' + MARKER)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert MARKER not in response.text
    assert MARKER not in caplog.text


@pytest.mark.parametrize(
    "error_type, status, code",
    [
        (AuthenticationRequiredError, 401, "UNAUTHORIZED"),
        (AccountDeletingError, 403, "ACCOUNT_DELETING"),
        (AuthServiceUnavailableError, 503, "AUTH_UNAVAILABLE"),
        (DatabaseUnavailableError, 503, "DB_UNAVAILABLE"),
    ],
)
async def test_service_errors_log_only_safe_503_metadata(
    caplog, error_type, status, code
):
    caplog.set_level(logging.INFO)
    token = "DUMMY_TEST_TOKEN"
    connection_url = "postgresql://dummy:dummy@invalid.test/dummy"
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/dummy")
    async def dummy():
        try:
            raise RuntimeError(f"{MARKER} {token} {connection_url}")
        except RuntimeError as cause:
            raise error_type(f"{MARKER} {token} {connection_url}") from cause

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/dummy",
            headers={"Authorization": f"Bearer {token}"},
            json={"detail": MARKER},
        )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
    else:
        assert "www-authenticate" not in response.headers

    records = [r for r in caplog.records if r.name == "app.core.errors"]
    if status == 503:
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert records[0].getMessage() == f"{code} {error_type.__name__}"
    else:
        assert records == []

    for record in caplog.records:
        assert record.exc_info is None
        assert record.exc_text is None
        assert record.stack_info is None
    for secret in (MARKER, token, connection_url):
        assert secret not in response.text
        assert secret not in caplog.text
