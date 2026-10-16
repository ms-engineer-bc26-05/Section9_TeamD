"""Synthetic deletion tests; no external services or shared database."""

import asyncio
from unittest.mock import AsyncMock, Mock, call
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.core.exceptions import (
    AuthenticationRequiredError,
    AuthServiceUnavailableError,
    DatabaseUnavailableError,
)
from app.features.auth import service as auth_service
from app.features.payments.public import PaymentSettlementBlocked, StripeUnavailable
from app.features.usage.exceptions import UsageStoreUnavailable
from app.features.users.deletion_repository import DeletionBlocked
from app.features.users.deletion_service import DeletionService, get_deletion_service
from app.features.users.lifecycle_lock import DeletionInProgress, lifecycle_lock
from app.features.users.router import router
from app.integrations.firebase.client import InvalidTokenError


@pytest.fixture
def setup():
    events = []
    user_id = uuid4()

    def step(name, result=None):
        async def call(*args, **kwargs):
            events.append(name)
            return result

        return AsyncMock(side_effect=call)

    repo = Mock(
        begin=step("begin", user_id),
        delete_memos=step("memos"),
        finish=step("finish"),
        recovery_uid=step("lookup", "synthetic-uid"),
    )
    service = DeletionService(
        repo,
        step("discard"),
        step("settle"),
        step("redis"),
        step("firebase"),
        step("absent", True),
        step("verify", "synthetic-uid"),
    )
    return service, events


async def test_order_and_success(setup):
    service, events = setup
    await service.delete("synthetic-token")
    assert service.verify.await_args_list == [
        call("synthetic-token", check_revoked=False),
        call("synthetic-token", check_revoked=True),
    ]
    assert events == [
        "verify",
        "verify",
        "begin",
        "memos",
        "discard",
        "settle",
        "redis",
        "firebase",
        "redis",
        "finish",
    ]


@pytest.mark.parametrize(
    "target",
    ["begin", "delete_memos", "discard", "settle", "clear_usage", "remove_firebase", "finish"],
)
async def test_failure_stops_and_retry_restarts(setup, target):
    service, events = setup
    obj = service.repository if target in ("begin", "delete_memos", "finish") else service
    method = getattr(obj, target)
    original = method.side_effect
    method.side_effect = RuntimeError("synthetic private exception")
    with pytest.raises(RuntimeError):
        await service.delete("synthetic-token")
    service.repository.finish.assert_not_awaited() if target != "finish" else None
    method.side_effect = original
    await service.delete("synthetic-token")
    assert events[-1] == "finish"


async def test_final_redis_failure_never_finishes(setup):
    service, _ = setup
    service.clear_usage.side_effect = [None, UsageStoreUnavailable()]
    with pytest.raises(UsageStoreUnavailable):
        await service.delete("synthetic-token")
    service.remove_firebase.assert_awaited_once()
    service.repository.finish.assert_not_awaited()


@pytest.mark.parametrize("stage", [0, 1])
@pytest.mark.parametrize("error", [AuthenticationRequiredError, AuthServiceUnavailableError])
async def test_verification_failure_never_starts_deletion(setup, stage, error):
    service, _ = setup
    service.verify.side_effect = ["synthetic-uid"] * stage + [error()]
    with pytest.raises(error):
        await service.delete("synthetic-token")
    assert (
        service.verify.await_args_list
        == [
            call("synthetic-token", check_revoked=False),
            call("synthetic-token", check_revoked=True),
        ][: stage + 1]
    )
    service.repository.begin.assert_not_awaited()
    service.remove_firebase.assert_not_awaited()


async def test_changed_uid_after_lock_never_starts_deletion(setup):
    service, _ = setup
    service.verify.side_effect = ["synthetic-uid", "synthetic-other"]
    with pytest.raises(AuthenticationRequiredError):
        await service.delete("synthetic-token")
    service.repository.begin.assert_not_awaited()


async def test_parallel_delete_rejected_and_lock_released(setup):
    service, _ = setup
    entered, release = asyncio.Event(), asyncio.Event()

    async def settle(_):
        entered.set()
        await release.wait()

    service.settle.side_effect = settle
    task = asyncio.create_task(service.delete("synthetic-token"))
    await entered.wait()
    try:
        with pytest.raises(DeletionInProgress):
            await service.delete("synthetic-token")
    finally:
        release.set()
        await task
    await service.delete("synthetic-token")


