"""Redisによる相談回数のカウント（Issue #57）。

Redisのキー：usage_limit:{内部ユーザーID}（ハッシュ）
  - count  ：期間内に開始した相談の回数
  - period ：期間ID。期間が始まる（キーを作る）たびに新しく振る
  会話内容・入力原文・個人情報は保存しない。

- 「上限未満なら加算」「初回だけTTLを設定」「戻すときの期間IDの確認と減算」は、
  それぞれ1つのLuaスクリプトで原子的に行う（判定と加算の間に別の処理が割り込まない）
- 上限超過で拒否したリクエストは加算しない
- 戻すのは、そのリクエストが実際に加算した1回分だけ。同じ予約で2回戻さない。
  加算したときと期間IDが違えば（期間が切り替わっていれば）何もしない。
  戻して回数が0になったらキーごと削除する
- Redis障害時：相談開始の判定はフェイルオープン（許可し、加算しない）。
  ログには例外の種類だけを出し、ユーザーID・接続先は出さない
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

from app.features.usage.exceptions import UsageStoreUnavailable
from app.features.usage.settings import UsageSettings, get_usage_settings

logger = logging.getLogger(__name__)

KEY_PREFIX = "usage_limit:"

# 上限なし（無制限）をLuaへ渡すときの値
_NO_LIMIT = -1

# KEYS[1]=キー ARGV[1]=上限（-1は無制限） ARGV[2]=TTL秒 ARGV[3]=新しい期間ID
# 戻り値：{加算したか(1/0), 判定後の回数, 期間ID, 残りミリ秒}
_RESERVE_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local key_type = redis.call("TYPE", key)["ok"]
if key_type ~= "none" and key_type ~= "hash" then
    redis.call("DEL", key)
end
local count = tonumber(redis.call("HGET", key, "count") or "0")
local period = redis.call("HGET", key, "period")
if (not period) or count < 0 then
    redis.call("DEL", key)
    count = 0
    period = false
end
if limit >= 0 and count >= limit then
    return {0, count, period or "", redis.call("PTTL", key)}
end
if not period then
    redis.call("HSET", key, "count", 1, "period", ARGV[3])
    redis.call("EXPIRE", key, tonumber(ARGV[2]))
    return {1, 1, ARGV[3], redis.call("PTTL", key)}
end
local new_count = redis.call("HINCRBY", key, "count", 1)
if redis.call("PTTL", key) < 0 then
    redis.call("EXPIRE", key, tonumber(ARGV[2]))
end
return {1, new_count, period, redis.call("PTTL", key)}
"""

# KEYS[1]=キー ARGV[1]=加算したときの期間ID
# 戻り値：戻した場合1、期間が違う・キーがない場合0
_REFUND_SCRIPT = """
local key = KEYS[1]
if redis.call("TYPE", key)["ok"] ~= "hash" then
    return 0
end
if redis.call("HGET", key, "period") ~= ARGV[1] then
    return 0
end
local count = redis.call("HINCRBY", key, "count", -1)
if count <= 0 then
    redis.call("DEL", key)
end
return 1
"""

# KEYS[1]=キー 戻り値：{回数, 残りミリ秒}
_READ_SCRIPT = """
local key = KEYS[1]
if redis.call("TYPE", key)["ok"] ~= "hash" then
    return {0, -2}
end
return {tonumber(redis.call("HGET", key, "count") or "0"), redis.call("PTTL", key)}
"""

_REDIS_ERRORS = (RedisError, OSError, TimeoutError)


def usage_key(user_id: UUID) -> str:
    return f"{KEY_PREFIX}{user_id}"


@dataclass
class Reservation:
    """相談開始時の判定結果。戻す処理（refund）に使う"""

    user_id: UUID
    allowed: bool
    counted: bool  # このリクエストで実際に加算したか
    count: int | None  # 判定後の回数。Redis障害で判定できなかった場合は None
    period_id: str | None = field(default=None, repr=False)
    refunded: bool = False


@dataclass(frozen=True)
class UsageCounter:
    """GET /usage 用の現在の回数"""

    count: int
    resets_at: datetime | None  # キーがない（まだ使っていない）場合は None


def _now() -> datetime:
    return datetime.now(UTC)


