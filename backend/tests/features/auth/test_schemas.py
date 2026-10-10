from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.features.auth.schemas import CurrentUser


def test_current_user_accepts_generated_uuid():
    user_id = uuid4()

    user = CurrentUser(user_id=user_id)

    assert user.user_id == user_id
    assert isinstance(user.user_id, UUID)


def test_current_user_accepts_fixed_uuid():
    user_id = UUID("11111111-1111-4111-8111-111111111111")

    user = CurrentUser(user_id=user_id)

    assert user.user_id == user_id


def test_current_user_requires_user_id():
    with pytest.raises(ValidationError):
        CurrentUser()


def test_current_user_rejects_invalid_uuid():
    with pytest.raises(ValidationError):
        CurrentUser(user_id="not-a-uuid")


def test_current_user_rejects_unknown_field():
    with pytest.raises(ValidationError):
        CurrentUser(
            user_id=uuid4(),
            unexpected="dummy",
        )
