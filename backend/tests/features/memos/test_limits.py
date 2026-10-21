"""保存件数の上限値の取得（#94）のテスト。プラン判定・設定値は偽物にする。"""

from uuid import uuid4

import pytest

from app.features.memos import limits
from app.features.plans.public import PlanCode
from app.features.usage.exceptions import PlanUnavailable

from tests.features.usage.fakes import FakePlanResolver, make_settings, plan_unavailable


@pytest.mark.parametrize(
    ("plan", "env", "expected"),
    [
        (PlanCode.FREE, {}, 10),  # #59・PR #90の既定値
        (PlanCode.PREMIUM, {}, 100),
        (PlanCode.FREE, {"USAGE_FREE_MEMO_LIMIT": "3"}, 3),
        (PlanCode.PREMIUM, {"USAGE_PREMIUM_MEMO_LIMIT": "unlimited"}, None),
    ],
)
async def test_returns_memo_limit_of_current_plan(monkeypatch, plan, env, expected):
    # GET /usage の memo_limit と同じ設定値・プラン判定を使う
    monkeypatch.setattr(limits, "get_plan_resolver", lambda: FakePlanResolver(plan))
    monkeypatch.setattr(limits, "get_plan_settings", lambda: make_settings(**env))

    assert await limits.get_memo_limit(uuid4()) == expected


async def test_plan_unavailable_is_not_treated_as_free(monkeypatch):
    monkeypatch.setattr(limits, "get_plan_resolver", plan_unavailable)
    monkeypatch.setattr(limits, "get_plan_settings", lambda: make_settings())

    with pytest.raises(PlanUnavailable):
        await limits.get_memo_limit(uuid4())
