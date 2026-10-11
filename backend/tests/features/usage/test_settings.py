"""設定値の読み込みのテスト。"""

import pytest

from app.features.usage.settings import PlanCode, PlanLimits, load_usage_settings


def test_defaults():
    settings = load_usage_settings({})

    assert settings.limits_for(PlanCode.FREE) == PlanLimits(consultation_limit=3, memo_limit=10)
    assert settings.limits_for(PlanCode.PREMIUM) == PlanLimits(
        consultation_limit=30, memo_limit=None
    )
    assert settings.period_seconds == 30 * 24 * 60 * 60
    assert settings.redis_url == ""
    # Issue #57（質問⑧）で実測して決めた値
    assert settings.redis_connect_timeout_seconds == 0.5
    assert settings.redis_command_timeout_seconds == 0.5


def test_reads_environment():
    settings = load_usage_settings(
        {
            "USAGE_FREE_CONSULTATION_LIMIT": "5",
            "USAGE_PREMIUM_CONSULTATION_LIMIT": "unlimited",
            "USAGE_PERIOD_SECONDS": "60",
            "REDIS_URL": "redis://redis:6379/0",
            "REDIS_CONNECT_TIMEOUT_SECONDS": "0.3",
            "REDIS_COMMAND_TIMEOUT_SECONDS": "0.7",
        }
    )

    assert settings.limits_for(PlanCode.FREE).consultation_limit == 5
    # "unlimited" を明示した場合だけ無制限（None）
    assert settings.limits_for(PlanCode.PREMIUM).consultation_limit is None
    assert settings.period_seconds == 60
    assert settings.redis_connect_timeout_seconds == 0.3
    assert settings.redis_command_timeout_seconds == 0.7


@pytest.mark.parametrize(
    ("name", "value"),
    [
        # 不正な値・空欄を「無制限」とみなさず、起動時にエラーにする
        ("USAGE_FREE_CONSULTATION_LIMIT", ""),
        ("USAGE_FREE_CONSULTATION_LIMIT", "abc"),
        ("USAGE_FREE_CONSULTATION_LIMIT", "-1"),
        ("USAGE_PREMIUM_MEMO_LIMIT", "null"),
        ("USAGE_PERIOD_SECONDS", "0"),
        ("REDIS_CONNECT_TIMEOUT_SECONDS", "0"),
        ("REDIS_COMMAND_TIMEOUT_SECONDS", "x"),
    ],
)
def test_invalid_values_raise(name, value):
    with pytest.raises(ValueError) as exc_info:
        load_usage_settings({name: value})
    assert name in str(exc_info.value)
