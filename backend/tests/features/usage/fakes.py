"""テスト用の偽物（Redis・DBへは接続しない）。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from app.features.usage.exceptions import PlanUnavailable, UserStatusUnavailable
from app.features.usage.limiter import Reservation, UsageCounter
from app.features.usage.settings import PlanCode, load_usage_settings
from app.features.usage.users import UserStatus


def make_settings(**env: str):
    return load_usage_settings(env)


class FakePlanResolver:
    def __init__(self, plan: PlanCode | Exception = PlanCode.FREE) -> None:
        self.plan = plan
        self.calls = 0

    async def resolve(self, user_id: UUID) -> PlanCode:
        self.calls += 1
        if isinstance(self.plan, Exception):
            raise self.plan
        return self.plan


def plan_unavailable() -> FakePlanResolver:
    return FakePlanResolver(PlanUnavailable())


class FakeMemoCounter:
    def __init__(self, count: int = 0) -> None:
        self.value = count

    async def count(self, user_id: UUID) -> int:
        return self.value


class FakeLimiter:
    """UsageLimiter と同じ呼び出し方をする偽物。呼び出しを記録する"""

    def __init__(
        self,
        count: int | None = 0,
        resets_at: datetime | None = None,
        fail: bool = False,
    ) -> None:
        self.count = count
        self.resets_at = resets_at
        self.fail = fail  # True ならRedis障害を模す
        self.reserve_calls: list[int | None] = []
        self.refund_calls: list[Reservation] = []
        self.delete_calls = 0

    async def reserve(self, user_id: UUID, limit: int | None) -> Reservation:
        self.reserve_calls.append(limit)
        if self.fail:
            return Reservation(user_id=user_id, allowed=True, counted=False, count=None)
        if limit is not None and self.count >= limit:
            return Reservation(user_id=user_id, allowed=False, counted=False, count=self.count)
        self.count += 1
        return Reservation(
            user_id=user_id, allowed=True, counted=True, count=self.count, period_id="p1"
        )

    async def refund(self, reservation: Reservation) -> bool:
        """本物と同じく、加算した予約だけを1回だけ戻す"""
        self.refund_calls.append(reservation)
        if not reservation.counted or reservation.refunded:
            return False
        reservation.refunded = True
        self.count -= 1
        return True

    async def delete_user_usage(self, user_id: UUID) -> None:
        self.delete_calls += 1
        self.count = 0

    async def get_counter(self, user_id: UUID) -> UsageCounter | None:
        if self.fail:
            return None
        return UsageCounter(count=self.count, resets_at=self.resets_at)


class FakeUserStatusChecker:
    def __init__(self, status: UserStatus | None = UserStatus.ACTIVE) -> None:
        # None ならDB障害を模す
        self.status = status
        self.calls = 0

    async def get_status(self, user_id: UUID) -> UserStatus:
        self.calls += 1
        if self.status is None:
            raise UserStatusUnavailable
        return self.status


class _NoopTicket:
    async def refund(self) -> None:
        return None


class AllowAllStartGate:
    """相談機能のテスト用。利用回数を判定せず、常に相談開始を許可する"""

    @asynccontextmanager
    async def consultation_start(self, user_id: UUID) -> AsyncIterator[_NoopTicket]:
        yield _NoopTicket()
