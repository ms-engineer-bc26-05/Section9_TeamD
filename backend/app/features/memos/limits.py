"""保存件数の上限値（API設計6.5.2の403・#94）。

上限値は plans/public.py の設定値、プランの判定は利用回数制限と同じ判定（usage/plans.py の
DbPlanResolver。中で plans/public.py の get_current_plan を使う）を使う（#92・#95）。
GET /usage の memo_limit と同じ値で判定し、画面の表示と保存の判定がずれないようにする。

プランの判定は、保存のトランザクション（ユーザー行のロック）の前に、別のセッションで行う（#94で決定）。
判定と保存の間に有料になった場合は、無料の上限で判定されるだけで、上限を超えて保存されることはない。
有料から無料に戻る流れ（返金・期限切れなど）は今はない（買い切りで valid_until は NULL。#59）ため考えていない。
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from app.features.plans.public import get_plan_settings
from app.features.usage.plans import get_plan_resolver

# user_id → そのユーザーの保存件数の上限（None は無制限）
GetMemoLimit = Callable[[UUID], Awaitable[int | None]]


async def get_memo_limit(user_id: UUID) -> int | None:
    """プランを確認できない場合は PlanUnavailable を送出する（無料・無制限とみなさない）"""
    plan = await get_plan_resolver().resolve(user_id)
    return get_plan_settings().limits_for(plan).memo_limit