async def test_delayed_registration_revalidates_before_db(monkeypatch):
    verified = asyncio.Event()
    checks = []

    async def verify(*args, **kwargs):
        checks.append(kwargs["check_revoked"])
        if len(checks) == 1:
            verified.set()
            return "synthetic-uid"
        raise InvalidTokenError

    monkeypatch.setattr(auth_service, "to_thread", verify)
    factory = Mock()
    monkeypatch.setattr(auth_service, "get_session_factory", factory)
    async with lifecycle_lock("synthetic-uid", deletion=True):
        task = asyncio.create_task(auth_service.register_or_get_user("synthetic-token"))
        await verified.wait()
    with pytest.raises(AuthenticationRequiredError):
        await task
    assert checks == [False, True]
    factory.assert_not_called()


async def test_recovery_requires_absence_and_repeats_cleanup(setup):
    service, events = setup
    service.absent.side_effect = None
    service.absent.return_value = False
    with pytest.raises(DeletionBlocked):
        await service.recover(uuid4())
    service.repository.begin.assert_not_awaited()
    service.absent.return_value = True
    await service.recover(uuid4())
    assert service.clear_usage.await_count == 2
    assert events[-1] == "finish"
    assert service.repository.begin.await_args.kwargs == {"recovery": True}


async def test_recovery_lookup_failure_never_deletes(setup):
    service, _ = setup
    service.absent.side_effect = RuntimeError("synthetic connection error")
    with pytest.raises(RuntimeError):
        await service.recover(uuid4())
    service.repository.begin.assert_not_awaited()
    service.clear_usage.assert_not_awaited()
    service.remove_firebase.assert_not_awaited()


async def test_cancelled_delete_releases_lock_and_retry_is_possible(setup):
    service, _ = setup
    entered = asyncio.Event()

    async def settle(_):
        entered.set()
        await asyncio.Event().wait()

    service.settle.side_effect = settle
    task = asyncio.create_task(service.delete("synthetic-token"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    service.repository.finish.assert_not_awaited()
    service.settle.side_effect = None
    await service.delete("synthetic-token")
    service.repository.finish.assert_awaited_once()


async def test_registration_lock_does_not_block_other_users():
    async with lifecycle_lock("synthetic-first"):
        async with lifecycle_lock("synthetic-other", deletion=True):
            pass


async def test_deletion_waits_for_registration(setup):
    service, _ = setup
    async with lifecycle_lock("synthetic-uid"):
        task = asyncio.create_task(service.delete("synthetic-token"))
        await asyncio.sleep(0)
        service.repository.begin.assert_not_awaited()
    await task
    service.repository.finish.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (DeletionBlocked(), 409, "ACCOUNT_DELETION_BLOCKED"),
        (PaymentSettlementBlocked(), 409, "ACCOUNT_DELETION_BLOCKED"),
        (DeletionInProgress(), 409, "ACCOUNT_DELETION_IN_PROGRESS"),
        (StripeUnavailable(), 503, "PAYMENT_UNAVAILABLE"),
        (UsageStoreUnavailable(), 503, "USAGE_UNAVAILABLE"),
        (AuthenticationRequiredError(), 401, "UNAUTHORIZED"),
        (RuntimeError("synthetic-secret"), 500, "INTERNAL_SERVER_ERROR"),
    ],
)
def test_http_errors_are_fixed(error, status, code, caplog):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    service = Mock(delete=AsyncMock(side_effect=error))
    app.dependency_overrides[get_deletion_service] = lambda: service
    with TestClient(app) as client:
        response = client.delete("/users/me", headers={"Authorization": "Bearer synthetic-token"})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "synthetic-secret" not in response.text + caplog.text
    assert "synthetic-token" not in response.text + caplog.text
    if status == 500:
        records = [r for r in caplog.records if r.name.endswith("deletion_http")]
        assert len(records) == 1
        assert records[0].getMessage() == "account deletion failed: RuntimeError"
        assert records[0].exc_info is None
        assert "RuntimeError" not in response.text
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"


def test_http_requires_auth_and_success_has_no_body():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    service = Mock(delete=AsyncMock())
    app.dependency_overrides[get_deletion_service] = lambda: service
    with TestClient(app) as client:
        assert client.delete("/users/me").status_code == 401
        service.delete.assert_not_awaited()
        response = client.delete("/users/me", headers={"Authorization": "Bearer synthetic-token"})
    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.parametrize("error", [AuthServiceUnavailableError(), DatabaseUnavailableError()])
def test_common_connection_errors_remain_503(error):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    service = Mock(delete=AsyncMock(side_effect=error))
    app.dependency_overrides[get_deletion_service] = lambda: service
    with TestClient(app) as client:
        response = client.delete("/users/me", headers={"Authorization": "Bearer synthetic-token"})
    assert response.status_code == 503


def test_missing_token_does_not_initialize_deletion_dependencies():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    factory = Mock(side_effect=AssertionError("must not initialize"))

    def dependency():
        return factory()

    app.dependency_overrides[get_deletion_service] = dependency
    with TestClient(app) as client:
        assert client.delete("/users/me").status_code == 401
    factory.assert_not_called()
