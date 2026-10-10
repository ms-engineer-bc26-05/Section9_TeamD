"""Opt-in Firebase probe. The database is always mocked; never run by pytest."""

import argparse
import asyncio
import getpass
import logging
import os
import signal
import sys
import time
import warnings
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from fastapi import FastAPI
from firebase_admin import exceptions as firebase_exceptions
from httpx import ASGITransport, AsyncClient
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.response import HTTPResponse
from urllib3.util.retry import Retry

from app.core.errors import register_exception_handlers
from app.features.auth import service as auth_service
from app.features.users import router as users_router
from app.integrations.firebase import client as firebase_client


MAX_HTTP_ATTEMPTS = 10
MAX_PROBE_SECONDS = 60


class ProbeLimitReached(BaseException):
    """Bypass SDK/application Exception handlers and stop without secret details."""


@contextmanager
def live_limits(max_attempts=MAX_HTTP_ATTEMPTS, seconds=MAX_PROBE_SECONDS):
    # This private urllib3 hook counts each retry, not just Session.request calls.
    if HTTPSConnectionPool._make_request is not HTTPConnectionPool._make_request:
        raise ProbeLimitReached()
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise ProbeLimitReached()
    original = HTTPConnectionPool._make_request
    previous_handler = signal.getsignal(signal.SIGALRM)
    state = {"attempts": 0}

    def stop(signum, frame):
        raise ProbeLimitReached()

    def bounded_request(pool, *args, **kwargs):
        if state["attempts"] >= max_attempts:
            raise ProbeLimitReached()
        state["attempts"] += 1
        return original(pool, *args, **kwargs)

    signal.signal(signal.SIGALRM, stop)
    try:
        with patch.object(HTTPConnectionPool, "_make_request", bounded_request):
            signal.setitimer(signal.ITIMER_REAL, seconds)
            yield state
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def limits_self_test():
    for pool_type in (HTTPConnectionPool, HTTPSConnectionPool):
        transport = Mock(return_value=HTTPResponse(status=200))
        with patch.object(HTTPConnectionPool, "_make_request", transport):
            with live_limits(max_attempts=2) as state:
                pool = pool_type("probe.invalid")
                for _ in range(2):
                    pool._make_request(None, "GET", "/")
                try:
                    pool._make_request(None, "GET", "/")
                except ProbeLimitReached:
                    pass
                else:
                    return False
                if transport.call_count != 2 or state["attempts"] != 2:
                    return False
            if HTTPConnectionPool._make_request is not transport:
                return False

    # Exercise urllib3's real retry loop with a fake transport and no sockets.
    transport = Mock(side_effect=lambda *a, **k: HTTPResponse(status=503, body=b""))
    with patch.object(HTTPConnectionPool, "_make_request", transport):
        try:
            with live_limits(max_attempts=2):
                with HTTPSConnectionPool("probe.invalid") as pool:
                    pool.urlopen("GET", "/", retries=Retry(total=4, status_forcelist=[503]))
        except ProbeLimitReached:
            if transport.call_count != 2:
                return False
        else:
            return False

    previous_handler = signal.getsignal(signal.SIGALRM)
    try:
        with live_limits(seconds=0.01):
            time.sleep(0.1)
    except ProbeLimitReached:
        return (
            signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
            and signal.getsignal(signal.SIGALRM) == previous_handler
        )
    return False


