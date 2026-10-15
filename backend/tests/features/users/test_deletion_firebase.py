"""No Firebase connection: SDK boundary behavior only."""

from unittest.mock import Mock

import pytest

from app.features.users.deletion_service import verify_deletion_token
from app.integrations.firebase import client, deletion
from app.integrations.firebase.client import AuthServiceUnavailableError


@pytest.mark.parametrize("check_revoked", [False, True])
async def test_deletion_verifier_passes_revocation_flag(monkeypatch, check_revoked):
    verify = Mock(return_value="synthetic-uid")
    monkeypatch.setattr(client, "verify_token", verify)
    assert (
        await verify_deletion_token("synthetic-token", check_revoked=check_revoked)
        == "synthetic-uid"
    )
    verify.assert_called_once_with("synthetic-token", check_revoked=check_revoked)


@pytest.mark.parametrize("operation", ["delete_user", "user_is_absent"])
def test_absence_is_idempotent(monkeypatch, operation):
    monkeypatch.setattr(deletion, "get_firebase_app", lambda: object())
    sdk_name = "delete_user" if operation == "delete_user" else "get_user"
    monkeypatch.setattr(
        deletion.auth, sdk_name, Mock(side_effect=deletion.auth.UserNotFoundError("synthetic"))
    )
    result = getattr(deletion, operation)("synthetic-uid")
    assert result is (None if operation == "delete_user" else True)


@pytest.mark.parametrize("operation", ["delete_user", "user_is_absent"])
def test_connection_failure_is_never_absence(monkeypatch, operation):
    monkeypatch.setattr(deletion, "get_firebase_app", lambda: object())
    sdk_name = "delete_user" if operation == "delete_user" else "get_user"
    monkeypatch.setattr(deletion.auth, sdk_name, Mock(side_effect=RuntimeError("synthetic-secret")))
    with pytest.raises(AuthServiceUnavailableError) as error:
        getattr(deletion, operation)("synthetic-uid")
    assert "synthetic-secret" not in str(error.value)


def test_existing_user_is_not_absent(monkeypatch):
    monkeypatch.setattr(deletion, "get_firebase_app", lambda: object())
    monkeypatch.setattr(deletion.auth, "get_user", Mock(return_value=object()))
    assert deletion.user_is_absent("synthetic-uid") is False
