"""決済の確認（PaymentConfirmService）のテスト。DB・Stripeは fakes.py の偽物を使う。

#59の結論（確認の照合、session_id の省略、支払い後に退会処理が始まっていた場合）に対応する。
"""

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.features.payments.confirm import ConfirmResult, PaymentConfirmService
from app.features.payments.exceptions import (
    AlreadyPaid,
    PaymentNotFound,
    PaymentVerificationFailed,
)
from app.features.payments.repository import UserNotActive
from app.features.payments.service import CheckoutService
from app.features.payments.settings import CheckoutSettings
from app.integrations.stripe.client import StripeUnavailable
from tests.features.payments.fakes import (
    PREMIUM_PLAN,
    FakeStripe,
    InMemoryPaymentRepository,
)

USER_A = UUID("00000000-0000-0000-0000-000000000001")
USER_B = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)

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
def confirm(repo, stripe) -> PaymentConfirmService:
    return PaymentConfirmService(repo, stripe, now=lambda: NOW)


async def start_pending(repo, stripe, user_id: UUID = USER_A) -> str:
    """pending の行を作り、そのSession IDを返す"""
    started = await CheckoutService(repo, stripe, SETTINGS).create_checkout(user_id, "premium")
    return started.session_id


def row_of(repo, session_id: str):
    [row] = [r for r in repo.rows.values() if r.stripe_checkout_session_id == session_id]
    return row


# --- 支払い済み ----------------------------------------------------------------


async def test_paid_session_grants_entitlement(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)

    result = await confirm.confirm(USER_A, session_id)

    assert result == ConfirmResult("paid")
    row = row_of(repo, session_id)
    assert row.status == "paid"
    assert row.verified_at == NOW
    assert row.entitlement_applied_at == NOW
    assert repo.entitlements == {USER_A: PREMIUM_PLAN.id}
    # 有料になった後は、新しいSessionを作らない
    with pytest.raises(AlreadyPaid):
        await CheckoutService(repo, stripe, SETTINGS).create_checkout(USER_A, "premium")


async def test_confirm_again_returns_same_result_without_stripe(confirm, repo, stripe):
    # 成功画面の再読み込み：同じ session_id で何度呼んでも同じ結果
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)
    await confirm.confirm(USER_A, session_id)
    calls = len(stripe.retrieve_calls)

    result = await confirm.confirm(USER_A, session_id)

    assert result == ConfirmResult("paid")
    assert len(stripe.retrieve_calls) == calls
    assert repo.entitlements == {USER_A: PREMIUM_PLAN.id}


async def test_concurrent_confirms_apply_once(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)

    first, second = await asyncio.gather(
        confirm.confirm(USER_A, session_id),
        confirm.confirm(USER_A, session_id),
    )

    assert first == second == ConfirmResult("paid")
    row = row_of(repo, session_id)
    assert (row.status, row.entitlement_applied_at) == ("paid", NOW)
    assert repo.entitlements == {USER_A: PREMIUM_PLAN.id}


# --- session_id の省略（「決済を確認する」ボタン） ---------------------------------


async def test_omitted_session_id_confirms_own_pending(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)

    result = await confirm.confirm(USER_A)

    assert result == ConfirmResult("paid")
    assert stripe.retrieve_calls[-1] == session_id


async def test_omitted_session_id_without_payment_is_not_found(confirm, repo, stripe):
    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A)


async def test_omitted_session_id_ignores_creating(confirm, repo, stripe):
    # creating の行はSessionのurlがまだユーザーに渡っていないため、確認の対象にしない
    stripe.create_errors.append(StripeUnavailable("架空"))
    with pytest.raises(StripeUnavailable):
        await CheckoutService(repo, stripe, SETTINGS).create_checkout(USER_A, "premium")

    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A)
    assert stripe.retrieve_calls == []


