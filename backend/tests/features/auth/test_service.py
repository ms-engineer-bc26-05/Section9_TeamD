"""認証処理のテスト。Firebase・DBへは接続しない。"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.features.auth import service
from app.integrations.firebase.client import (
    AuthServiceUnavailableError,
    InvalidTokenError,
)


@pytest.fixture
def auth_mocks(monkeypatch):
    user = Mock(id=uuid4(), status="active")
    lookup = AsyncMock(return_value=user)
    thread = AsyncMock(return_value="dummy-firebase-uid")

    session = Mock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = False
    factory = Mock(return_value=context)

    monkeypatch.setattr(service, "to_thread", thread)
    monkeypatch.setattr(service, "get_user_by_firebase_uid", lookup)
    monkeypatch.setattr(service, "get_session_factory", Mock(return_value=factory))

    return user, lookup, thread, session, context, factory


async def test_authenticate_returns_internal_uuid_and_closes_session(auth_mocks):
    user, lookup, thread, session, context, factory = auth_mocks

    current_user = await service.authenticate_user("dummy-token")

    assert current_user.user_id == user.id
    thread.assert_awaited_once_with(
        service.verify_token,
        "dummy-token",
        check_revoked=False,
    )
    factory.assert_called_once_with()
    lookup.assert_awaited_once_with(session, "dummy-firebase-uid")
    context.__aexit__.assert_awaited_once_with(None, None, None)
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (None, service.AuthenticationRequiredError),
        ("deleting", service.AccountDeletingError),
        ("unexpected", RuntimeError),
    ],
)
async def test_unavailable_user_is_rejected_and_session_closed(auth_mocks, status, expected_error):
    user, lookup, _, session, context, _ = auth_mocks

    if status is None:
        lookup.return_value = None
    else:
        user.status = status

    with pytest.raises(expected_error) as caught:
        await service.authenticate_user("dummy-token")

    context.__aexit__.assert_awaited_once()
    assert context.__aexit__.await_args.args[0] is expected_error
    assert context.__aexit__.await_args.args[1] is caught.value
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (InvalidTokenError("Dummy secret"), service.AuthenticationRequiredError),
        (AuthServiceUnavailableError("Dummy secret"), service.AuthServiceUnavailableError),
    ],
)
async def test_verification_failure_does_not_open_db(auth_mocks, error, expected_error):
    _, lookup, thread, _, context, factory = auth_mocks
    thread.side_effect = error

    with pytest.raises(expected_error) as caught:
        await service.authenticate_user("dummy-token")

    assert "Dummy secret" not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    service.get_session_factory.assert_not_called()
    factory.assert_not_called()
    context.__aenter__.assert_not_awaited()
    lookup.assert_not_awaited()


async def test_db_failure_propagates_and_closes_session(auth_mocks):
    _, lookup, _, session, context, _ = auth_mocks
    error = OperationalError(
        "SELECT dummy",
        {},
        RuntimeError("Dummy database failure"),
    )
    lookup.side_effect = error

    with pytest.raises(OperationalError) as caught:
        await service.authenticate_user("dummy-token")

    assert caught.value is error
    context.__aexit__.assert_awaited_once()
    assert context.__aexit__.await_args.args[0] is OperationalError
    assert context.__aexit__.await_args.args[1] is error
    session.add.assert_not_called()
    session.commit.assert_not_called()


async def test_db_connection_failure_is_converted_and_session_closed(auth_mocks):
    _, lookup, _, session, context, _ = auth_mocks
    marker = "DUMMY_DB_ERROR_MARKER"
    lookup.side_effect = OperationalError(
        "SELECT dummy",
        {},
        ConnectionRefusedError(marker),
    )

    with pytest.raises(service.DatabaseUnavailableError) as caught:
        await service.authenticate_user("dummy-token")

    assert str(caught.value) == "Database connection unavailable"
    assert marker not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    context.__aexit__.assert_awaited_once()
    session.add.assert_not_called()
    session.commit.assert_not_called()


async def test_integrity_error_is_not_converted(auth_mocks):
    _, lookup, _, session, context, _ = auth_mocks
    error = IntegrityError(
        "INSERT dummy",
        {},
        Exception("DUMMY_CONSTRAINT_ERROR"),
    )
    lookup.side_effect = error

    with pytest.raises(IntegrityError) as caught:
        await service.authenticate_user("dummy-token")

    assert caught.value is error
    context.__aexit__.assert_awaited_once()
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.parametrize(
    ("is_new", "has_seen_notice"),
    [(True, False), (False, True)],
)
async def test_register_or_get_user_returns_user_and_commits(monkeypatch, is_new, has_seen_notice):
    user = Mock(
        id=uuid4(),
        status="active",
        has_seen_notice=has_seen_notice,
    )
    verify = AsyncMock(return_value="dummy-firebase-uid")
    get_or_create = AsyncMock(return_value=(user, is_new))

    transaction = AsyncMock()
    transaction.__aexit__.return_value = False

    session = Mock()
    session.begin = Mock(return_value=transaction)

    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = False
    factory = Mock(return_value=session_context)

    monkeypatch.setattr(service, "to_thread", verify)
    monkeypatch.setattr(service, "get_or_create_user", get_or_create)
    monkeypatch.setattr(service, "get_session_factory", Mock(return_value=factory))

    response, created = await service.register_or_get_user("dummy-token")

    assert response.model_dump(mode="json") == {
        "user_id": str(user.id),
        "has_seen_notice": has_seen_notice,
    }
    assert created is is_new
    assert verify.await_count == 2
    verify.assert_awaited_with(
        service.verify_token,
        "dummy-token",
        check_revoked=True,
    )
    factory.assert_called_once_with()
    session.begin.assert_called_once_with()
    transaction.__aenter__.assert_awaited_once()
    get_or_create.assert_awaited_once_with(session, "dummy-firebase-uid")
    transaction.__aexit__.assert_awaited_once_with(None, None, None)
    session_context.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        ("deleting", service.AccountDeletingError),
        ("unexpected", RuntimeError),
    ],
)
async def test_register_or_get_user_rejects_unavailable_user(monkeypatch, status, expected_error):
    user = Mock(id=uuid4(), status=status, has_seen_notice=False)
    verify = AsyncMock(return_value="dummy-firebase-uid")
    get_or_create = AsyncMock(return_value=(user, False))

    transaction = AsyncMock()
    transaction.__aexit__.return_value = False

    session = Mock()
    session.begin = Mock(return_value=transaction)

    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = False
    factory = Mock(return_value=session_context)

    monkeypatch.setattr(service, "to_thread", verify)
    monkeypatch.setattr(service, "get_or_create_user", get_or_create)
    monkeypatch.setattr(service, "get_session_factory", Mock(return_value=factory))

    with pytest.raises(expected_error) as caught:
        await service.register_or_get_user("dummy-token")

    get_or_create.assert_awaited_once_with(session, "dummy-firebase-uid")
    transaction.__aenter__.assert_awaited_once()
    transaction.__aexit__.assert_awaited_once()
    assert transaction.__aexit__.await_args.args[0] is expected_error
    assert transaction.__aexit__.await_args.args[1] is caught.value

    session_context.__aexit__.assert_awaited_once()
    assert session_context.__aexit__.await_args.args[1] is caught.value


async def test_register_or_get_user_commit_failure_does_not_return_success(
    monkeypatch,
):
    user = Mock(id=uuid4(), status="active", has_seen_notice=False)
    verify = AsyncMock(return_value="dummy-firebase-uid")
    get_or_create = AsyncMock(return_value=(user, True))

    marker = "DUMMY_COMMIT_ERROR"
    error = OperationalError(
        "COMMIT",
        {},
        ConnectionRefusedError(marker),
    )

    transaction = AsyncMock()
    transaction.__aexit__.side_effect = error

    session = Mock()
    session.begin = Mock(return_value=transaction)

    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = False
    factory = Mock(return_value=session_context)

    monkeypatch.setattr(service, "to_thread", verify)
    monkeypatch.setattr(service, "get_or_create_user", get_or_create)
    monkeypatch.setattr(service, "get_session_factory", Mock(return_value=factory))

    with pytest.raises(service.DatabaseUnavailableError) as caught:
        await service.register_or_get_user("dummy-token")

    get_or_create.assert_awaited_once_with(session, "dummy-firebase-uid")
    transaction.__aexit__.assert_awaited_once_with(None, None, None)
    session_context.__aexit__.assert_awaited_once()
    assert session_context.__aexit__.await_args.args[1] is error

    assert str(caught.value) == "Database connection unavailable"
    assert marker not in str(caught.value)
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (InvalidTokenError("Dummy secret"), service.AuthenticationRequiredError),
        (AuthServiceUnavailableError("Dummy secret"), service.AuthServiceUnavailableError),
    ],
)
async def test_register_verification_failure_does_not_open_db(monkeypatch, error, expected_error):
    verify = AsyncMock(side_effect=error)
    factory = Mock()
    get_or_create = AsyncMock()

    monkeypatch.setattr(service, "to_thread", verify)
    monkeypatch.setattr(service, "get_session_factory", factory)
    monkeypatch.setattr(service, "get_or_create_user", get_or_create)

    with pytest.raises(expected_error) as caught:
        await service.register_or_get_user("dummy-token")

    verify.assert_awaited_once_with(
        service.verify_token,
        "dummy-token",
        check_revoked=True,
    )
    factory.assert_not_called()
    get_or_create.assert_not_awaited()
    assert "Dummy secret" not in str(caught.value)
    assert caught.value.__suppress_context__ is True
