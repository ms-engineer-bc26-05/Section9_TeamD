"""利用中のプランの判定（#92。F-05の user_entitlements を読む）。

「有料」の条件は、F-05（#59）の payments/db_repository.py の has_paid_entitlement とそろえる
（#92でじまさんと合意）。#95で F-05 側をこちらへ差し替えるまで、2か所の条件を同じに保つ。

- user_entitlements.status が 'active'
- valid_from が now 以前
- valid_until が NULL か、now より後
- プランの code が 'free' 以外

テーブル定義（Model）は、#92でじまさんと合意したとおり payments/models.py のものを使う。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.payments.models import PlanRow, UserEntitlementRow
from app.features.plans.settings import PlanCode


async def get_current_plan(
    session: AsyncSession,
    user_id: UUID,
    now: datetime,
) -> PlanCode:
    """利用中のプランを返す。有料の利用権限が有効なら premium、それ以外は free。

    利用権限の行がない場合は無料（DB設計 user_entitlements）。
    状態の取得だけを行い、セッションの終了・commitは呼び出し元で行う。
    DBの例外は変換せずにそのまま送出する（接続障害の扱いは呼び出し元で決める）。
    """
    statement = select(
        exists().where(
            UserEntitlementRow.user_id == user_id,
            UserEntitlementRow.status == "active",
            UserEntitlementRow.valid_from <= now,
            or_(UserEntitlementRow.valid_until.is_(None), UserEntitlementRow.valid_until > now),
            PlanRow.id == UserEntitlementRow.plan_id,
            PlanRow.code != PlanCode.FREE.value,
        )
    )
    paid = bool((await session.execute(statement)).scalar_one())
    return PlanCode.PREMIUM if paid else PlanCode.FREE
