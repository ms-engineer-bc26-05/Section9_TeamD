"""利用中のプランの判定（Issue #57・#59）。

- user_entitlements（F-05で作成）を読む本実装は、F-05のマージ後に差し替える
- それまでは「利用権限の行がない＝無料プラン」（DB設計 user_entitlements）として扱う
- DB障害などで利用権限を確認できない場合は、無料にも有料にもせず PlanUnavailable を送出する
"""

from typing import Protocol
from uuid import UUID

from app.features.usage.settings import PlanCode


class PlanResolver(Protocol):
    async def resolve(self, user_id: UUID) -> PlanCode:
        """利用中のプランを返す。確認できない場合は PlanUnavailable を送出する"""
        ...


class FreePlanResolver:
    """F-05の利用権限を読むまでの仮実装。全員を無料プランとして扱う"""

    async def resolve(self, user_id: UUID) -> PlanCode:
        return PlanCode.FREE


_resolver = FreePlanResolver()


def get_plan_resolver() -> PlanResolver:
    """APIで使うプラン判定。テストでは dependency_overrides 等で差し替える"""
    return _resolver
