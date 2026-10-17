"""OpenRouter（OpenAI互換API）の非同期クライアント。

- httpx.AsyncClient を使い、AIの応答待ちでワーカー全体を止めない（requests等の同期I/Oは使わない）
- 構造化出力（response_format: json_schema, strict）を指定し、JSON以外の応答は失敗として扱う
- require_parameters は provider の中に指定する（Issue #4では最上位に置いており、効いていなかった可能性がある）
- 送信内容・AIの出力・APIキーは、例外メッセージやログに含めない

提供元の条件（I-07 #54。講師への確認結果）：
- zdr=True：データを保持しない（ZDR）提供元だけを使う
- data_collection="deny"：送信内容を学習・データ収集に使う提供元を除外する
- スクールのキーにも同じ条件が設定済みだが、別のキーを使う場合もアプリ側で同じ条件をかけるため指定する
- 提供元は固定しない（講師の推奨）。条件を満たす提供元がない場合はエラー（再試行しない）
- ignore=["coreweave"]：実API確認で出力の崩れが集中したため除外する（Issue #54に記録）

再試行（I-07 #54で決定）：
- このクライアントは再試行しない。失敗の種類（kind）と再試行してよいか（retryable）を
  AIClientError に持たせ、再試行は相談Service（ai_retry.py）で1回だけ行う
- 再試行してよい失敗：接続エラー、429、5xx、200だがJSONとして解析できない応答
- 再試行しない失敗：タイムアウト、それ以外のエラー応答（400・401・402・403・404など）、APIキー未設定
"""

import asyncio
import json
import logging
import math
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

# 提供元の条件（I-07 #54）
PROVIDER_PREFERENCES = {
    # 指定したパラメータ（構造化出力）に対応する提供元だけに振り分ける
    "require_parameters": True,
    # データを保持しない（ZDR）提供元だけを使う
    "zdr": True,
    # 送信内容を学習・データ収集に使う提供元を除外する
    "data_collection": "deny",
    # 実API確認（I-07、10/16）で、CoreWeaveに振り分けられた6回のうち4回で出力が崩れた
    # （質問文の途切れ2回・7,792トークンの出力で157秒・危機の見逃し1回）。ほかの8社では0回
    "ignore": ["coreweave"],
}


class AIClientError(Exception):
    """AIの呼び出しに失敗した（APIでは502）。メッセージに送信内容・出力を含めない。

    kind：失敗の種類（ログ用。本文は含まない）
    retryable：再試行してよい失敗か
    retry_after：429の Retry-After（秒）。ヘッダーがなければ None、解析できなければ無限大
    """

    def __init__(
        self,
        message: str = "AIの呼び出しに失敗しました",
        *,
        kind: str = "unknown",
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class AICallResult:
    """AIの応答。content はJSONとして解析済みの値（Schemaの検証は呼び出し側で行う）"""

    content: dict[str, Any] = field(repr=False)
    # 実API確認の記録用（本文は含まない）
    model: str | None = None
    provider: str | None = None
    usage: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0


def _parse_retry_after(value: str | None) -> float | None:
    """Retry-After（秒）を読む。ヘッダーがなければ None、日付形式などで読めなければ無限大"""
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return math.inf
    if math.isnan(seconds):
        return math.inf
    return max(seconds, 0.0)


def _error_for_status(response: httpx.Response) -> AIClientError:
    status = response.status_code
    if status == 429:
        return AIClientError(
            kind="http_429",
            retryable=True,
            retry_after=_parse_retry_after(response.headers.get("Retry-After")),
        )
    if 500 <= status <= 599:
        return AIClientError(kind="http_5xx", retryable=True)
    # 400・401・402・403・404など：設定・残高・条件を満たす提供元がない等。何度呼んでも失敗する
    return AIClientError(kind=f"http_{status}", retryable=False)


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,  # テスト・実API確認で差し替える
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
        """構造化出力を指定してAIを呼び出し、JSONとして解析した結果を返す（再試行はしない）"""
        if not self._api_key:
            raise AIClientError("OpenRouterのAPIキーが設定されていません", kind="no_api_key")

        payload = {
            "model": self._model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            "provider": dict(PROVIDER_PREFERENCES),
            # 応答の usage に料金（cost）を含める（実測した料金の記録用）
            "usage": {"include": True},
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
                # httpx の timeout は「データが届かない時間」の上限で、応答全体の上限ではない。
                # OpenRouterは応答を作る間も接続維持のためにデータを送ることがあり、
                # 実API確認（I-07）では30秒の設定で157秒待った。応答全体にも上限をかける
                response = await asyncio.wait_for(
                    client.post(OPENROUTER_API_URL, headers=headers, json=payload),
                    timeout=self._timeout,
                )
        except (TimeoutError, httpx.TimeoutException):
            logger.warning("OpenRouter呼び出しがタイムアウトしました schema=%s", schema_name)
            raise AIClientError("AIの呼び出しがタイムアウトしました", kind="timeout") from None
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            logger.warning(
                "OpenRouterへの接続に失敗しました schema=%s error=%s",
                schema_name,
                type(exc).__name__,
            )
            raise AIClientError(kind="network", retryable=True) from None
        except httpx.HTTPError as exc:
            logger.warning(
                "OpenRouter呼び出しに失敗しました schema=%s error=%s",
                schema_name,
                type(exc).__name__,
            )
            raise AIClientError(kind="http_error") from None
        elapsed = round(time.monotonic() - start, 2)

        if response.status_code != 200:
            # エラー本文には送信内容が含まれる可能性があるため、ステータスコードだけを記録する
            logger.warning(
                "OpenRouterがエラーを返しました schema=%s status=%s elapsed=%s",
                schema_name,
                response.status_code,
                elapsed,
            )
            raise _error_for_status(response)

        try:
            body = response.json()
            raw_content = body["choices"][0]["message"]["content"]
            content = json.loads(raw_content)
        except (ValueError, KeyError, IndexError, TypeError):
            logger.warning("OpenRouterの応答をJSONとして解析できませんでした schema=%s", schema_name)
            raise AIClientError(
                "AIの応答を解析できませんでした", kind="invalid_response", retryable=True
            ) from None

        if not isinstance(content, dict):
            logger.warning("OpenRouterの応答がJSONオブジェクトではありません schema=%s", schema_name)
            raise AIClientError(
                "AIの応答を解析できませんでした", kind="invalid_response", retryable=True
            )

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
