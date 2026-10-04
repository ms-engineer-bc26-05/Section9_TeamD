"""OpenRouter（OpenAI互換API）の非同期クライアント。

- httpx.AsyncClient を使い、AIの応答待ちでワーカー全体を止めない（requests等の同期I/Oは使わない）
- 構造化出力（response_format: json_schema, strict）を指定し、JSON以外の応答は失敗として扱う
- require_parameters は provider の中に指定する（Issue #4では最上位に置いており、効いていなかった可能性がある）
- 送信内容・AIの出力・APIキーは、例外メッセージやログに含めない
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# 設定値は共通の config.py ではなく、この連携の中で読み込む（他Issueとの競合を避けるため）
DEFAULT_MODEL = "openai/gpt-oss-120b"  # Issue #4の暫定候補
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_TEMPERATURE = 0.7


class AIClientError(Exception):
    """AIの呼び出しに失敗した（APIでは502）。メッセージに送信内容・出力を含めない"""


@dataclass(frozen=True)
class AICallResult:
    """AIの応答。content はJSONとして解析済みの値（Schemaの検証は呼び出し側で行う）"""

    content: dict[str, Any] = field(repr=False)
    # 実API確認の記録用（本文は含まない）
    model: str | None = None
    provider: str | None = None
    usage: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,  # テストで差し替える
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._transport = transport

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        schema_name: str,
    ) -> AICallResult:
        """構造化出力を指定してAIを呼び出し、JSONとして解析した結果を返す"""
        if not self._api_key:
            raise AIClientError("OpenRouterのAPIキーが設定されていません")

        payload = {
            "model": self._model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            # 指定したパラメータ（構造化出力）に対応するプロバイダだけに振り分ける
            "provider": {"require_parameters": True},
            "temperature": DEFAULT_TEMPERATURE,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(OPENROUTER_API_URL, headers=headers, json=payload)
        except httpx.TimeoutException:
            logger.warning("OpenRouter呼び出しがタイムアウトしました schema=%s", schema_name)
            raise AIClientError("AIの呼び出しがタイムアウトしました") from None
        except httpx.HTTPError as exc:
            logger.warning(
                "OpenRouter呼び出しに失敗しました schema=%s error=%s",
                schema_name,
                type(exc).__name__,
            )
            raise AIClientError("AIの呼び出しに失敗しました") from None
        elapsed = round(time.monotonic() - start, 2)

        if response.status_code != 200:
            # エラー本文には送信内容が含まれる可能性があるため、ステータスコードだけを記録する
            logger.warning(
                "OpenRouterがエラーを返しました schema=%s status=%s elapsed=%s",
                schema_name,
                response.status_code,
                elapsed,
            )
            raise AIClientError("AIの呼び出しに失敗しました")

        try:
            body = response.json()
            raw_content = body["choices"][0]["message"]["content"]
            content = json.loads(raw_content)
        except (ValueError, KeyError, IndexError, TypeError):
            logger.warning("OpenRouterの応答をJSONとして解析できませんでした schema=%s", schema_name)
            raise AIClientError("AIの応答を解析できませんでした") from None

        if not isinstance(content, dict):
            logger.warning("OpenRouterの応答がJSONオブジェクトではありません schema=%s", schema_name)
            raise AIClientError("AIの応答を解析できませんでした")

        logger.info(
            "OpenRouter呼び出しに成功しました schema=%s model=%s provider=%s elapsed=%s",
            schema_name,
            body.get("model"),
            body.get("provider"),
            elapsed,
        )
        return AICallResult(
            content=content,
            model=body.get("model"),
            provider=body.get("provider"),
            usage=body.get("usage"),
            elapsed_seconds=elapsed,
        )


def get_ai_client() -> OpenRouterClient:
    """APIで使うクライアント。テストでは dependency_overrides 等で差し替える"""
    return OpenRouterClient(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
        timeout_seconds=float(
            os.environ.get("OPENROUTER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        ),
    )
