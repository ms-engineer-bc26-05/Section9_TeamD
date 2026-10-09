"""相談開始時の判定（UsageService.reserve_consultation）のテスト。Redis・DBは偽物。"""

from uuid import uuid4

import pytest

from app.features.usage.exceptions import PlanUnavailable, UsageLimitExceeded
from app.features.usage.service import UsageService
from app.features.usage.settings import PlanCode
from tests.features.usage.fakes import (
    FakeLimiter,
    FakeMemoCounter,
    FakePlanResolver,
    make_settings,
    plan_unavailable,
)


def make_service(limiter, plans=None, **env):
    return UsageService(
        limiter, plans or FakePlanResolver(), FakeMemoCounter(), make_settings(**env)
    )


async def test_reserve_uses_free_plan_limit():
    limiter = FakeLimiter(count=0)
    reservation = await make_service(limiter).reserve_consultation(uuid4())

    assert reservation.counted is True
    assert limiter.reserve_calls == [3]


async def test_reserve_raises_when_limit_exceeded():
    # RL-04：上限超過は UsageLimitExceeded（403）
    limiter = FakeLimiter(count=3)

    with pytest.raises(UsageLimitExceeded):
        await make_service(limiter).reserve_consultation(uuid4())
    assert limiter.count == 3


async def test_premium_plan_uses_premium_limit():
    # RL-14：有料プランでは有料の上限値で判定する
    limiter = FakeLimiter(count=3)
    service = make_service(limiter, FakePlanResolver(PlanCode.PREMIUM))

    reservation = await service.reserve_consultation(uuid4())

    assert reservation.allowed is True
    assert limiter.reserve_calls == [30]


async def test_unlimited_plan_passes_none():
    limiter = FakeLimiter(count=100)
    service = make_service(
        limiter,
        FakePlanResolver(PlanCode.PREMIUM),
        USAGE_PREMIUM_CONSULTATION_LIMIT="unlimited",
    )

    await service.reserve_consultation(uuid4())

    assert limiter.reserve_calls == [None]


async def test_plan_unavailable_does_not_touch_counter():
    # プランを確認できない場合は、無料・無制限とみなさず、判定・加算しない
    limiter = FakeLimiter(count=0)

    with pytest.raises(PlanUnavailable):
        await make_service(limiter, plan_unavailable()).reserve_consultation(uuid4())
    assert limiter.reserve_calls == []


async def test_redis_failure_allows_start():
    # RL-10：Redis障害時は許可する（フェイルオープン）
    limiter = FakeLimiter(fail=True)

    reservation = await make_service(limiter).reserve_consultation(uuid4())

    assert (reservation.allowed, reservation.counted) == (True, False)


async def test_refund_delegates_to_limiter():
    limiter = FakeLimiter(count=0)
    service = make_service(limiter)
    reservation = await service.reserve_consultation(uuid4())

    await service.refund(reservation)

    assert limiter.refund_calls == [reservation]
