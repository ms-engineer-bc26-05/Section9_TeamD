"""相談機能の型（schemas.py）のテスト。テストデータはすべて架空。"""

import pytest
from pydantic import ValidationError

from app.features.consultations.schemas import (
    ApprovableResult,
    ConsultationResultInput,
    EmotionCategory,
    EmotionInput,
    EventDetailsInput,
)


def test_emotion_input_accepts_detail():
    emotion = EmotionInput(category="anxious", detail="架空の気持ち")
    assert emotion.category is EmotionCategory.ANXIOUS


def test_emotion_input_accepts_cannot_verbalize():
    emotion = EmotionInput(category="other", cannot_verbalize=True)
    assert emotion.detail is None


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "anxious"},  # どちらもない
        {"category": "anxious", "detail": "   "},  # 空白だけ
        {"category": "anxious", "detail": "架空", "cannot_verbalize": True},  # 両方
        {"category": "unknown", "detail": "架空"},  # 許可されていない値
        {"category": "anxious", "detail": "架空", "extra": 1},  # 想定外の項目
    ],
)
def test_emotion_input_rejects_invalid(payload):
    with pytest.raises(ValidationError):
        EmotionInput(**payload)


def test_event_details_input_rejects_blank():
    with pytest.raises(ValidationError):
        EventDetailsInput(what_happened="  ", what_bothered_me="架空")


def test_result_input_rejects_approved():
    # approvedは専用APIでのみ更新するため、PATCHでは受け付けない
    with pytest.raises(ValidationError):
        ConsultationResultInput(approved=True)


def test_approvable_result_allows_empty_background_only():
    result = ApprovableResult(
        event_summary="架空の出来事",
        emotion="架空の感情",
        true_feeling="架空の本音",
        background="",
        wish="架空の望み",
    )
    assert result.background == ""

    with pytest.raises(ValidationError):
        ApprovableResult(
            event_summary="架空の出来事",
            emotion="架空の感情",
            true_feeling="   ",  # 空白だけは空として扱う
            background="",
            wish="架空の望み",
        )


@pytest.mark.parametrize("payload", [{}, {"wish": None}, {"background": None}])
def test_result_input_rejects_empty_and_null(payload):
    with pytest.raises(ValidationError):
        ConsultationResultInput(**payload)


def test_result_input_allows_empty_background():
    assert ConsultationResultInput(background="").background == ""
