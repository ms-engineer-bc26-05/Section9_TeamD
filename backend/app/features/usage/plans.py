"""利用中のプランの判定（Issue #57・#59・#92）。

プランの判定は plans/public.py の get_current_plan を使う（#92）。
- get_current_plan は状態の取得だけを行う。セッションはここで開き、閉じる（読むだけなのでcommitしない）
- 利用権限の行がない場合は無料プラン（DB設計 user_entitlements）
- DBの接続障害で利用権限を確認できない場合は、無料にも有料にもせず PlanUnavailable（503）を送出する
- それ以外の例外は、ユーザー状態の確認（usage/users.py）・#47と同じく、そのまま上へ送る
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.core.database_errors import is_database_connection_error
from app.core.exceptions import DatabaseUnavailableError
from app.features.plans.public import PlanCode, get_current_plan
from app.features.usage.exceptions import PlanUnavailable


class PlanResolver(Protocol):
    async def resolve(self, user_id: UUID) -> PlanCode:
        """利用中のプランを返す。確認できない場合は PlanUnavailable を送出する"""
        ...


def _now() -> datetime:
    return datetime.now(UTC)


class DbPlanResolver:
    """DBの user_entitlements からプランを判定する"""

    def __init__(
        self,
        session_factory: Callable[[], async_sessionmaker[AsyncSession]] = get_session_factory,
        now: Callable[[], datetime] = _now,
    ) -> None:
        # import時にDBへ接続しないよう、作り方（関数）を持ち、判定のたびに呼ぶ
        self._session_factory = session_factory
        self._now = now

    async def resolve(self, user_id: UUID) -> PlanCode:
        try:
            async with self._session_factory()() as session:
                return await get_current_plan(session, user_id, self._now())
        except DatabaseUnavailableError:
            # 新しい接続を作る処理のタイムアウト（app.core.database）
            raise PlanUnavailable from None
        except Exception as error:
            if is_database_connection_error(error):
                # DBの例外のメッセージは接続情報を含みうるため、from None で捨てる
                raise PlanUnavailable from None
            raise


_resolver = DbPlanResolver()


def get_plan_resolver() -> PlanResolver:
    """APIで使うプラン判定。テストでは dependency_overrides 等で差し替える"""
    return _resolver
