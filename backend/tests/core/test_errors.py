"""共通エラーハンドラ（422・400）のテスト。

入力を受け取るAPIはまだないため、テスト用の仮APIで確認する。
送信した値がレスポンス・ログに含まれないことを、目印の文字列で確認する。
"""

from typing import Optional

import pytest

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import register_exception_handlers
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


# ---------------------------------------------------------------------------
# 想定外の例外（500）：#86
# ---------------------------------------------------------------------------

import logging  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.errors import (  # noqa: E402
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    InternalErrorMiddleware,
)

INTERNAL_ERROR_BODY = {"error": {"code": INTERNAL_ERROR_CODE, "message": INTERNAL_ERROR_MESSAGE}}
ORIGIN = "http://localhost:3000"


def _make_failing_app(*, with_cors: bool = False) -> FastAPI:
    """想定外の例外を起こす仮APIを持つアプリ（main.py と同じ順番で登録する）"""
    app = FastAPI()
    register_exception_handlers(app)
    if with_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[ORIGIN],
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.post("/runtime-error")
    async def runtime_error(body: dict) -> dict:
        # 例外のメッセージに入力値が入る場合を模す
        raise RuntimeError(f"入力値を含むメッセージ {body}")

    @app.post("/validation-error")
    async def validation_error(body: dict) -> dict:
        # 処理の途中で Pydantic の検証に失敗する場合（ValidationError は入力値をメッセージに含む）
        DummyInput.model_validate({"theme": "other", "detail": body["detail"]})
        return {"ok": True}

    @app.get("/not-found")
    async def not_found() -> dict:
        raise HTTPException(status_code=404)

    @app.get("/stream-error")
    async def stream_error():
        async def body():
            yield b"partial"
            raise RuntimeError(f"送信中のエラー {MARKER}")

        return StreamingResponse(body())

    return app


def test_main_app_registers_internal_error_middleware():
    classes = [m.cls for m in main_app.user_middleware]
    assert InternalErrorMiddleware in classes
    # CORSMiddleware が外側（リストの前）にあるため、500の応答にもCORSのヘッダーが付く
    assert classes.index(CORSMiddleware) < classes.index(InternalErrorMiddleware)


@pytest.mark.parametrize("path", ["/runtime-error", "/validation-error"])
def test_unexpected_error_returns_500_in_common_format(caplog, path):
    caplog.set_level(logging.DEBUG)
    # raise_server_exceptions=True（既定）でも例外が出ない＝例外を投げ直していない
    client = TestClient(_make_failing_app())

    response = client.post(path, json={"detail": f"架空の相談本文 {MARKER}"})

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == INTERNAL_ERROR_BODY
    assert MARKER not in response.text
    # ログには例外の種類と場所だけを出し、メッセージ（入力値）は出さない
    assert MARKER not in caplog.text
    assert "unhandled error" in caplog.text


def test_log_contains_error_type_and_location(caplog):
    caplog.set_level(logging.DEBUG)
    TestClient(_make_failing_app()).post("/runtime-error", json={"detail": "架空"})

    records = [r for r in caplog.records if r.name == "app.core.errors"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "RuntimeError" in message
    assert "in runtime_error" in message  # 起きた関数の名前
    assert "POST /runtime-error" in message
    assert "架空" not in message


def test_internal_error_response_has_cors_headers():
    # 画面（ブラウザ）が500の本文を読めるよう、CORSのヘッダーが付く
    client = TestClient(_make_failing_app(with_cors=True))

    response = client.post("/runtime-error", json={"detail": "架空"}, headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.json() == INTERNAL_ERROR_BODY


def test_other_errors_keep_their_own_handling():
    client = TestClient(_make_failing_app())

    # HTTPException は、これまでどおり FastAPI の処理で返す（500にしない）
    assert client.get("/not-found").status_code == 404
    # リクエストの検証エラーは、これまでどおり422
    response = client.post("/validation-error", json=[1])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_error_after_response_started_is_not_raised(caplog):
    # 応答を送り始めた後のエラーは、別の応答を送れないため打ち切る（例外は投げ直さない）
    caplog.set_level(logging.DEBUG)
    client = TestClient(_make_failing_app())

    response = client.get("/stream-error")

    assert response.status_code == 200
    assert MARKER not in caplog.text
    # 非同期処理でまとめられた例外からも、元の例外の種類と場所を取り出してログに出す
    assert "RuntimeError" in caplog.text
    assert "in body" in caplog.text
