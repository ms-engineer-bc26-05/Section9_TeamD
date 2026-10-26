"""OpenRouterクライアントのテスト。外部APIへは接続せず、httpx.MockTransportで応答を模す。"""

import asyncio
import json
import logging
import time

import httpx
import pytest

from app.integrations.openrouter.client import AIClientError, OpenRouterClient

SCHEMA = {
    "type": "object",
    "properties": {"ai_question": {"type": "string"}},
    "required": ["ai_question"],
    "additionalProperties": False,
}
MESSAGES = [
    {"role": "system", "content": "架空のシステム指示"},
    {"role": "user", "content": "架空の相談本文"},
]


def make_client(handler):
    return OpenRouterClient(
        api_key="test-key",
        model="test/model",
        transport=httpx.MockTransport(handler),
    )


def ok_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "test/model",
            "provider": "TestProvider",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [{"message": {"role": "assistant", "content": content}}],
        },
    )


@pytest.mark.asyncio
async def test_sends_structured_output_request():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["auth"] = request.headers["Authorization"]
        sent["body"] = json.loads(request.content)
        return ok_response('{"ai_question": "架空の質問"}')

    result = await make_client(handler).complete_json(MESSAGES, SCHEMA, "first_question")

    assert result.content == {"ai_question": "架空の質問"}
    assert result.provider == "TestProvider"
    assert sent["auth"] == "Bearer test-key"
    body = sent["body"]
    assert body["model"] == "test/model"
    assert body["messages"] == MESSAGES
    assert body["response_format"]["json_schema"]["strict"] is True
    # require_parameters は provider の中に指定する。ZDR・学習に使わない提供元だけを使う（I-07）
    assert body["provider"] == {
        "require_parameters": True,
        "zdr": True,
        "data_collection": "deny",
        # 実API確認で出力の崩れが集中した提供元を除外する（I-07）
        "ignore": ["coreweave"],
    }
    assert "require_parameters" not in body
    # 実測した料金の記録用に、usage へ料金を含める
    assert body["usage"] == {"include": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="架空の相談本文を含むエラー"),
        httpx.Response(400, text="架空の相談本文を含むエラー"),
        httpx.Response(200, text="JSONではない"),
        httpx.Response(200, json={"choices": []}),
    ],
)
async def test_raises_error_without_content(response, caplog):
    caplog.set_level(logging.INFO)
    client = make_client(lambda request: response)

    with pytest.raises(AIClientError) as exc_info:
        await client.complete_json(MESSAGES, SCHEMA, "first_question")

    assert "架空" not in str(exc_info.value)
    assert "架空" not in caplog.text


@pytest.mark.asyncio
async def test_raises_error_when_content_is_not_json():
    client = make_client(lambda request: ok_response("架空の自由文章"))

    with pytest.raises(AIClientError) as exc_info:
        await client.complete_json(MESSAGES, SCHEMA, "first_question")
    assert "架空" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_raises_error_on_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(AIClientError):
        await make_client(handler).complete_json(MESSAGES, SCHEMA, "first_question")


@pytest.mark.asyncio
async def test_raises_error_without_api_key():
    client = OpenRouterClient(api_key="", transport=httpx.MockTransport(lambda r: ok_response("{}")))

    with pytest.raises(AIClientError) as exc_info:
        await client.complete_json(MESSAGES, SCHEMA, "first_question")
    assert exc_info.value.retryable is False


# --- 失敗の種類と、再試行してよいか（I-07 #54） -------------------------------------


async def _error_of(handler) -> AIClientError:
    with pytest.raises(AIClientError) as exc_info:
        await make_client(handler).complete_json(MESSAGES, SCHEMA, "first_question")
    return exc_info.value


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_5xx_is_retryable(status):
    error = await _error_of(lambda request: httpx.Response(status))
    assert (error.kind, error.retryable) == ("http_5xx", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 408])
async def test_other_error_status_is_not_retryable(status):
    error = await _error_of(lambda request: httpx.Response(status))
    assert (error.kind, error.retryable) == (f"http_{status}", False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "retry_after"),
    [
        ({}, None),  # ヘッダーなし
        ({"Retry-After": "1"}, 1.0),
        ({"Retry-After": "0.5"}, 0.5),
        ({"Retry-After": "5"}, 5.0),
        ({"Retry-After": "-1"}, 0.0),
        # 日付形式など、秒として読めない場合は「長い」とみなす（再試行しない）
        ({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, float("inf")),
    ],
)
async def test_429_is_retryable_with_retry_after(headers, retry_after):
    error = await _error_of(lambda request: httpx.Response(429, headers=headers))
    assert (error.kind, error.retryable) == ("http_429", True)
    assert error.retry_after == retry_after


@pytest.mark.asyncio
async def test_timeout_is_not_retryable():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    error = await _error_of(handler)
    assert (error.kind, error.retryable) == ("timeout", False)


@pytest.mark.asyncio
async def test_total_time_is_limited_even_if_data_keeps_arriving():
    # 接続維持のデータが届き続け、httpxの timeout（データが届かない時間）では止まらない場合も、
    # 応答全体の上限（timeout_seconds）で打ち切る（I-07の実API確認で157秒待ったことへの対策）
    class Trickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.01)
                yield b" "

    def handler(request):
        return httpx.Response(200, stream=Trickle())

    client = OpenRouterClient(
        api_key="test-key",
        model="test/model",
        timeout_seconds=0.1,
        transport=httpx.MockTransport(handler),
    )
    started = time.monotonic()
    with pytest.raises(AIClientError) as exc_info:
        await client.complete_json(MESSAGES, SCHEMA, "first_question")

    assert (exc_info.value.kind, exc_info.value.retryable) == ("timeout", False)
    assert time.monotonic() - started < 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_type", [httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError]
)
async def test_network_error_is_retryable(exc_type):
    def handler(request):
        raise exc_type("架空の接続エラー", request=request)

    error = await _error_of(handler)
    assert (error.kind, error.retryable) == ("network", True)
    assert "架空" not in str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        ok_response("架空の自由文章"),  # contentがJSONではない
        ok_response('["架空"]'),  # JSONだがオブジェクトではない
        httpx.Response(200, json={"choices": []}),
    ],
)
async def test_unparsable_response_is_retryable(response):
    error = await _error_of(lambda request: response)
    assert (error.kind, error.retryable) == ("invalid_response", True)
    assert "架空" not in str(error)