class UsageLimiter:
    def __init__(
        self,
        redis: Redis | None,
        period_seconds: int,
        now: Callable[[], datetime] = _now,
    ) -> None:
        # redis が None の場合（REDIS_URL 未設定）は、常にRedis障害として扱う
        self._redis = redis
        self._period_seconds = period_seconds
        self._now = now
        if redis is not None:
            self._reserve = redis.register_script(_RESERVE_SCRIPT)
            self._refund = redis.register_script(_REFUND_SCRIPT)
            self._read = redis.register_script(_READ_SCRIPT)

    async def _run(self, script_name: str, keys: list[str], args: list[Any]) -> Any:
        if self._redis is None:
            raise UsageStoreUnavailable
        script = getattr(self, script_name)
        try:
            return await script(keys=keys, args=args)
        except _REDIS_ERRORS as exc:
            # 接続先・キー（ユーザーID）を含めないため、例外の種類だけを記録する
            logger.warning("usage redis error: %s", type(exc).__name__)
            raise UsageStoreUnavailable from None

    async def reserve(self, user_id: UUID, limit: int | None) -> Reservation:
        """上限未満なら1回加算する。Redis障害時は許可し、加算しない（フェイルオープン）"""
        try:
            allowed, count, period_id, _ = await self._run(
                "_reserve",
                [usage_key(user_id)],
                [_NO_LIMIT if limit is None else limit, self._period_seconds, uuid.uuid4().hex],
            )
        except UsageStoreUnavailable:
            logger.warning("usage limit check skipped (fail-open)")
            return Reservation(user_id=user_id, allowed=True, counted=False, count=None)
        allowed = bool(int(allowed))
        return Reservation(
            user_id=user_id,
            allowed=allowed,
            counted=allowed,
            count=int(count),
            period_id=period_id if allowed else None,
        )

    async def refund(self, reservation: Reservation) -> bool:
        """そのリクエストが加算した1回分を戻す。戻した場合 True。

        - 加算していない・すでに戻した予約では何もしない
        - 加算したときと期間が違えば何もしない
        - Redis障害で戻せなかった場合は記録だけ残し、例外は出さない
        """
        if not reservation.counted or reservation.refunded:
            return False
        # await より前に印を付け、同じ予約で2回戻さない
        reservation.refunded = True
        try:
            refunded = await self._run(
                "_refund", [usage_key(reservation.user_id)], [reservation.period_id]
            )
        except UsageStoreUnavailable:
            logger.warning("usage refund skipped")
            return False
        return bool(int(refunded))

    async def get_counter(self, user_id: UUID) -> UsageCounter | None:
        """現在の回数とリセット日時。Redis障害時は None"""
        try:
            count, pttl = await self._run("_read", [usage_key(user_id)], [])
        except UsageStoreUnavailable:
            return None
        count, pttl = int(count), int(pttl)
        resets_at = self._now() + timedelta(milliseconds=pttl) if pttl > 0 else None
        return UsageCounter(count=count, resets_at=resets_at)

    async def delete_user_usage(self, user_id: UUID) -> None:
        """退会処理（F-06）から呼ぶ。本人のキーだけを削除し、キーがなくても正常終了する。

        Redis障害時は UsageStoreUnavailable を送出する（退会処理を再実行できるように）。
        """
        if self._redis is None:
            raise UsageStoreUnavailable
        try:
            await self._redis.delete(usage_key(user_id))
        except _REDIS_ERRORS as exc:
            logger.warning("usage redis error: %s", type(exc).__name__)
            raise UsageStoreUnavailable from None


def create_redis(settings: UsageSettings) -> Redis | None:
    if not settings.redis_url:
        return None
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_command_timeout_seconds,
        # 再試行しない（質問⑧）。待ち時間がタイムアウトの合計を超えないようにする
        retry_on_timeout=False,
        retry=Retry(NoBackoff(), 0),
    )


_limiter: UsageLimiter | None = None


def get_usage_limiter() -> UsageLimiter:
    """APIプロセスで共有するカウンタ。テストでは dependency_overrides 等で差し替える"""
    global _limiter
    if _limiter is None:
        settings = get_usage_settings()
        _limiter = UsageLimiter(create_redis(settings), settings.period_seconds)
    return _limiter


async def close_usage_limiter() -> None:
    """アプリ終了時にRedisの接続を閉じる。

    main.py の lifespan からの呼び出しは、結合Issue（I-06）で行う。
    """
    global _limiter
    if _limiter is not None and _limiter._redis is not None:
        await _limiter._redis.aclose()
    _limiter = None
