"""利用中のプランの判定（#92）と、有料の利用権限の付与（#95。F-05から移動）。

F-05（決済）・GET /usage・保存件数の上限は、どれもこの get_current_plan でプランを判定する（#95）。
「有料」の条件は次のとおり（#59・#92で決定）。

- user_entitlements.status が 'active'
- valid_from が now 以前
- valid_until が NULL か、now より後
- プランの code が 'free' 以外

テーブル定義（Model）は、#92でじまさんと合意したとおり payments/models.py のものを使う。
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.dialects.postgresql import insert
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


async def grant_paid_entitlement(
    session: AsyncSession,
    user_id: UUID,
    plan_id: UUID,
    now: datetime,
) -> None:
    """有料の利用権限を付与する（決済の確認から呼ぶ。#59で決めた形を F-05 から移動。#95）。

    1ユーザー1行（あれば上書き）。買い切りのため status は active、valid_until は NULL。
    呼び出し元のトランザクションの中で実行し、commit・ロックは呼び出し元で行う。
    """
    values = {
        "plan_id": plan_id,
        "status": "active",
        "valid_from": now,
        "valid_until": None,
        "updated_at": now,
    }
    statement = (
        insert(UserEntitlementRow)
        .values(user_id=user_id, **values)
        .on_conflict_do_update(index_elements=[UserEntitlementRow.user_id], set_=values)
    )
    await session.execute(statement)
