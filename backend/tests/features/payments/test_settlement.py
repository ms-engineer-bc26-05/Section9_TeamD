"""退会時の未完了の決済の照合（PaymentSettlementService）のテスト。DB・Stripeは fakes.py の偽物を使う。

#60で合意した退会用の関数と、#59でもえさんと確認した「状態不明の間は退会へ進まない」に対応する。
"""

import logging
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.features.payments.exceptions import (
    PaymentSettlementBlocked,
    PaymentVerificationFailed,
)
from app.features.payments.service import CheckoutService
from app.features.payments.settings import CheckoutSettings
from app.features.payments.settlement import PaymentSettlementService
from app.integrations.stripe.client import (
    StripeRequestFailed,
    StripeSessionNotFound,
    StripeUnavailable,
)
from tests.features.payments.fakes import FakeStripe, InMemoryPaymentRepository

USER_A = UUID("00000000-0000-0000-0000-000000000001")
USER_B = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)

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
def settlement(repo, stripe) -> PaymentSettlementService:
    return PaymentSettlementService(repo, stripe, now=lambda: NOW)


async def start_pending(repo, stripe, user_id: UUID = USER_A) -> str:
    """pending の行を作り、そのSession IDを返す（その後、退会処理でユーザーを deleting にする）"""
    started = await CheckoutService(repo, stripe, SETTINGS).create_checkout(user_id, "premium")
    repo.user_statuses[user_id] = "deleting"
    return started.session_id


def row_of(repo, session_id: str):
    [row] = [r for r in repo.rows.values() if r.stripe_checkout_session_id == session_id]
    return row


# --- 未完了の行がない --------------------------------------------------------------


async def test_no_unfinished_payment_does_nothing(settlement, repo, stripe):
    repo.user_statuses[USER_A] = "deleting"

    await settlement.settle_unfinished_payments(USER_A)

    assert stripe.retrieve_calls == []


# --- pending の行 ---------------------------------------------------------------


async def test_open_session_is_expired(settlement, repo, stripe):
    session_id = await start_pending(repo, stripe)

    await settlement.settle_unfinished_payments(USER_A)

    assert stripe.expire_calls == [session_id]
    assert stripe.sessions[session_id].status == "expired"
    assert row_of(repo, session_id).status == "expired"


