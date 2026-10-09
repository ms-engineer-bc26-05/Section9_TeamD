"""Checkout Session作成（CheckoutService）のテスト。DB・Stripeは fakes.py の偽物を使う。

テスト設計書5.8のPY-02〜PY-05・PY-19〜PY-22と、Q-34の案（#59で相談中）に対応する。
"""

import asyncio
import logging
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.features.payments.exceptions import (
    AlreadyPaid,
    CheckoutInProgress,
    PaymentConfirmationRequired,
    PlanNotAvailable,
    PriceConfigError,
)
from app.features.payments.repository import UserNotActive, UserNotFound
from app.features.payments.service import CheckoutService
from app.features.payments.settings import CheckoutSettings
from app.integrations.stripe.client import StripeUnavailable
from tests.features.payments.fakes import (
    PREMIUM_PLAN,
    FakeStripe,
    InMemoryPaymentRepository,
)

USER_A = UUID("00000000-0000-0000-0000-000000000001")

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
def service(repo, stripe) -> CheckoutService:
    return CheckoutService(repo, stripe, SETTINGS)


def rows_of(repo: InMemoryPaymentRepository, user_id: UUID = USER_A):
    return sorted(
        (row for row in repo.rows.values() if row.user_id == user_id),
        key=lambda row: row.created_at,
    )


async def start_pending(service, stripe) -> str:
    """ユーザーAの pending の行を作り、そのSession IDを返す"""
    started = await service.create_checkout(USER_A, "premium")
    return started.session_id


# --- 新しく作成する（PY-02・PY-22） ----------------------------------------------


async def test_create_new_session(service, repo, stripe):
    started = await service.create_checkout(USER_A, "premium")

    session = stripe.sessions[started.session_id]
    assert started.checkout_url == session.url
    [row] = rows_of(repo)
    assert row.status == "pending"
    assert row.stripe_checkout_session_id == started.session_id
    assert row.plan_id == PREMIUM_PLAN.id
    # 金額・通貨はStripe Priceの値
    assert (row.amount_minor, row.currency) == (300, "jpy")


async def test_create_uses_server_issued_values(service, repo, stripe):
    await service.create_checkout(USER_A, "premium")

    [row] = rows_of(repo)
    [call] = stripe.create_calls
    assert call == {
        "idempotency_key": str(row.idempotency_key),
        "price_id": "price_dummy",
        "client_reference_id": str(USER_A),
        "metadata": {"payment_id": str(row.id)},
        "success_url": SETTINGS.success_url,
        "cancel_url": SETTINGS.cancel_url,
    }


# --- 作成しない（PY-03・PY-04） -------------------------------------------------


async def test_paid_user_cannot_create(service, repo, stripe):
    repo.paid_users.add(USER_A)

    with pytest.raises(AlreadyPaid):
        await service.create_checkout(USER_A, "premium")
    assert stripe.create_calls == []
    assert rows_of(repo) == []


@pytest.mark.parametrize("plan_code", ["unknown", "free", ""])
async def test_plan_without_price_cannot_create(service, repo, stripe, plan_code):
    with pytest.raises(PlanNotAvailable):
        await service.create_checkout(USER_A, plan_code)
    assert stripe.create_calls == []
    assert rows_of(repo) == []


async def test_inactive_plan_cannot_create(service, repo, stripe):
    repo.plans["premium"] = replace(PREMIUM_PLAN, is_active=False)

    with pytest.raises(PlanNotAvailable):
        await service.create_checkout(USER_A, "premium")
    assert stripe.create_calls == []
    assert rows_of(repo) == []


@pytest.mark.parametrize(
    "price_changes",
    [
        {"active": False},
        {"type": "recurring"},
        {"unit_amount": None},
        {"unit_amount": -1},
        {"currency": None},
    ],
)
async def test_invalid_price_cannot_create(service, repo, stripe, price_changes):
    stripe.price = replace(stripe.price, **price_changes)

    with pytest.raises(PriceConfigError):
        await service.create_checkout(USER_A, "premium")
    assert stripe.create_calls == []
    assert rows_of(repo) == []


@pytest.mark.parametrize(("status", "error"), [(None, UserNotFound), ("deleting", UserNotActive)])
async def test_inactive_user_cannot_create(service, repo, stripe, status, error):
    repo.user_statuses[USER_A] = status

    with pytest.raises(error):
        await service.create_checkout(USER_A, "premium")
    assert stripe.create_calls == []
    assert rows_of(repo) == []


# --- pending の行がある（PY-19・PY-21） -----------------------------------------


async def test_open_session_is_reused(service, repo, stripe):
    session_id = await start_pending(service, stripe)

    started = await service.create_checkout(USER_A, "premium")

    assert started.session_id == session_id
    assert started.checkout_url == stripe.sessions[session_id].url
    assert len(stripe.create_calls) == 1
    assert len(rows_of(repo)) == 1


async def test_expired_session_is_replaced(service, repo, stripe):
    old_session_id = await start_pending(service, stripe)
    stripe.set_session_status(old_session_id, "expired")

    started = await service.create_checkout(USER_A, "premium")

    assert started.session_id != old_session_id
    old_row, new_row = rows_of(repo)
    assert old_row.status == "expired"
    assert new_row.status == "pending"
    assert new_row.stripe_checkout_session_id == started.session_id
    # 新しい行は新しい idempotency key を使う
    assert old_row.idempotency_key != new_row.idempotency_key


async def test_completed_session_requires_confirmation(service, repo, stripe):
    session_id = await start_pending(service, stripe)
    stripe.set_session_status(session_id, "complete")

    with pytest.raises(PaymentConfirmationRequired) as exc_info:
        await service.create_checkout(USER_A, "premium")

    assert exc_info.value.session_id == session_id
    assert len(stripe.create_calls) == 1
    [row] = rows_of(repo)
    assert row.status == "pending"


