"""Opt-in Firebase probe. The database is always mocked; never run by pytest."""

import argparse
import asyncio
import getpass
import io
import logging
import os
import signal
import sys
import time
import warnings
from contextlib import ExitStack, contextmanager, redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from fastapi import FastAPI
from cachecontrol.adapter import CacheControlAdapter
from firebase_admin import exceptions as firebase_exceptions
from google.auth import exceptions as google_auth_exceptions
from httpx import ASGITransport, AsyncClient
import requests
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.response import HTTPResponse
from urllib3.util.retry import Retry

from app.core.errors import register_exception_handlers
from app.features.auth import service as auth_service
from app.features.users import router as users_router
from app.integrations.firebase import client as firebase_client


MAX_HTTP_ATTEMPTS = 10
MAX_PROBE_SECONDS = 60
TEST_USER_EMAIL = "issue47-auth-check@example.com"


def certificate_cache_preflight():
    """Exercise the SDK's response cache with synthetic data and no transport."""
    request = requests.Request("GET", "https://probe.invalid/certificates").prepare()
    response = HTTPResponse(body=io.BytesIO(b"{}"), status=200, preload_content=False)
    adapter = CacheControlAdapter()
    try:
        with adapter.build_response(request, response) as result:
            return result.content == b"{}"
    except Exception:
        return False
    finally:
        response.close()
        adapter.close()


class SignInFailure(ValueError):
    """Carry only a locally defined diagnostic category."""


