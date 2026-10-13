"""Redis障害時のテスト（テスト設計 RL-10・RL-11）。

接続できない接続先を指定して障害を模す（実物のRedisは不要）。
"""

import logging
from uuid import uuid4

import pytest

from app.features.usage.exceptions import UsageStoreUnavailable
from app.features.usage.limiter import Reservation, UsageLimiter, create_redis
from tests.features.usage.conftest import UNREACHABLE_REDIS_URL
from tests.features.usage.fakes import make_settings


@pytest.fixture
async def broken_limiter():
    settings = make_settings(
        REDIS_URL=UNREACHABLE_REDIS_URL,
        REDIS_CONNECT_TIMEOUT_SECONDS="0.5",
        REDIS_COMMAND_TIMEOUT_SECONDS="0.5",
    )
    redis = create_redis(settings)
    yield UsageLimiter(redis, settings.period_seconds)
    await redis.aclose()


@pytest.fixture
def no_url_limiter():
    # REDIS_URL が未設定の場合
    return UsageLimiter(None, 60)


@pytest.fixture(params=["broken_limiter", "no_url_limiter"])
def unavailable_limiter(request):
    return request.getfixturevalue(request.param)


async def test_reserve_fails_open_without_counting(unavailable_limiter, caplog):
    # RL-10：Redis障害時も相談を開始できる。加算はしない
    caplog.set_level(logging.INFO)
    user = uuid4()

    reservation = await unavailable_limiter.reserve(user, 3)

    assert (reservation.allowed, reservation.counted, reservation.count) == (True, False, None)
    assert "fail-open" in caplog.text
    # ログにユーザーID・接続先を含めない
    assert str(user) not in caplog.text
    assert "127.0.0.1" not in caplog.text


async def test_refund_after_fail_open_does_nothing(unavailable_limiter):
    # 加算できたか分からない（加算していない）リクエストは戻さない
    reservation = await unavailable_limiter.reserve(uuid4(), 3)

    assert await unavailable_limiter.refund(reservation) is False


async def test_refund_error_is_not_raised(unavailable_limiter, caplog):
    # 加算後にRedisが止まった場合、戻せなくても例外にしない（記録だけ残す）
    caplog.set_level(logging.INFO)
    user = uuid4()
    reservation = Reservation(user_id=user, allowed=True, counted=True, count=1, period_id="p1")

    assert await unavailable_limiter.refund(reservation) is False
    assert str(user) not in caplog.text


async def test_get_counter_returns_none(unavailable_limiter):
    # RL-11：利用状況の回数は「不明」（None）として返す
    assert await unavailable_limiter.get_counter(uuid4()) is None


async def test_delete_user_usage_raises(unavailable_limiter):
    # 退会処理（F-06）は失敗を知る必要があるため、フェイルオープンにしない
    with pytest.raises(UsageStoreUnavailable):
        await unavailable_limiter.delete_user_usage(uuid4())