async def test_missing_session_is_replaced(service, repo, stripe):
    old_session_id = await start_pending(service, stripe)
    del stripe.sessions[old_session_id]

    started = await service.create_checkout(USER_A, "premium")

    old_row, new_row = rows_of(repo)
    assert old_row.status == "failed"
    assert new_row.stripe_checkout_session_id == started.session_id


# --- creating の行がある（Q-34の案） ---------------------------------------------


async def test_timeout_before_stripe_keeps_creating_and_retry_succeeds(service, repo, stripe):
    # PY-05：Stripeへ届かずに失敗した。行は creating のまま残し、failed にしない
    stripe.create_errors.append(StripeUnavailable("架空"))
    with pytest.raises(StripeUnavailable):
        await service.create_checkout(USER_A, "premium")
    [row] = rows_of(repo)
    assert row.status == "creating"

    started = await service.create_checkout(USER_A, "premium")

    [row] = rows_of(repo)
    assert row.status == "pending"
    assert row.stripe_checkout_session_id == started.session_id
    # 再試行は同じ idempotency key
    first, second = stripe.create_calls
    assert first["idempotency_key"] == second["idempotency_key"] == str(row.idempotency_key)


async def test_lost_response_retry_returns_same_session(service, repo, stripe):
    # Stripeでは作成されたが、タイムアウトで応答を受け取れなかった
    stripe.lose_next_response = True
    with pytest.raises(StripeUnavailable):
        await service.create_checkout(USER_A, "premium")

    started = await service.create_checkout(USER_A, "premium")

    # 同じ idempotency key で呼び直したため、Sessionは1件だけ
    assert stripe.created_session_count == 1
    assert started.session_id in stripe.sessions
    [row] = rows_of(repo)
    assert row.status == "pending"


async def test_changed_params_mark_failed_and_create_new(repo, stripe):
    # 1回目はStripeで作成されたが応答を受け取れず、その後URLの設定が変わった。
    # 同じ idempotency key で内容が違うため、Stripeが受け付けない
    stripe.lose_next_response = True
    with pytest.raises(StripeUnavailable):
        await CheckoutService(repo, stripe, SETTINGS).create_checkout(USER_A, "premium")

    changed = replace(SETTINGS, cancel_url="http://localhost:3000/plan?canceled=1")
    started = await CheckoutService(repo, stripe, changed).create_checkout(USER_A, "premium")

    old_row, new_row = rows_of(repo)
    assert old_row.status == "failed"
    assert new_row.status == "pending"
    assert new_row.stripe_checkout_session_id == started.session_id


# --- 同時リクエスト（PY-20） -----------------------------------------------------


async def test_concurrent_requests_create_one_session(service, repo, stripe):
    first, second = await asyncio.gather(
        service.create_checkout(USER_A, "premium"),
        service.create_checkout(USER_A, "premium"),
    )

    assert first.session_id == second.session_id
    assert stripe.created_session_count == 1
    [row] = rows_of(repo)
    assert row.status == "pending"


async def test_concurrent_request_while_stripe_in_progress(service, repo, stripe):
    # 1つ目がStripeとやり取りしている途中に、2つ目が届いた
    stripe.create_gate = asyncio.Event()
    first_task = asyncio.create_task(service.create_checkout(USER_A, "premium"))
    while not stripe.create_calls:
        await asyncio.sleep(0)

    with pytest.raises(CheckoutInProgress):
        await service.create_checkout(USER_A, "premium")

    stripe.create_gate.set()
    first = await first_task
    # 少し待ってから再試行すると、同じSessionが返る
    again = await service.create_checkout(USER_A, "premium")
    assert again.session_id == first.session_id
    assert stripe.created_session_count == 1


async def test_users_do_not_share_unfinished_payments(service, repo, stripe):
    user_b = uuid4()

    a, b = await asyncio.gather(
        service.create_checkout(USER_A, "premium"),
        service.create_checkout(user_b, "premium"),
    )

    assert a.session_id != b.session_id
    assert stripe.created_session_count == 2


# --- Stripeの呼び出し中に退会処理が始まった ---------------------------------------


async def test_user_deleting_during_stripe_call_keeps_session_record(service, repo, stripe):
    stripe.create_gate = asyncio.Event()
    task = asyncio.create_task(service.create_checkout(USER_A, "premium"))
    while not stripe.create_calls:
        await asyncio.sleep(0)
    repo.user_statuses[USER_A] = "deleting"
    stripe.create_gate.set()

    with pytest.raises(UserNotActive):
        await task

    # 作成したSessionは記録から消さない（退会の処理で扱う。#59で相談中）
    [row] = rows_of(repo)
    assert row.status == "pending"
    assert row.stripe_checkout_session_id in stripe.sessions


# --- ログ ----------------------------------------------------------------------


async def test_session_info_is_not_logged(service, repo, stripe, caplog):
    caplog.set_level(logging.DEBUG)
    stripe.create_errors.append(StripeUnavailable("架空"))
    with pytest.raises(StripeUnavailable):
        await service.create_checkout(USER_A, "premium")
    started = await service.create_checkout(USER_A, "premium")
    stripe.set_session_status(started.session_id, "expired")
    await service.create_checkout(USER_A, "premium")

    for row in rows_of(repo):
        assert str(row.idempotency_key) not in caplog.text
        if row.stripe_checkout_session_id:
            assert row.stripe_checkout_session_id not in caplog.text
    assert "checkout.stripe.com" not in caplog.text
    assert repr(started) == "CheckoutStarted()"