def hidden_input(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def sign_in(api_key, password):
    """Sign in once; never expose the response, password, or refresh token."""
    previous_disable = logging.root.manager.disable
    logging.disable(sys.maxsize)
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(
                "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
                params={"key": api_key},
                json={"email": TEST_USER_EMAIL, "password": password, "returnSecureToken": True},
                timeout=(10, 15),
                allow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise SignInFailure("SIGN_IN_HTTP_REJECTED")
                data = response.json()
                token = data.get("idToken")
                lifetime = int(data.get("expiresIn", 0))
                if not isinstance(token, str) or not token.strip() or lifetime <= 60:
                    raise SignInFailure("SIGN_IN_RESPONSE_INVALID")
                return token, time.monotonic() + min(lifetime, 3600) - 60
    except SignInFailure:
        raise
    except requests.exceptions.RequestException:
        raise SignInFailure("SIGN_IN_TRANSPORT_FAILED") from None
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise SignInFailure("SIGN_IN_RESPONSE_INVALID") from None
    finally:
        logging.disable(previous_disable)


def guided_probe(*, allowed_only=False):
    cases = ("allowed",) if allowed_only else ("denied", "allowed", "disabled")
    print(
        "Dedicated test user must be enabled. Grant ONLY firebaseauth.users.get before starting."
        if allowed_only else "Dedicated test user only. Start with NO service-account roles."
    )
    if input(f"Type READY to start {cases[0]} verification: ") != "READY":
        return False
    api_key = hidden_input("Approved project's Web API key (hidden): ").strip()
    password = hidden_input("Dedicated test user's password (hidden): ")
    if not api_key or not password:
        return False
    token = None
    try:
        for index, case in enumerate(cases):
            if index and case == "allowed":
                print("Pause: grant ONLY firebaseauth.users.get and wait for IAM propagation.")
            elif case == "disabled":
                print("Pause: disable ONLY the dedicated test user in the console; keep its role.")
            if index:
                if input("Type READY after the manual step (anything else stops): ") != "READY":
                    return False
                if time.monotonic() >= deadline:
                    print("STOP: token lifetime exceeded. Do not restart without reviewing the run count.")
                    return False
            budget = None
            stage = "GUARD"
            try:
                with live_limits() as budget:
                    if index == 0:
                        stage = "SIGN_IN"
                        token, deadline = sign_in(api_key, password)
                        api_key = password = None
                    stage = "TOKEN_PROBE"
                    success = asyncio.run(probe(case, token))
            except (Exception, ProbeLimitReached, KeyboardInterrupt) as error:
                category = "UNEXPECTED_ERROR"
                if isinstance(error, SignInFailure):
                    candidate = error.args[0] if error.args else None
                    if candidate in ("SIGN_IN_HTTP_REJECTED", "SIGN_IN_TRANSPORT_FAILED", "SIGN_IN_RESPONSE_INVALID"):
                        category = candidate
                elif isinstance(error, ProbeLimitReached):
                    category = "LIMIT_OR_GUARD_STOP"
                elif isinstance(error, KeyboardInterrupt):
                    category = "CANCELLED"
                print("DIAGNOSTIC STAGE: " + stage)
                print("DIAGNOSTIC FAILURE: " + category)
                attempts = str(budget["attempts"]) if budget is not None else "UNKNOWN"
                print("HTTP attempts: " + attempts + "/" + str(MAX_HTTP_ATTEMPTS))
                return False
            print(f"{case}: {'PASS' if success else 'FAIL'}; HTTP attempts: {budget['attempts']}/{MAX_HTTP_ATTEMPTS}")
            if not success:
                return False
        return True
    finally:
        token = api_key = password = None


def allowed_only_self_test():
    module = sys.modules[__name__]
    for confirmation, failure_stage, result in (
        ("READY", None, True),
        ("READY", None, False),
        ("STOP", None, True),
        ("READY", "SIGN_IN", SignInFailure("SIGN_IN_HTTP_REJECTED")),
        ("READY", "SIGN_IN", RuntimeError("DUMMY_SECRET")),
        ("READY", "TOKEN_PROBE", RuntimeError("DUMMY_SECRET")),
        ("READY", "TOKEN_PROBE", ProbeLimitReached()),
        ("READY", "TOKEN_PROBE", KeyboardInterrupt()),
    ):
        output = io.StringIO()
        stages = []

        @contextmanager
        def fake_limits():
            stages.append("GUARD_START")
            try:
                yield {"attempts": 2}
            finally:
                stages.append("GUARD_END")

        def login_once(*args):
            stages.append("SIGN_IN")
            if failure_stage == "SIGN_IN":
                raise result
            return "DUMMY_TOKEN", time.monotonic() + 300

        async def probe_once(case, token):
            stages.append("TOKEN_PROBE")
            if failure_stage == "TOKEN_PROBE":
                raise result
            return result

        with patch("builtins.input", return_value=confirmation) as confirm, patch.object(
            module, "hidden_input", side_effect=["DUMMY_KEY", "DUMMY_PASSWORD"]
        ) as hidden, patch.object(module, "live_limits", fake_limits), patch.object(
            module, "sign_in", side_effect=login_once
        ) as login, patch.object(module, "probe", AsyncMock(side_effect=probe_once)) as check, redirect_stdout(output):
            actual = guided_probe(allowed_only=True)
        if actual is not (confirmation == "READY" and failure_stage is None and result is True):
            return False
        if confirm.call_count != 1:
            return False
        if confirmation != "READY":
            if hidden.called or login.called or check.called or stages:
                return False
            continue
        expected_stages = ["GUARD_START", "SIGN_IN"]
        if failure_stage != "SIGN_IN":
            expected_stages.append("TOKEN_PROBE")
            if check.await_args_list != [(("allowed", "DUMMY_TOKEN"), {})]:
                return False
        elif check.called:
            return False
        if stages != expected_stages + ["GUARD_END"] or login.call_count != 1:
            return False
        rendered = output.getvalue()
        if any(secret in rendered for secret in ("DUMMY_KEY", "DUMMY_PASSWORD", "DUMMY_TOKEN", "DUMMY_SECRET")):
            return False
        if "denied:" in rendered or "disabled:" in rendered or "2/10" not in rendered:
            return False
        if failure_stage and "DIAGNOSTIC STAGE: " + failure_stage not in rendered:
            return False
    return True


def guided_self_test():
    module = sys.modules[__name__]
    for status, data, expected in (
        (200, {"idToken": "DUMMY_TOKEN", "expiresIn": "3600"}, True),
        (400, {"error": "DUMMY_SECRET"}, False),
        (302, {}, False),
        (200, {"idToken": "", "expiresIn": "3600"}, False),
        (200, None, False),
        (200, {"idToken": "DUMMY_TOKEN", "expiresIn": "invalid"}, False),
        (None, {}, False),
    ):
        response = Mock(status_code=status)
        response.json.return_value = data
        response_context = Mock()
        response_context.__enter__ = Mock(return_value=response)
        response_context.__exit__ = Mock(return_value=False)
        session_context = Mock()
        session = Mock()
        session.post.return_value = response_context
        if status is None:
            session.post.side_effect = requests.exceptions.ConnectionError("DUMMY_SECRET")
        session_context.__enter__ = Mock(return_value=session)
        session_context.__exit__ = Mock(return_value=False)
        previous_disable = logging.root.manager.disable
        with patch.object(requests, "Session", return_value=session_context):
            try:
                token, deadline = sign_in("DUMMY_KEY", "DUMMY_PASSWORD")
                if not expected or token != "DUMMY_TOKEN" or deadline <= time.monotonic():
                    return False
            except SignInFailure as error:
                if expected:
                    return False
                category = (
                    "SIGN_IN_TRANSPORT_FAILED" if status is None else
                    "SIGN_IN_HTTP_REJECTED" if status != 200 else "SIGN_IN_RESPONSE_INVALID"
                )
                if error.args != (category,):
                    return False
        if logging.root.manager.disable != previous_disable or session.trust_env is not False:
            return False
        if session.post.call_count != 1 or session.post.call_args.kwargs["allow_redirects"] is not False:
            return False

    for results, confirmations, expected in (
        ([True, True, True], ["READY"] * 3, True),
        ([False], ["READY"], False),
        ([True, False], ["READY"] * 2, False),
        ([True], ["READY", "STOP"], False),
    ):
        output = io.StringIO()
        with patch("builtins.input", side_effect=confirmations), patch.object(
            module, "hidden_input", side_effect=["DUMMY_KEY", "DUMMY_PASSWORD"]
        ), patch.object(
            module, "sign_in", return_value=("DUMMY_TOKEN", time.monotonic() + 300)
        ) as login, patch.object(
            module, "probe", AsyncMock(side_effect=results)
        ) as check, redirect_stdout(output):
            if guided_probe() is not expected:
                return False
        if login.call_count != 1 or check.await_count != len(results):
            return False
        if [call.args[0] for call in check.await_args_list] != ["denied", "allowed", "disabled"][:len(results)]:
            return False
        if any(call.args[1] != "DUMMY_TOKEN" for call in check.await_args_list):
            return False
        if any(secret in output.getvalue() for secret in ("DUMMY_KEY", "DUMMY_PASSWORD", "DUMMY_TOKEN")):
            return False
    for failed_stage, error, category in (
        ("SIGN_IN", SignInFailure("SIGN_IN_HTTP_REJECTED"), "SIGN_IN_HTTP_REJECTED"),
        ("SIGN_IN", SignInFailure("SIGN_IN_TRANSPORT_FAILED"), "SIGN_IN_TRANSPORT_FAILED"),
        ("SIGN_IN", SignInFailure("SIGN_IN_RESPONSE_INVALID"), "SIGN_IN_RESPONSE_INVALID"),
        ("SIGN_IN", SignInFailure("DUMMY_SECRET"), "UNEXPECTED_ERROR"),
        ("SIGN_IN", RuntimeError("DUMMY_SECRET"), "UNEXPECTED_ERROR"),
        ("TOKEN_PROBE", RuntimeError("DUMMY_SECRET"), "UNEXPECTED_ERROR"),
        ("TOKEN_PROBE", ProbeLimitReached(), "LIMIT_OR_GUARD_STOP"),
        ("TOKEN_PROBE", KeyboardInterrupt(), "CANCELLED"),
    ):
        output = io.StringIO()

        @contextmanager
        def fake_limits():
            yield {"attempts": 2}

        with patch("builtins.input", return_value="READY"), patch.object(
            module, "hidden_input", side_effect=["DUMMY_KEY", "DUMMY_PASSWORD"]
        ), patch.object(module, "live_limits", fake_limits), patch.object(
            module, "sign_in", side_effect=error if failed_stage == "SIGN_IN" else None,
            return_value=("DUMMY_TOKEN", time.monotonic() + 300),
        ), patch.object(module, "probe", AsyncMock(side_effect=error)) as check, redirect_stdout(output):
            if guided_probe():
                return False
        rendered = output.getvalue()
        if any(secret in rendered for secret in ("DUMMY_SECRET", "DUMMY_KEY", "DUMMY_PASSWORD", "DUMMY_TOKEN")):
            return False
        if any(expected not in rendered for expected in (
            "DIAGNOSTIC STAGE: " + failed_stage, "DIAGNOSTIC FAILURE: " + category,
            "HTTP attempts: 2/10",
        )):
            return False
        if check.await_count != (0 if failed_stage == "SIGN_IN" else 1):
            return False
    return True


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
        "sdk": "NOT_REACHED",
        "permission_denied": False,
        "user_disabled": False,
        "uid": None,
    }
    original_verify = firebase_client.auth.verify_id_token

    def observe_verify(*args, **kwargs):
        try:
            decoded = original_verify(*args, **kwargs)
        except firebase_exceptions.PermissionDeniedError:
            outcome["sdk"] = "PERMISSION_DENIED"
            outcome["permission_denied"] = True
            raise
        except firebase_client.auth.UserDisabledError:
            outcome["sdk"] = "USER_DISABLED"
            outcome["user_disabled"] = True
            raise
        except Exception as error:
            # Only fixed categories are printable; never interpolate exception data.
            outcome["sdk"] = "OTHER_ERROR"
            for error_type, label in (
                (firebase_client.auth.CertificateFetchError, "CERTIFICATE_FETCH_ERROR"),
                (firebase_client.auth.ExpiredIdTokenError, "TOKEN_EXPIRED"),
                (firebase_client.auth.RevokedIdTokenError, "TOKEN_REVOKED"),
                (firebase_client.auth.InvalidIdTokenError, "TOKEN_INVALID"),
                (firebase_client.auth.UserNotFoundError, "USER_NOT_FOUND"),
                (google_auth_exceptions.RefreshError, "GOOGLE_AUTH_REFRESH_FAILED"),
                (google_auth_exceptions.DefaultCredentialsError, "GOOGLE_AUTH_CREDENTIALS_ERROR"),
                (google_auth_exceptions.TransportError, "GOOGLE_AUTH_TRANSPORT_FAILED"),
                (google_auth_exceptions.GoogleAuthError, "GOOGLE_AUTH_OTHER_ERROR"),
                (requests.exceptions.RequestException, "HTTP_TRANSPORT_FAILED"),
                (ValueError, "INVALID_ARGUMENT"),
            ):
                if isinstance(error, error_type):
                    outcome["sdk"] = label
                    break
            raise
        outcome["sdk"] = "VERIFIED"
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
            print("DIAGNOSTIC: VERIFY_CALL_CONTRACT_FAILED")
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
        success = valid and log_safe and body_safe
        if not success:
            print("DIAGNOSTIC SDK: " + outcome["sdk"])
            status = str(response.status_code) if response.status_code in (201, 401, 403, 500, 503) else "OTHER"
            print("DIAGNOSTIC HTTP: " + status)
            db_called = bool(get_factory.call_count or factory.call_count or lookup.call_count)
            print("DIAGNOSTIC DB: " + ("CALLED" if db_called else "NOT_CALLED"))
            for label, passed in (("CASE", valid), ("LOG", log_safe), ("BODY", body_safe)):
                print("DIAGNOSTIC " + label + ": " + ("PASS" if passed else "FAIL"))
        return success
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
            output = io.StringIO()
            with redirect_stdout(output):
                actual = await probe(case, "dummy-token")
            if actual is not expected:
                return False
            if any(secret in output.getvalue() for secret in ("dummy-token", "dummy-firebase-uid", "DUMMY_PRIVATE_ERROR")):
                return False
            if expected and output.getvalue():
                return False
            if not expected and "DIAGNOSTIC" not in output.getvalue():
                return False
    for error_type, category in (
        (google_auth_exceptions.RefreshError, "GOOGLE_AUTH_REFRESH_FAILED"),
        (google_auth_exceptions.DefaultCredentialsError, "GOOGLE_AUTH_CREDENTIALS_ERROR"),
        (google_auth_exceptions.TransportError, "GOOGLE_AUTH_TRANSPORT_FAILED"),
        (google_auth_exceptions.GoogleAuthError, "GOOGLE_AUTH_OTHER_ERROR"),
        (requests.exceptions.ConnectionError, "HTTP_TRANSPORT_FAILED"),
        (RuntimeError, "OTHER_ERROR"),
    ):
        output = io.StringIO()
        with patch.object(firebase_client, "get_firebase_app", return_value=Mock()), patch.object(
            firebase_client.auth, "verify_id_token", side_effect=error_type("DUMMY_PRIVATE_ERROR")
        ), redirect_stdout(output):
            if await probe("denied", "dummy-token"):
                return False
        rendered = output.getvalue()
        if any(secret in rendered for secret in ("DUMMY_PRIVATE_ERROR", "dummy-token", "Traceback")):
            return False
        if any(line not in rendered.splitlines() for line in (
            "DIAGNOSTIC SDK: " + category,
            "DIAGNOSTIC HTTP: 503",
            "DIAGNOSTIC DB: NOT_CALLED",
            "DIAGNOSTIC CASE: FAIL",
            "DIAGNOSTIC LOG: PASS",
            "DIAGNOSTIC BODY: PASS",
        )):
            return False

    def unsafe_sdk(*args, **kwargs):
        logging.getLogger("probe.self_test").warning("DUMMY_PRIVATE_ERROR")
        return {"uid": "dummy-firebase-uid"}

    with patch.object(firebase_client, "get_firebase_app", return_value=Mock()), patch.object(
        firebase_client.auth, "verify_id_token", side_effect=unsafe_sdk
    ):
        output = io.StringIO()
        with redirect_stdout(output):
            actual = await probe("allowed", "dummy-token")
        if actual or "DIAGNOSTIC LOG: FAIL" not in output.getvalue() or "DUMMY_PRIVATE_ERROR" in output.getvalue():
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--guided", action="store_true")
    modes.add_argument("--allowed-only", action="store_true", help="Sign in privately, run allowed once, then exit")
    modes.add_argument("--case", choices=("allowed", "denied", "disabled"))
    parser.add_argument("--approved", action="store_true", help="Confirm the documented live plan is approved")
    args = parser.parse_args()
    if not certificate_cache_preflight():
        print("STOP: certificate cache preflight failed; check writable temporary storage. No live request sent.")
        return 2
    if args.self_test:
        success = allowed_only_self_test() and guided_self_test() and asyncio.run(self_test())
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
        if args.guided or args.allowed_only:
            success = guided_probe(allowed_only=args.allowed_only)
        else:
            token = hidden_input("Test user ID token (hidden): ").strip()
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