async def test_omitted_session_id_does_not_pick_other_users(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe, USER_B)
    stripe.pay(session_id)

    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A)
    assert repo.entitlements == {}


# --- 本人・内容の照合 -------------------------------------------------------------


async def test_other_users_session_is_not_found(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe, USER_B)
    stripe.pay(session_id)

    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A, session_id)
    assert row_of(repo, session_id).status == "pending"
    assert stripe.retrieve_calls == []


async def test_unknown_session_id_is_not_found(confirm, repo, stripe):
    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A, "cs_test_unknown")


async def test_session_missing_in_stripe_is_not_found(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)
    del stripe.sessions[session_id]

    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A, session_id)


@pytest.mark.parametrize(
    "changes",
    [
        {"client_reference_id": str(USER_B)},
        {"metadata": {"payment_id": "00000000-0000-0000-0000-0000000000ff"}},
        {"metadata": {}},
    ],
)
async def test_session_owner_mismatch_is_not_found(confirm, repo, stripe, changes):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)
    stripe.sessions[session_id] = replace(stripe.sessions[session_id], **changes)

    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A, session_id)
    assert row_of(repo, session_id).status == "pending"
    assert repo.entitlements == {}


@pytest.mark.parametrize("changes", [{"amount_total": 500}, {"currency": "usd"}])
async def test_amount_or_currency_mismatch_is_not_paid(confirm, repo, stripe, changes):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)
    stripe.sessions[session_id] = replace(stripe.sessions[session_id], **changes)

    with pytest.raises(PaymentVerificationFailed):
        await confirm.confirm(USER_A, session_id)
    assert row_of(repo, session_id).status == "pending"
    assert repo.entitlements == {}


# --- まだ支払われていない・期限切れ -----------------------------------------------


async def test_unpaid_session_is_pending(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)

    result = await confirm.confirm(USER_A, session_id)

    assert result == ConfirmResult("pending")
    assert row_of(repo, session_id).status == "pending"
    assert repo.entitlements == {}


async def test_expired_session_marks_expired(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.set_session_status(session_id, "expired")

    result = await confirm.confirm(USER_A, session_id)

    assert result == ConfirmResult("expired")
    assert row_of(repo, session_id).status == "expired"
    # 期限切れの行は、もう確認の対象にしない
    with pytest.raises(PaymentNotFound):
        await confirm.confirm(USER_A, session_id)


async def test_stripe_unavailable_keeps_pending(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)
    stripe.retrieve_errors.append(StripeUnavailable("架空"))

    with pytest.raises(StripeUnavailable):
        await confirm.confirm(USER_A, session_id)
    assert row_of(repo, session_id).status == "pending"


# --- 支払い後に退会処理が始まっていた -------------------------------------------


async def test_deleting_user_records_paid_without_entitlement(confirm, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)
    repo.user_statuses[USER_A] = "deleting"

    with pytest.raises(UserNotActive):
        await confirm.confirm(USER_A, session_id)

    # paid の記録は commit されている。利用権限は付与しない
    row = row_of(repo, session_id)
    assert (row.status, row.verified_at) == ("paid", NOW)
    assert row.entitlement_applied_at is None
    assert repo.entitlements == {}

    # もう一度呼んでも、Stripeは呼ばずに同じ結果
    calls = len(stripe.retrieve_calls)
    with pytest.raises(UserNotActive):
        await confirm.confirm(USER_A, session_id)
    assert len(stripe.retrieve_calls) == calls
    assert repo.entitlements == {}


# --- ログ ----------------------------------------------------------------------


async def test_session_info_is_not_logged(confirm, repo, stripe, caplog):
    caplog.set_level(logging.DEBUG)
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)
    stripe.sessions[session_id] = replace(stripe.sessions[session_id], amount_total=500)

    with pytest.raises(PaymentVerificationFailed):
        await confirm.confirm(USER_A, session_id)

    assert session_id not in caplog.text
    assert "checkout.stripe.com" not in caplog.text