class CapturedLogs(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


async def probe(case, token):
    session = AsyncMock()
    session.begin = Mock(return_value=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    factory = Mock(return_value=context)
    user = SimpleNamespace(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        status="active",
        has_seen_notice=False,
    )
    lookup = AsyncMock(return_value=(user, True))
    outcome = {
        "permission_denied": False,
        "user_disabled": False,
        "uid": None,
    }
    original_verify = firebase_client.auth.verify_id_token

    def observe_verify(*args, **kwargs):
        try:
            decoded = original_verify(*args, **kwargs)
        except firebase_exceptions.PermissionDeniedError:
            outcome["permission_denied"] = True
            raise
        except firebase_client.auth.UserDisabledError:
            outcome["user_disabled"] = True
            raise
        if isinstance(decoded, dict):
            outcome["uid"] = decoded.get("uid")
        return decoded

    # Use the real route, auth service and error handlers, but no DB access.
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(users_router.router, prefix="/api/v1")
    logs = CapturedLogs()
    root = logging.getLogger()
    old_handlers, old_level = root.handlers[:], root.level
    root.handlers = [logs]
    root.setLevel(logging.INFO)
    try:
        with ExitStack() as stack:
            get_factory = stack.enter_context(
                patch.object(auth_service, "get_session_factory", return_value=factory)
            )
            stack.enter_context(patch.object(auth_service, "get_or_create_user", lookup))
            verify = stack.enter_context(
                patch.object(firebase_client.auth, "verify_id_token", side_effect=observe_verify)
            )
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://probe.invalid",
            ) as client:
                response = await client.post(
                    "/api/v1/users/me",
                    headers={"Authorization": "Bearer " + token},
                )

        if verify.call_count != 1 or verify.call_args.kwargs.get("check_revoked") is not True:
            return False
        if case == "allowed":
            valid = (
                response.status_code == 201
                and response.json() == {
                    "user_id": str(user.id), "has_seen_notice": False,
                }
                and not outcome["permission_denied"]
                and get_factory.call_count == 1
                and factory.call_count == 1
                and lookup.await_count == 1
                and lookup.call_args.args[1] == outcome["uid"]
                and session.begin.return_value.__aexit__.await_count == 1
                and session.begin.return_value.__aexit__.call_args.args[0] is None
                and context.__aexit__.await_count == 1
            )
        elif case == "denied":
            valid = (
                outcome["permission_denied"]
                and response.status_code == 503
                and response.json() == {
                    "error": {
                        "code": "AUTH_UNAVAILABLE",
                        "message": "認証サービスを利用できません。時間をおいて再度お試しください。",
                    }
                }
                and "www-authenticate" not in response.headers
                and factory.call_count == 0
                and get_factory.call_count == 0
                and lookup.call_count == 0
            )

        elif case == "disabled":
            valid = (
                outcome["user_disabled"]
                and response.status_code == 401
                and response.json() == {
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "ログインしてください。",
                    }
                }
                and response.headers.get("www-authenticate") == "Bearer"
                and factory.call_count == 0
                and get_factory.call_count == 0
                and lookup.call_count == 0
            )
        else:
            return False
        allowed_messages = {
            'HTTP Request: POST http://probe.invalid/api/v1/users/me "HTTP/1.1 201 Created"',
            'HTTP Request: POST http://probe.invalid/api/v1/users/me "HTTP/1.1 503 Service Unavailable"',
            "AUTH_UNAVAILABLE AuthServiceUnavailableError",
            'HTTP Request: POST http://probe.invalid/api/v1/users/me "HTTP/1.1 401 Unauthorized"',
        }
        log_safe = all(
            record.getMessage() in allowed_messages
            and not record.exc_info and not record.exc_text and not record.stack_info
            for record in logs.records
        )
        secret_values = (token, outcome["uid"], os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
        body_safe = all(not value or value not in response.text for value in secret_values)
        return valid and log_safe and body_safe
    finally:
        logs.records.clear()
        root.handlers, root.level = old_handlers, old_level


async def self_test():
    if not limits_self_test():
        return False
    scenarios = [
        ("disabled", firebase_client.auth.UserDisabledError("DUMMY_PRIVATE_ERROR"), True),
        ("disabled", firebase_client.auth.InvalidIdTokenError("DUMMY_PRIVATE_ERROR"), False),
        ("disabled", firebase_exceptions.PermissionDeniedError("DUMMY_PRIVATE_ERROR"), False),
        ("disabled", firebase_exceptions.UnavailableError("DUMMY_PRIVATE_ERROR"), False),
        ("disabled", {"uid": "dummy-firebase-uid"}, False),
        ("allowed", {"uid": "dummy-firebase-uid"}, True),
        ("denied", firebase_exceptions.PermissionDeniedError("DUMMY_PRIVATE_ERROR"), True),
        ("denied", firebase_exceptions.UnavailableError("DUMMY_PRIVATE_ERROR"), False),
        ("denied", firebase_client.auth.InvalidIdTokenError("DUMMY_PRIVATE_ERROR"), False),
        ("allowed", {"uid": ""}, False),
        ("denied", {"uid": "dummy-firebase-uid"}, False),
    ]
    for case, result, expected in scenarios:
        sdk = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
        with patch.object(firebase_client, "get_firebase_app", return_value=Mock()), patch.object(
            firebase_client.auth, "verify_id_token", sdk
        ):
            if await probe(case, "dummy-token") is not expected:
                return False
    def unsafe_sdk(*args, **kwargs):
        logging.getLogger("probe.self_test").warning("DUMMY_PRIVATE_ERROR")
        return {"uid": "dummy-firebase-uid"}

    with patch.object(firebase_client, "get_firebase_app", return_value=Mock()), patch.object(
        firebase_client.auth, "verify_id_token", side_effect=unsafe_sdk
    ):
        if await probe("allowed", "dummy-token"):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--case", choices=("allowed", "denied", "disabled"))
    parser.add_argument("--approved", action="store_true", help="Confirm the documented live plan is approved")
    args = parser.parse_args()
    if args.self_test:
        success = asyncio.run(self_test())
    else:
        if not args.approved or not sys.stdin.isatty():
            print("STOP: live approval and an interactive terminal are required.")
            return 2
        if (
            os.environ.get("FIREBASE_PROJECT_ID") != "porori-auth-spike"
            or not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or os.environ.get("FIREBASE_AUTH_EMULATOR_HOST")
        ):
            print("STOP: check the approved project and credential configuration.")
            return 2
        # Fail closed instead of falling back to an echoed password prompt.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("Test user ID token (hidden): ").strip()
        if not token or token == "dummy-token":
            print("STOP: a valid test user ID token is required.")
            return 2
        with live_limits() as budget:
            success = asyncio.run(probe(args.case, token))
        print(f"HTTP attempts: {budget['attempts']}/{MAX_HTTP_ATTEMPTS}")
    print("PASS" if success else "FAIL: stop and review the plan; details are suppressed.")
    return 0 if success else 1


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        print("STOP: cancelled.")
        code = 2
    except ProbeLimitReached:
        print("STOP: probe limit reached or guard unavailable. Do not retry without review.")
        code = 2
    except Exception:
        print("FAIL: unexpected error; details are suppressed. Do not retry without review.")
        code = 1
    sys.exit(code)
