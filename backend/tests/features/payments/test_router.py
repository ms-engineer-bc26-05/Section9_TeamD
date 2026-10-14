"""決済APIのテスト。

main.py への登録は結合Issue（#53）で行うため、決済Routerだけを載せたテスト用アプリを使う。
認証は dependency_overrides で固定UUIDのユーザーにし、DB・Stripeは fakes.py の偽物で模す。
テストデータはすべて架空。
"""

import logging
from dataclasses import replace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import INTERNAL_ERROR_CODE, register_exception_handlers
from app.core.exceptions import AccountDeletingError, DatabaseUnavailableError
from app.features.payments.router import (
    get_checkout_settings,
    get_current_user_id,
    get_payment_repository,
    router,
)
from app.features.payments.settings import CheckoutSettings
from app.integrations.stripe.client import (
    StripeIdempotencyMismatch,
    StripeUnavailable,
    get_stripe_client,
)
from tests.features.payments.fakes import FakeStripe, InMemoryPaymentRepository

BASE = "/api/v1/payments"
USER_A = UUID("00000000-0000-0000-0000-000000000001")
USER_B = UUID("00000000-0000-0000-0000-000000000002")

SETTINGS = CheckoutSettings(
    price_ids={"premium": "price_dummy"},
    success_url="http://localhost:3000/plan/success?session_id={CHECKOUT_SESSION_ID}",
    cancel_url="http://localhost:3000/plan",
)


@pytest.fixture
def repo() -> InMemoryPaymentRepository:
    return InMemoryPaymentRepository()


@pytest.fixture
def stripe() -> FakeStripe:
    return FakeStripe()


@pytest.fixture
def app(repo, stripe):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_payment_repository] = lambda: repo
    app.dependency_overrides[get_stripe_client] = lambda: stripe
    app.dependency_overrides[get_checkout_settings] = lambda: SETTINGS
    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def checkout(client, plan_code: str = "premium"):
    return client.post(f"{BASE}/checkout-session", json={"plan_code": plan_code})


def error_of(response) -> dict:
    return response.json()["error"]


# --- POST /payments/checkout-session ------------------------------------------------


def test_checkout_returns_url_and_session_id(client, stripe):
    response = checkout(client)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"checkout_url", "session_id"}
    assert body["session_id"] in stripe.sessions
    assert body["checkout_url"] == stripe.sessions[body["session_id"]].url


def test_checkout_twice_returns_same_session(client, stripe):
    first = checkout(client).json()
    second = checkout(client).json()

    assert first == second
    assert stripe.created_session_count == 1


def test_unknown_plan_is_422_plan_not_available(client, stripe):
    response = checkout(client, "gold")

    assert response.status_code == 422
    assert error_of(response)["code"] == "PLAN_NOT_AVAILABLE"
    assert stripe.created_session_count == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"plan_code": ""},
        {"plan_code": "premium", "amount": 1},
        {"plan_code": "premium", "price_id": "price_attacker"},
    ],
)
def test_invalid_body_is_validation_error(client, stripe, body):
    """金額・Price IDはクライアントから受け取らない"""
    response = client.post(f"{BASE}/checkout-session", json=body)

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"
    assert "price_attacker" not in response.text
    assert stripe.created_session_count == 0


def test_already_paid_is_409(client, repo):
    repo.paid_users.add(USER_A)

    response = checkout(client)

    assert response.status_code == 409
    assert error_of(response)["code"] == "ALREADY_PAID"


def test_unconfirmable_creating_is_409_checkout_in_progress(client, repo, stripe):
    stripe.create_errors.append(StripeUnavailable("架空"))
    assert checkout(client).status_code == 503
    stripe.create_errors.append(StripeIdempotencyMismatch("架空"))

    response = checkout(client)

    assert response.status_code == 409
    assert error_of(response)["code"] == "CHECKOUT_IN_PROGRESS"
    assert [row.status for row in repo.rows.values()] == ["creating"]


def test_paid_but_unconfirmed_is_409_with_session_id(client, stripe):
    session_id = checkout(client).json()["session_id"]
    stripe.pay(session_id)

    response = checkout(client)

    assert response.status_code == 409
    error = error_of(response)
    assert error["code"] == "PAYMENT_CONFIRMATION_REQUIRED"
    assert error["session_id"] == session_id


