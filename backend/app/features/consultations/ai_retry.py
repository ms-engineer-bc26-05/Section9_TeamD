"""AI呼び出しの再試行（I-07 #54で決定）。

- 1回の呼び出しにつき、再試行は1回まで（合計2回）
- 再試行する：接続エラー、429、5xx、JSONとして解析できない応答（AIClientError.retryable）、
  AIの出力の不正（AIOutputInvalid。Schema不正・サーバーが指定した進め方と違う）
- 再試行しない：タイムアウト、400・401・402・403・404など（AIClientError.retryable が False）
- 429で Retry-After が1秒を超える場合は再試行しない。1秒以下ならその秒数、ヘッダーがなければ1秒待つ
- 1回目の失敗までにかかった時間が max_first_attempt_seconds を超えた場合は再試行しない
  （利用者の待ち時間が長くなりすぎないため。暫定25秒、実測後に確定。
   最長の待ち時間は 25秒＋1秒＋タイムアウト30秒 ＝ 約56秒）
- 安全案内の印を読み取れる出力（Q-28）は不正ではないため、再試行の対象にならない
- 再試行の前に相談（または開始の予約）がまだ有効かを確認する（呼び出し側の相談Serviceで行う）
- ログには失敗の種類と試行回数だけを残す（入力・AIの出力・エラー本文は残さない）

待ち時間の線は環境変数 AI_RETRY_MAX_FIRST_ATTEMPT_SECONDS で変えられる。
テストでは _policy_provider を差し替える（tests/features/conftest.py で、既定では再試行しない）。
"""

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.features.consultations.ai_schemas import AIOutputInvalid
from app.integrations.openrouter.client import AIClientError

logger = logging.getLogger(__name__)

# 暫定値（I-07の実測後に確定する）
DEFAULT_MAX_FIRST_ATTEMPT_SECONDS = 25.0
DEFAULT_WAIT_SECONDS = 1.0
MAX_RETRY_AFTER_SECONDS = 1.0


@dataclass(frozen=True)
class AIRetryPolicy:
    max_attempts: int = 2
    max_first_attempt_seconds: float = DEFAULT_MAX_FIRST_ATTEMPT_SECONDS
    default_wait_seconds: float = DEFAULT_WAIT_SECONDS
    max_retry_after_seconds: float = MAX_RETRY_AFTER_SECONDS
    # テストで差し替える
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clock: Callable[[], float] = time.monotonic

    def wait_before_retry(
        self, exc: Exception, attempt: int, elapsed_seconds: float
    ) -> float | None:
        """再試行する場合は待つ秒数を、しない場合は None を返す"""
        if attempt >= self.max_attempts:
            return None
        if elapsed_seconds > self.max_first_attempt_seconds:
            return None
        if isinstance(exc, AIOutputInvalid):
            return self.default_wait_seconds
        if isinstance(exc, AIClientError) and exc.retryable:
            if exc.retry_after is None:
                return self.default_wait_seconds
            if exc.retry_after > self.max_retry_after_seconds:
                return None
            return exc.retry_after
        return None


# 再試行しない（テストの既定）
NO_RETRY = AIRetryPolicy(max_attempts=1)


def failure_kind(exc: Exception) -> str:
    """ログに残す失敗の種類。例外のメッセージ（内容）は使わない"""
    if isinstance(exc, AIOutputInvalid):
        return "output_invalid"
    if isinstance(exc, AIClientError):
        return exc.kind
    return type(exc).__name__


def _read_seconds(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        seconds = float(value)
    except ValueError:
        logger.warning("%s の値が不正なため既定値を使います", name)
        return default
    if not seconds >= 0:  # 負の値・NaN
        logger.warning("%s の値が不正なため既定値を使います", name)
        return default
    return seconds


def _default_policy() -> AIRetryPolicy:
    return AIRetryPolicy(
        max_first_attempt_seconds=_read_seconds(
            "AI_RETRY_MAX_FIRST_ATTEMPT_SECONDS", DEFAULT_MAX_FIRST_ATTEMPT_SECONDS
        )
    )


# テストで差し替えられるよう、作り方を変数に持つ
_policy_provider: Callable[[], AIRetryPolicy] = _default_policy


def get_ai_retry_policy() -> AIRetryPolicy:
    """相談Serviceが使う再試行の方針"""
    return _policy_provider()
