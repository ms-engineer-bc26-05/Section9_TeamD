"""Stripe Checkoutクライアントのテスト。Stripeへは接続せず、httpx.MockTransportで応答を模す。"""

import logging
from urllib.parse import parse_qs

import httpx
import pytest

from app.integrations.stripe.client import (
    StripeCheckoutClient,
    StripeConfigError,
    StripeExpiresAtRejected,
    StripeIdempotencyInProgress,
    StripeIdempotencyMismatch,
    StripeRequestFailed,
    StripeSessionNotFound,
    StripeUnavailable,
)

TEST_KEY = "sk_test_dummy_key_for_tests"
SESSION_ID = "cs_test_dummy_session"
SESSION_URL = "https://checkout.stripe.com/c/pay/cs_test_dummy_session"
USER_ID = "00000000-0000-0000-0000-000000000001"
PAYMENT_ID = "00000000-0000-0000-0000-0000000000a1"
IDEMPOTENCY_KEY = "00000000-0000-0000-0000-0000000000b1"
EXPIRES_AT = 1_791_700_000


def make_client(handler, secret_key: str = TEST_KEY) -> StripeCheckoutClient:
    return StripeCheckoutClient(secret_key=secret_key, transport=httpx.MockTransport(handler))


def session_body(**overrides) -> dict:
    body = {
        "id": SESSION_ID,
        "object": "checkout.session",
        "url": SESSION_URL,
        "status": "open",
        "payment_status": "unpaid",
        "amount_total": 300,
        "currency": "jpy",
        "client_reference_id": USER_ID,
        "metadata": {"payment_id": PAYMENT_ID},
    }
    body.update(overrides)
    return body


def error_response(
    status: int, error_type: str, code: str | None = None, param: str | None = None
) -> httpx.Response:
    error = {"type": error_type, "message": f"架空のエラー {SESSION_ID}"}
    if code:
        error["code"] = code
    if param:
        error["param"] = param
    return httpx.Response(status, json={"error": error})


async def create(client: StripeCheckoutClient):
    return await client.create_checkout_session(
        price_id="price_dummy",
        client_reference_id=USER_ID,
        metadata={"payment_id": PAYMENT_ID},
        success_url="http://localhost:3000/plan/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="http://localhost:3000/plan",
        expires_at=EXPIRES_AT,
        idempotency_key=IDEMPOTENCY_KEY,
    )


# --- Session作成 ---------------------------------------------------------------


async def test_create_sends_one_time_payment_request():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["method"] = request.method
        sent["url"] = str(request.url)
        sent["auth"] = request.headers["Authorization"]
        sent["idempotency_key"] = request.headers.get("Idempotency-Key")
        sent["form"] = parse_qs(request.content.decode())
        return httpx.Response(200, json=session_body())

    session = await create(make_client(handler))

    assert session.id == SESSION_ID
    assert session.url == SESSION_URL
    assert session.status == "open"
    assert sent["method"] == "POST"
    assert sent["url"] == "https://api.stripe.com/v1/checkout/sessions"
    assert sent["auth"] == f"Bearer {TEST_KEY}"
    assert sent["idempotency_key"] == IDEMPOTENCY_KEY
    form = sent["form"]
    assert form["mode"] == ["payment"]
    assert form["line_items[0][price]"] == ["price_dummy"]
    assert form["line_items[0][quantity]"] == ["1"]
    assert form["client_reference_id"] == [USER_ID]
    assert form["metadata[payment_id]"] == [PAYMENT_ID]
    assert form["success_url"] == [
        "http://localhost:3000/plan/success?session_id={CHECKOUT_SESSION_ID}"
    ]
    assert form["expires_at"] == [str(EXPIRES_AT)]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": {"type": "api_error", "message": "架空"}}),
        httpx.Response(503, json={"error": {"type": "api_error", "message": "架空"}}),
        error_response(429, "invalid_request_error", "rate_limit"),
    ],
)
async def test_create_server_error_is_unavailable(response):
    with pytest.raises(StripeUnavailable):
        await create(make_client(lambda request: response))


async def test_create_timeout_is_unavailable():
    # 作成されたか分からない失敗。呼び出し側が同じidempotency keyで再試行する
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("架空のタイムアウト")

    with pytest.raises(StripeUnavailable):
        await create(make_client(handler))


async def test_create_is_not_retried_by_sdk():
    # 再試行は呼び出し側で行うため、SDKは1回しか送らない
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("架空の接続失敗")

    with pytest.raises(StripeUnavailable):
        await create(make_client(handler))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        error_response(400, "invalid_request_error", "parameter_invalid"),
        error_response(401, "invalid_request_error"),
    ],
)
async def test_create_request_error_is_not_retryable(response):
    with pytest.raises(StripeRequestFailed):
        await create(make_client(lambda request: response))


async def test_create_expires_at_rejected():
    # 有効期限が条件（作成時から30分以上）を満たさない。入力の検査で断られ、Sessionは作成されない
    response = error_response(400, "invalid_request_error", "parameter_invalid", "expires_at")
    with pytest.raises(StripeExpiresAtRejected):
        await create(make_client(lambda request: response))


