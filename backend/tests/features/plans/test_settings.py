"""プランごとの上限値（plans/settings.py。#92で usage/ から移動）のテスト。"""

import pytest

from app.features.plans.public import PlanCode, PlanLimits, load_plan_settings
from app.features.usage.settings import load_usage_settings


def test_defaults():
    settings = load_plan_settings({})

    assert settings.limits_for(PlanCode.FREE) == PlanLimits(consultation_limit=3, memo_limit=10)
    assert settings.limits_for(PlanCode.PREMIUM) == PlanLimits(
        consultation_limit=30, memo_limit=100
    )


def test_env_names_are_unchanged_and_unlimited_is_none():
    # 環境変数の名前は #57 のまま（.env.example・compose.yaml を変えない）
    settings = load_plan_settings(
        {"USAGE_FREE_CONSULTATION_LIMIT": "5", "USAGE_PREMIUM_MEMO_LIMIT": "unlimited"}
    )

    assert settings.limits_for(PlanCode.FREE).consultation_limit == 5
    assert settings.limits_for(PlanCode.PREMIUM).memo_limit is None


@pytest.mark.parametrize("value", ["-1", "abc", "", "null"])
def test_invalid_limit_is_rejected_without_value(value):
    # 読み込みに失敗した値を無制限とみなさない。メッセージに値そのものを含めない
    with pytest.raises(ValueError) as caught:
        load_plan_settings({"USAGE_FREE_MEMO_LIMIT": value})

    assert "USAGE_FREE_MEMO_LIMIT" in str(caught.value)
    if value:
        assert value not in str(caught.value)


def test_usage_settings_use_plan_limits():
    # 利用回数側（GET /usage・相談開始・保存件数の上限）は、plans/ と同じ上限値を使う
    env = {"USAGE_FREE_CONSULTATION_LIMIT": "7", "USAGE_PREMIUM_MEMO_LIMIT": "unlimited"}

    assert load_usage_settings(env).plan_limits == load_plan_settings(env).plan_limits
