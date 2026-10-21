"""プランごとの上限値（plans/settings.py。#92で usage/ から移動）と Stripe PriceのID（#95）のテスト。"""

import pytest

from app.features.payments.settings import load_checkout_settings
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
    # 利用回数側（GET /usage・相談開始）は、メモ保存（memos/limits.py の get_plan_settings）と同じ上限値を使う
    env = {"USAGE_FREE_CONSULTATION_LIMIT": "7", "USAGE_PREMIUM_MEMO_LIMIT": "unlimited"}

    assert load_usage_settings(env).plan_limits == load_plan_settings(env).plan_limits


def test_stripe_price_id_is_read_separately_from_limits():
    # 環境変数の名前は F-05 のまま。上限値とは別の項目として持つ（#59）
    settings = load_plan_settings({"STRIPE_PRICE_ID_PREMIUM": " price_test \n"})

    assert settings.stripe_price_ids == {PlanCode.PREMIUM: "price_test"}
    assert settings.limits_for(PlanCode.PREMIUM) == load_plan_settings({}).limits_for(
        PlanCode.PREMIUM
    )


@pytest.mark.parametrize("env", [{}, {"STRIPE_PRICE_ID_PREMIUM": "  "}])
def test_missing_stripe_price_id_is_not_set(env):
    # 未設定のプランは購入できない（422 PLAN_NOT_AVAILABLE）。無料のプランには Price IDを持たない
    assert load_plan_settings(env).stripe_price_ids == {}


def test_price_id_is_not_in_repr():
    settings = load_plan_settings({"STRIPE_PRICE_ID_PREMIUM": "price_secret_like"})

    assert "price_secret_like" not in repr(settings)


def test_checkout_settings_read_price_id_from_plan_settings(monkeypatch):
    # 決済（F-05）は plans/ の設定から Price IDを読む（#95）
    monkeypatch.setenv("STRIPE_PRICE_ID_PREMIUM", "price_from_plans")

    assert load_checkout_settings().price_ids == {"premium": "price_from_plans"}


def test_checkout_settings_without_price_id(monkeypatch):
    monkeypatch.delenv("STRIPE_PRICE_ID_PREMIUM", raising=False)

    assert load_checkout_settings().price_ids == {}