async def test_expired_session_is_marked_expired(settlement, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.set_session_status(session_id, "expired")

    await settlement.settle_unfinished_payments(USER_A)

    assert stripe.expire_calls == []
    assert row_of(repo, session_id).status == "expired"


async def test_paid_session_is_recorded_without_entitlement(settlement, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)

    await settlement.settle_unfinished_payments(USER_A)

    row = row_of(repo, session_id)
    assert row.status == "paid"
    assert row.verified_at == NOW
    # 退会処理中のため、利用権限は付与しない
    assert row.entitlement_applied_at is None
    assert USER_A not in repo.entitlements


async def test_missing_session_blocks(settlement, repo, stripe):
    session_id = await start_pending(repo, stripe)
    del stripe.sessions[session_id]

    with pytest.raises(PaymentSettlementBlocked):
        await settlement.settle_unfinished_payments(USER_A)

    # 見つからないだけでは failed にせず、退会を止める（PR #100のレビュー）
    assert row_of(repo, session_id).status == "pending"


async def test_session_in_other_environment_blocks(settlement, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)

    # 作成時と別のアカウント・サンドボックスの鍵で照会すると、支払い済みでも見つからない
    other_settlement = PaymentSettlementService(repo, FakeStripe(), now=lambda: NOW)
    with pytest.raises(PaymentSettlementBlocked):
        await other_settlement.settle_unfinished_payments(USER_A)
    assert row_of(repo, session_id).status == "pending"

    # 元の環境に戻すと、支払い済みの記録が残る
    await settlement.settle_unfinished_payments(USER_A)
    assert row_of(repo, session_id).status == "paid"


# --- 期限切れにできない場合 ---------------------------------------------------------


async def test_expire_fails_but_session_was_paid(settlement, repo, stripe):
    """期限切れにする直前に支払われた。照会し直して paid の記録を残す"""
    session_id = await start_pending(repo, stripe)
    stripe.expire_errors.append(StripeRequestFailed("架空"))
    # 支払いは済んでいるが、最初の照会ではまだ open に見えていた状態を再現する
    stripe.sessions[session_id] = replace(stripe.sessions[session_id], payment_status="paid")
    original_retrieve = stripe.retrieve_checkout_session
    calls = 0

    async def retrieve(sid):
        nonlocal calls
        calls += 1
        session = await original_retrieve(sid)
        return session if calls == 1 else replace(session, status="complete")

    stripe.retrieve_checkout_session = retrieve

    await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "paid"


async def test_expire_fails_and_session_is_still_open(settlement, repo, stripe):
    """期限切れにできず、照会し直しても open。未確認のまま expired にしない"""
    session_id = await start_pending(repo, stripe)
    stripe.expire_errors.append(StripeRequestFailed("架空"))

    with pytest.raises(PaymentSettlementBlocked):
        await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "pending"


async def test_expire_and_retrieve_unavailable_keeps_pending(settlement, repo, stripe):
    """Stripeに接続できない。例外をそのまま送出し、再実行で再開できるよう行を変えない"""
    session_id = await start_pending(repo, stripe)
    stripe.expire_errors.append(StripeUnavailable("架空"))
    original_retrieve = stripe.retrieve_checkout_session
    calls = 0

    async def retrieve(sid):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise StripeUnavailable("架空")
        return await original_retrieve(sid)

    stripe.retrieve_checkout_session = retrieve

    with pytest.raises(StripeUnavailable):
        await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "pending"


async def test_retrieve_unavailable_keeps_pending(settlement, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.retrieve_errors.append(StripeUnavailable("架空"))

    with pytest.raises(StripeUnavailable):
        await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "pending"


async def test_rerun_after_failure_settles(settlement, repo, stripe):
    """Stripeの障害で止まった後、再実行すると照合が終わる"""
    session_id = await start_pending(repo, stripe)
    stripe.retrieve_errors.append(StripeUnavailable("架空"))
    with pytest.raises(StripeUnavailable):
        await settlement.settle_unfinished_payments(USER_A)

    await settlement.settle_unfinished_payments(USER_A)
    await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "expired"
    assert stripe.expire_calls == [session_id]


# --- 確定できない場合は止める ----------------------------------------------------------


async def test_creating_payment_blocks_settlement(settlement, repo, stripe):
    """状態不明の creating が残っている間は、退会へ進まない（#59・#60）"""
    stripe.create_errors.append(StripeUnavailable("架空"))
    with pytest.raises(StripeUnavailable):
        await CheckoutService(repo, stripe, SETTINGS).create_checkout(USER_A, "premium")
    repo.user_statuses[USER_A] = "deleting"
    [row] = repo.rows.values()
    assert row.status == "creating"

    with pytest.raises(PaymentSettlementBlocked):
        await settlement.settle_unfinished_payments(USER_A)

    assert [r.status for r in repo.rows.values()] == ["creating"]
    assert stripe.retrieve_calls == []


async def test_complete_but_unpaid_blocks_settlement(settlement, repo, stripe):
    session_id = await start_pending(repo, stripe)
    stripe.set_session_status(session_id, "complete")  # payment_status は unpaid のまま

    with pytest.raises(PaymentSettlementBlocked):
        await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "pending"


@pytest.mark.parametrize(
    "changes",
    [{"amount_total": 1}, {"currency": "usd"}, {"client_reference_id": str(USER_B)}],
)
async def test_mismatched_session_is_not_recorded(settlement, repo, stripe, changes):
    session_id = await start_pending(repo, stripe)
    stripe.pay(session_id)
    stripe.sessions[session_id] = replace(stripe.sessions[session_id], **changes)

    with pytest.raises(PaymentVerificationFailed):
        await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "pending"


# --- ほかのユーザー・ログ -------------------------------------------------------------


async def test_other_users_payment_is_untouched(settlement, repo, stripe):
    mine = await start_pending(repo, stripe, USER_A)
    others = await start_pending(repo, stripe, USER_B)
    repo.user_statuses[USER_B] = "active"

    await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, mine).status == "expired"
    assert row_of(repo, others).status == "pending"
    assert stripe.sessions[others].status == "open"


async def test_session_info_is_not_logged(settlement, repo, stripe, caplog):
    session_id = await start_pending(repo, stripe)
    stripe.expire_errors.append(StripeRequestFailed("架空"))
    caplog.set_level(logging.DEBUG)

    with pytest.raises(PaymentSettlementBlocked):
        await settlement.settle_unfinished_payments(USER_A)

    assert session_id not in caplog.text
    assert "checkout.stripe.com" not in caplog.text


async def test_not_found_on_retry_blocks(settlement, repo, stripe):
    """期限切れにできず、照会し直したらSessionが見つからない。確認できないので止める"""
    session_id = await start_pending(repo, stripe)
    stripe.expire_errors.append(StripeRequestFailed("架空"))
    original_retrieve = stripe.retrieve_checkout_session
    calls = 0

    async def retrieve(sid):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise StripeSessionNotFound("架空")
        return await original_retrieve(sid)

    stripe.retrieve_checkout_session = retrieve

    with pytest.raises(PaymentSettlementBlocked):
        await settlement.settle_unfinished_payments(USER_A)

    assert row_of(repo, session_id).status == "pending"
