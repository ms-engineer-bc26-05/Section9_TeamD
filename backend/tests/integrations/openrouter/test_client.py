"""OpenRouterクライアントのテスト。外部APIへは接続せず、httpx.MockTransportで応答を模す。"""

import json
import logging

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
    # require_parameters は provider の中に指定する
    assert body["provider"] == {"require_parameters": True}
    assert "require_parameters" not in body


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

    with pytest.raises(AIClientError):
        await client.complete_json(MESSAGES, SCHEMA, "first_question")
