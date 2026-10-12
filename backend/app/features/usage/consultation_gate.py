"""相談開始APIへの利用回数の組み込み（Issue #57）。

相談開始（POST /consultations）は、次の順に処理する。

1. 利用回数を判定して加算する
   - 上限超過：403 USAGE_LIMIT_EXCEEDED（加算しない・AIを呼ばない）
   - プランを確認できない：503（加算しない・AIを呼ばない）
   - Redis障害：許可し、加算しない（フェイルオープン）
2. ユーザーの状態をDBからもう一度確認する（質問⑨。退会処理との同時実行への対策）
   - 退会処理中：403 ACCOUNT_DELETING。そのユーザーのキーを丸ごと削除する
   - ユーザーがいない（退会完了）：401 UNAUTHORIZED。キーを丸ごと削除する
   - DB障害で確認できない：503（DB_UNAVAILABLE）。加算した1回を戻す
   - 確認中に中断・想定外の例外が起きた：加算した1回を戻す
3. 相談を開始する（AIを呼ぶ）
   - 失敗（AIの失敗・同時開始の409・404・そのほかの例外）：加算した1回を戻す
4. 開始時に安全案内へ切り替わった場合：加算した1回を戻す（呼び出し側で ticket.refund()）

状態の確認を AI を呼ぶ前に行うため、退会処理中のユーザーのためにAIの利用料はかからない。

使い方（相談Router）：

    async with gate.consultation_start(user_id) as ticket:
        state = await service.start(...)
        if state.status is ConsultationStatus.SAFETY_GUIDANCE:
            await ticket.refund()

テストでは get_consultation_start_gate を dependency_overrides で差し替えるか、
_gate_provider を差し替える（相談機能のテストでは tests/features/consultations/conftest.py で、
常に許可する偽物に自動で差し替えている）。
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from app.features.usage.exceptions import AccountDeleting, NotAuthenticated
from app.features.usage.limiter import Reservation, get_usage_limiter
from app.features.usage.memos import get_memo_counter
from app.features.usage.plans import get_plan_resolver
from app.features.usage.service import UsageService
from app.features.usage.settings import get_usage_settings
from app.features.usage.users import UserStatus, UserStatusChecker, get_user_status_checker


class StartTicket:
    """相談開始1回分の利用回数。refund() は何度呼んでも1回だけ戻す"""

    def __init__(self, usage: UsageService, reservation: Reservation) -> None:
        self._usage = usage
        self._reservation = reservation

    async def refund(self) -> None:
        # 応答の取り消しなどで処理が中断されても、戻す処理は最後まで行う
        await asyncio.shield(self._usage.refund(self._reservation))

    def settle_without_refund(self) -> None:
        """キーを丸ごと削除した場合など、これ以上戻す必要がないことを記録する。

        削除した後に戻す処理を重ねて呼ばないようにする（Redisへの操作を重複させない）。
        """
        self._reservation.refunded = True


class ConsultationStartGate:
    def __init__(self, usage: UsageService, users: UserStatusChecker) -> None:
        self._usage = usage
        self._users = users

    async def _confirm_user(self, user_id: UUID, ticket: StartTicket) -> None:
        """加算後にユーザーの状態をDBから取り直す（質問⑨）。

        DB障害（UserStatusUnavailable）・中断・想定外の例外は、呼び出し側で1回戻す。
        """
        status = await self._users.get_status(user_id)
        if status is UserStatus.ACTIVE:
            return
        # 退会処理中・退会完了：加算できたか分からない回も含めて、キーを丸ごと削除する。
        # 削除したので、このあと戻す処理は行わない
        await asyncio.shield(self._usage.discard_user_usage_quietly(user_id))
        ticket.settle_without_refund()
        if status is UserStatus.DELETING:
            raise AccountDeleting
        raise NotAuthenticated

    @asynccontextmanager
    async def consultation_start(self, user_id: UUID) -> AsyncIterator[StartTicket]:
        reservation = await self._usage.reserve_consultation(user_id)
        ticket = StartTicket(self._usage, reservation)
        # 加算したあとは、状態の確認から相談開始の終わりまでを「失敗したら戻す」範囲にする。
        # 状態の確認中に中断（キャンセル）や想定外の例外が起きた場合も、加算した1回を残さない
        try:
            await self._confirm_user(user_id, ticket)
            yield ticket
        except BaseException:
            await ticket.refund()
            raise


def _default_gate() -> ConsultationStartGate:
    usage = UsageService(
        get_usage_limiter(), get_plan_resolver(), get_memo_counter(), get_usage_settings()
    )
    return ConsultationStartGate(usage, get_user_status_checker())


# テストで差し替えられるよう、作り方を変数に持つ
_gate_provider: Callable[[], ConsultationStartGate] = _default_gate


def get_consultation_start_gate() -> ConsultationStartGate:
    """相談開始で使う利用回数の判定。テストでは dependency_overrides 等で差し替える"""
    return _gate_provider()