async def test_create_same_key_in_progress():
    # 同じidempotency keyの最初のリクエストを、Stripeがまだ処理している
    response = error_response(409, "invalid_request_error", "idempotency_key_in_use")
    with pytest.raises(StripeIdempotencyInProgress):
        await create(make_client(lambda request: response))


async def test_create_same_key_with_different_params():
    response = error_response(400, "idempotency_error")
    with pytest.raises(StripeIdempotencyMismatch):
        await create(make_client(lambda request: response))


# --- Price取得 -----------------------------------------------------------------


async def test_retrieve_price_returns_amount_and_currency():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["method"] = request.method
        sent["path"] = request.url.path
        return httpx.Response(
            200,
            json={
                "id": "price_dummy",
                "object": "price",
                "active": True,
                "type": "one_time",
                "unit_amount": 300,
                "currency": "jpy",
            },
        )

    price = await make_client(handler).retrieve_price("price_dummy")

    assert sent == {"method": "GET", "path": "/v1/prices/price_dummy"}
    assert (price.active, price.type, price.unit_amount, price.currency) == (
        True,
        "one_time",
        300,
        "jpy",
    )


async def test_retrieve_missing_price_is_not_retryable():
    response = error_response(404, "invalid_request_error", "resource_missing")
    # Priceが見つからないのは設定の誤り。Session用の例外（StripeSessionNotFound）にはしない
    with pytest.raises(StripeRequestFailed):
        await make_client(lambda request: response).retrieve_price("price_dummy")


# --- Session取得 ---------------------------------------------------------------


async def test_retrieve_returns_payment_fields():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["method"] = request.method
        sent["url"] = str(request.url)
        return httpx.Response(
            200, json=session_body(status="complete", payment_status="paid", url=None)
        )

    session = await make_client(handler).retrieve_checkout_session(SESSION_ID)

    assert sent["method"] == "GET"
    assert sent["url"] == f"https://api.stripe.com/v1/checkout/sessions/{SESSION_ID}"
    assert session.status == "complete"
    assert session.payment_status == "paid"
    assert session.url is None
    assert session.amount_total == 300
    assert session.currency == "jpy"
    assert session.client_reference_id == USER_ID
    assert session.metadata == {"payment_id": PAYMENT_ID}


async def test_retrieve_missing_session_is_not_found():
    response = error_response(404, "invalid_request_error", "resource_missing")
    with pytest.raises(StripeSessionNotFound):
        await make_client(lambda request: response).retrieve_checkout_session(SESSION_ID)


async def test_retrieve_timeout_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("架空のタイムアウト")

    with pytest.raises(StripeUnavailable):
        await make_client(handler).retrieve_checkout_session(SESSION_ID)


# --- テストモードの鍵の確認 -------------------------------------------------------


@pytest.mark.parametrize("secret_key", ["", "sk_live_dummy", "pk_test_dummy"])
async def test_non_test_key_is_rejected_before_request(secret_key):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=session_body())

    client = make_client(handler, secret_key=secret_key)
    with pytest.raises(StripeConfigError):
        await create(client)
    with pytest.raises(StripeConfigError):
        await client.retrieve_checkout_session(SESSION_ID)
    assert calls == []


async def test_restricted_test_key_is_allowed():
    client = make_client(lambda request: httpx.Response(200, json=session_body()), "rk_test_x")
    session = await client.retrieve_checkout_session(SESSION_ID)
    assert session.id == SESSION_ID


# --- 秘密情報をログ・例外・reprへ出さない --------------------------------------------


async def test_secrets_are_not_in_logs_or_errors(caplog):
    caplog.set_level(logging.DEBUG)
    response = error_response(400, "invalid_request_error", "parameter_invalid")

    with pytest.raises(StripeRequestFailed) as exc_info:
        await create(make_client(lambda request: response))

    for text in (caplog.text, str(exc_info.value), repr(exc_info.value)):
        assert TEST_KEY not in text
        assert SESSION_ID not in text
        assert USER_ID not in text
        assert PAYMENT_ID not in text


async def test_session_info_is_not_in_logs_on_success(caplog):
    # httpx はリクエストのURL（取得ではSession IDを含む）を INFO で出力するため、抑止を確認する
    caplog.set_level(logging.DEBUG)
    client = make_client(lambda request: httpx.Response(200, json=session_body()))

    await create(client)
    await client.retrieve_checkout_session(SESSION_ID)

    assert TEST_KEY not in caplog.text
    assert SESSION_ID not in caplog.text
    assert SESSION_URL not in caplog.text
    assert USER_ID not in caplog.text
    assert PAYMENT_ID not in caplog.text


async def test_session_repr_does_not_include_session_info():
    session = await make_client(
        lambda request: httpx.Response(200, json=session_body())
    ).retrieve_checkout_session(SESSION_ID)

    text = repr(session)
    assert SESSION_ID not in text
    assert SESSION_URL not in text
    assert USER_ID not in text
    assert PAYMENT_ID not in text
