"""利用状況APIのレスポンス（docs/api-design.md 6.7）。"""

from datetime import datetime

from pydantic import BaseModel

from app.features.usage.settings import PlanCode


class UsageView(BaseModel):
    """GET /api/v1/usage

    null の意味（画面で見分ける）：
    - consultation_count     : Redisから取得できず、回数が分からない
    - consultation_limit     : 無制限
    - consultation_resets_at : まだ使っていない・無制限・回数が分からない
    - memo_limit             : 無制限
    """

    plan_code: PlanCode
    consultation_count: int | None
    consultation_limit: int | None
    can_start_consultation: bool
    consultation_resets_at: datetime | None
    memo_count: int
    memo_limit: int | None
