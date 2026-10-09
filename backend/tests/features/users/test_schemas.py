"""ユーザーAPIの返却形式のテスト。"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.features.users.schemas import UserNoticeUpdate, UserResponse


def test_user_response_serializes_internal_uuid():
    user_id = UUID("11111111-1111-4111-8111-111111111111")

    response = UserResponse(
        user_id=user_id,
        has_seen_notice=False,
    )

    assert response.model_dump(mode="json") == {
        "user_id": str(user_id),
        "has_seen_notice": False,
    }


def test_user_response_rejects_extra_fields():
    with pytest.raises(ValidationError):
        UserResponse(
            user_id=UUID("11111111-1111-4111-8111-111111111111"),
            has_seen_notice=False,
            firebase_uid="dummy-firebase-uid",
        )


def test_notice_update_accepts_true():
    request = UserNoticeUpdate(has_seen_notice=True)

    assert request.has_seen_notice is True


@pytest.mark.parametrize(
    "payload",
    [
        {"has_seen_notice": False},
        {"has_seen_notice": "true"},
        {"has_seen_notice": "false"},
        {"has_seen_notice": 1},
        {"has_seen_notice": 0},
        {"has_seen_notice": None},
        {},
        {"has_seen_notice": True, "unexpected": "dummy"},
    ],
)
def test_notice_update_rejects_invalid_input(payload):
    with pytest.raises(ValidationError):
        UserNoticeUpdate.model_validate(payload)
