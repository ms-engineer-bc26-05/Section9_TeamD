"""メモ機能のテストの共通設定。

保存件数の上限（#94）は、利用回数側のプランの判定（usage/plans.py の get_plan_resolver）を使う。
#92でプランの判定がDB（user_entitlements）を読むようになったため、メモ機能のテストでは
プランの判定を「常に無料プラン」の偽物へ自動で差し替える（DBへは接続しない）。

上限値とプランの組み合わせは test_limits.py で、テストごとに差し替えて確認する
（テストの中で monkeypatch した場合は、そちらが優先される）。
"""

import pytest

from app.features.memos import limits
from tests.features.usage.fakes import FakePlanResolver


@pytest.fixture(autouse=True)
def free_plan(monkeypatch):
    resolver = FakePlanResolver()
    monkeypatch.setattr(limits, "get_plan_resolver", lambda: resolver)
    return resolver
