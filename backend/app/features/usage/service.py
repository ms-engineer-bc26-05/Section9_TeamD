"""利用回数とプランの判定（Issue #57）。

相談開始APIへの組み込みは consultation_gate.py で行う。
"""

import logging
from uuid import UUID

from fastapi import Depends

from app.features.usage.exceptions import UsageLimitExceeded, UsageStoreUnavailable
from app.features.usage.limiter import Reservation, UsageLimiter, get_usage_limiter
from app.features.usage.memos import MemoCounter, get_memo_counter
from app.features.usage.plans import PlanResolver, get_plan_resolver
from app.features.usage.schemas import UsageView
from app.features.usage.settings import UsageSettings, get_usage_settings

logger = logging.getLogger(__name__)


class UsageService:
    def __init__(
        self,
        limiter: UsageLimiter,
        plans: PlanResolver,
        memos: MemoCounter,
        settings: UsageSettings,
    ) -> None:
        self._limiter = limiter
        self._plans = plans
        self._memos = memos
        self._settings = settings

    async def reserve_consultation(self, user_id: UUID) -> Reservation:
        """相談を開始できるか判定し、できる場合は1回加算する。

        - 上限超過：UsageLimitExceeded（加算しない）
        - プランを確認できない：PlanUnavailable（判定・加算しない）
        - Redis障害：許可し、加算しない（フェイルオープン）
        """
        plan = await self._plans.resolve(user_id)
        limit = self._settings.limits_for(plan).consultation_limit
        reservation = await self._limiter.reserve(user_id, limit)
        if not reservation.allowed:
            raise UsageLimitExceeded
        return reservation

    async def refund(self, reservation: Reservation) -> bool:
        """そのリクエストが加算した1回分を戻す（質問③）"""
        return await self._limiter.refund(reservation)

    async def discard_user_usage_quietly(self, user_id: UUID) -> None:
        """そのユーザーのキーを丸ごと削除する（退会処理中・不在と分かった場合。質問⑨）。

        加算できたか分からない回も含めて消すため、1回分を戻すのではなく丸ごと削除する。
        Redis障害で削除できなかった場合は記録だけ残す（相談開始の拒否は続ける）。
        """
        try:
            await self._limiter.delete_user_usage(user_id)
        except UsageStoreUnavailable:
            logger.warning("usage key delete skipped")

    async def get_usage(self, user_id: UUID) -> UsageView:
        plan = await self._plans.resolve(user_id)
        limits = self._settings.limits_for(plan)
        memo_count = await self._memos.count(user_id)
        counter = await self._limiter.get_counter(user_id)

        if counter is None:
            # Redis障害：回数は不明。相談開始は止めない（質問⑥）
            count, resets_at, can_start = None, None, True
        elif limits.consultation_limit is None:
            # 無制限：回数は表示用に返し、リセット日は返さない（質問⑤）
            count, resets_at, can_start = counter.count, None, True
        else:
            count = counter.count
            resets_at = counter.resets_at
            can_start = counter.count < limits.consultation_limit

        return UsageView(
            plan_code=plan,
            consultation_count=count,
            consultation_limit=limits.consultation_limit,
            can_start_consultation=can_start,
            consultation_resets_at=resets_at,
            memo_count=memo_count,
            memo_limit=limits.memo_limit,
        )


def get_usage_service(
    limiter: UsageLimiter = Depends(get_usage_limiter),
    plans: PlanResolver = Depends(get_plan_resolver),
    memos: MemoCounter = Depends(get_memo_counter),
    settings: UsageSettings = Depends(get_usage_settings),
) -> UsageService:
    return UsageService(limiter, plans, memos, settings)
