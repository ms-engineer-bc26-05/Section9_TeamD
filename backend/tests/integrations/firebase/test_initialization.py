"""Firebase初期化のテスト。実際のSDK初期化は行わない。"""

from unittest.mock import Mock

import pytest

from app.integrations.firebase import client


@pytest.fixture(autouse=True)
def initialization_mock(monkeypatch):
    initialize = Mock(return_value=Mock())

    monkeypatch.setattr(client, "_app", None)
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "dummy-project")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(
        client.firebase_admin, "initialize_app", initialize
    )

    return initialize


def test_initializes_once_and_reuses(initialization_mock):
    first = client.get_firebase_app()
    second = client.get_firebase_app()

    assert first is initialization_mock.return_value
    assert second is first
    initialization_mock.assert_called_once_with(
        options={"projectId": "dummy-project"},
        name="porori-auth",
    )


@pytest.mark.parametrize("project_id", [None, "", "   "])
def test_missing_project_does_not_initialize(
    monkeypatch, initialization_mock, project_id
):
    if project_id is None:
        monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    else:
        monkeypatch.setenv("FIREBASE_PROJECT_ID", project_id)

    with pytest.raises(client.AuthServiceUnavailableError):
        client.get_firebase_app()

    initialization_mock.assert_not_called()


def test_emulator_setting_is_rejected(monkeypatch, initialization_mock):
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")

    with pytest.raises(client.AuthServiceUnavailableError):
        client.get_firebase_app()

    initialization_mock.assert_not_called()


def test_initialization_failure_hides_details_and_can_retry(
    initialization_mock, caplog
):
    app = Mock()
    initialization_mock.side_effect = [
        RuntimeError("DUMMY_SECRET_MARKER"),
        app,
    ]

    with pytest.raises(client.AuthServiceUnavailableError) as caught:
        client.get_firebase_app()

    assert str(caught.value) == "Authentication service unavailable"
    assert "DUMMY_SECRET_MARKER" not in caplog.text
    assert client._app is None

    assert client.get_firebase_app() is app
    assert initialization_mock.call_count == 2
