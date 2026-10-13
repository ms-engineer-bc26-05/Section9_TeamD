"""保存件数の上限値（API設計6.5.2の403・#94）。

上限値とプランの判定は、利用回数制限（#57・PR #90）の設定値・プラン判定を使う。
GET /usage の memo_limit と同じ値で判定し、画面の表示と保存の判定がずれないようにする。
plans/public.py の get_current_plan ができたら、そちらへ差し替える（#92・#95）。
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from app.features.usage.plans import get_plan_resolver
from app.features.usage.settings import get_usage_settings

# user_id → そのユーザーの保存件数の上限（None は無制限）
GetMemoLimit = Callable[[UUID], Awaitable[int | None]]


async def get_memo_limit(user_id: UUID) -> int | None:
    """プランを確認できない場合は PlanUnavailable を送出する（無料・無制限とみなさない）"""
    plan = await get_plan_resolver().resolve(user_id)
    return get_usage_settings().limits_for(plan).memo_limit
