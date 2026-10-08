"""ユーザーAPIの返却形式のテスト。"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.features.users.schemas import UserResponse


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