def test_deleting_user_is_403(client, repo):
    repo.user_statuses[USER_A] = "deleting"

    response = checkout(client)

    assert response.status_code == 403
    assert error_of(response)["code"] == "ACCOUNT_DELETING"
    assert repo.rows == {}


def test_deleted_user_is_401(client, repo):
    repo.user_statuses[USER_A] = None

    response = checkout(client)

    assert response.status_code == 401
    assert error_of(response)["code"] == "UNAUTHORIZED"
    # 共通のエラーハンドラの401と同じく、WWW-Authenticate ヘッダーを付ける
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_invalid_price_is_fixed_500(client, stripe):
    stripe.price = replace(stripe.price, type="recurring")

    response = checkout(client)

    assert response.status_code == 500
    assert error_of(response)["code"] == INTERNAL_ERROR_CODE
    assert "recurring" not in response.text


# --- POST /payments/confirm --------------------------------------------------------


def test_confirm_paid_then_plan_is_premium(client, stripe):
    session_id = checkout(client).json()["session_id"]
    stripe.pay(session_id)

    response = client.post(f"{BASE}/confirm", json={"session_id": session_id})
    again = client.post(f"{BASE}/confirm", json={"session_id": session_id})

    assert response.status_code == 200
    assert response.json() == {"status": "paid"}
    assert again.json() == {"status": "paid"}
    assert client.get(f"{BASE}/me").json() == {"plan_code": "premium"}


@pytest.mark.parametrize("send", [{"json": {}}, {}])
def test_confirm_without_session_id_checks_own_pending(client, stripe, send):
    checkout(client)

    response = client.post(f"{BASE}/confirm", **send)

    assert response.status_code == 200
    assert response.json() == {"status": "pending"}


def test_confirm_expired(client, stripe):
    session_id = checkout(client).json()["session_id"]
    stripe.set_session_status(session_id, "expired")

    response = client.post(f"{BASE}/confirm", json={"session_id": session_id})

    assert response.json() == {"status": "expired"}


def test_confirm_others_session_is_404(app, client, stripe):
    session_id = checkout(client).json()["session_id"]
    stripe.pay(session_id)
    app.dependency_overrides[get_current_user_id] = lambda: USER_B

    response = client.post(f"{BASE}/confirm", json={"session_id": session_id})

    assert response.status_code == 404
    assert error_of(response)["code"] == "PAYMENT_NOT_FOUND"
    assert session_id not in response.text


def test_confirm_stripe_unavailable_is_503(client, stripe):
    session_id = checkout(client).json()["session_id"]
    stripe.retrieve_errors.append(StripeUnavailable("架空"))

    response = client.post(f"{BASE}/confirm", json={"session_id": session_id})

    assert response.status_code == 503
    assert error_of(response)["code"] == "PAYMENT_UNAVAILABLE"


def test_confirm_rejects_extra_fields(client):
    response = client.post(f"{BASE}/confirm", json={"session_id": "cs_test_x", "status": "paid"})

    assert response.status_code == 422
    assert error_of(response)["code"] == "VALIDATION_ERROR"


# --- GET /payments/me ----------------------------------------------------------------


def test_plan_is_free_without_entitlement(client):
    assert client.get(f"{BASE}/me").json() == {"plan_code": "free"}


def test_plan_db_unavailable_is_503_not_free(app, client, repo):
    """権限を確認できない場合は、無料として返さない（#59）"""

    def broken():
        raise DatabaseUnavailableError("架空")

    app.dependency_overrides[get_payment_repository] = broken

    response = client.get(f"{BASE}/me")

    assert response.status_code == 503
    assert error_of(response)["code"] == "DB_UNAVAILABLE"


# --- 共通 --------------------------------------------------------------------------


def test_common_auth_errors_are_not_converted(app, client):
    def deleting():
        raise AccountDeletingError("架空")

    app.dependency_overrides[get_current_user_id] = deleting

    response = checkout(client)

    assert response.status_code == 403
    assert error_of(response)["code"] == "ACCOUNT_DELETING"


def test_session_info_is_not_logged(client, stripe, caplog):
    caplog.set_level(logging.DEBUG)
    session_id = checkout(client).json()["session_id"]
    stripe.pay(session_id)
    checkout(client)  # 409 PAYMENT_CONFIRMATION_REQUIRED
    client.post(f"{BASE}/confirm", json={"session_id": session_id})

    assert session_id not in caplog.text
    assert "checkout.stripe.com" not in caplog.text
