"""I-05へ公開する契約（public.py）のテスト。テストデータはすべて架空。"""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.consultations.public import (
    ConsultationNotFound,
    ConsultationStateConflict,
    discard_consultation,
    get_approved_result,
)
from app.features.consultations.schemas import ConsultationStatus, HandlingType
from app.features.consultations.store import ConsultationStore

from tests.features.consultations.factories import make_save_confirmation_state


@pytest.fixture
def store():
    return ConsultationStore()


@pytest.mark.asyncio
async def test_returns_frozen_copy_with_utc_approved_at(store):
    user_id = uuid4()
    state = make_save_confirmation_state(store, user_id, handling=HandlingType.TELL)

    approved = await get_approved_result(user_id, state.consultation_id, store=store)

    assert approved.consultation_id == state.consultation_id
    assert approved.handling is HandlingType.TELL
    assert approved.result.wish == "架空の望み"
    # タイムゾーン付き（UTC）
    assert approved.approved_at.tzinfo is not None
    assert approved.approved_at.utcoffset() == timedelta(0)
    # 書き換えできない
    with pytest.raises(AttributeError):
        approved.handling = HandlingType.HOLD
    with pytest.raises(ValidationError):
        approved.result.wish = "架空の書き換え"
    # 一時状態から切り離されている
    assert approved.result is not state.approved_result


@pytest.mark.asyncio
async def test_works_while_consultation_lock_is_held(store):
    user_id = uuid4()
    state = make_save_confirmation_state(store, user_id)

    async with store.locked(user_id, state.consultation_id):
        # 同じ相談の別の処理中でも、409（CONSULTATION_BUSY）にならない
        approved = await get_approved_result(user_id, state.consultation_id, store=store)
        await discard_consultation(user_id, state.consultation_id, store=store)

    assert approved.result.event_summary == "架空の出来事の要約"
    assert not store.exists(user_id, state.consultation_id)


@pytest.mark.asyncio
async def test_not_found_for_other_user_and_after_discard(store):
    user_id = uuid4()
    state = make_save_confirmation_state(store, user_id)

    with pytest.raises(ConsultationNotFound):
        await get_approved_result(uuid4(), state.consultation_id, store=store)

    await discard_consultation(uuid4(), state.consultation_id, store=store)  # 他人は破棄できない
    assert store.exists(user_id, state.consultation_id)

    await discard_consultation(user_id, state.consultation_id, store=store)
    await discard_consultation(user_id, state.consultation_id, store=store)  # 冪等
    with pytest.raises(ConsultationNotFound):
        await get_approved_result(user_id, state.consultation_id, store=store)


@pytest.mark.asyncio
async def test_conflict_before_handling_is_selected(store):
    user_id = uuid4()
    state = make_save_confirmation_state(store, user_id)
    state.status = ConsultationStatus.HANDLING_SELECTION
    state.handling = None

    with pytest.raises(ConsultationStateConflict):
        await get_approved_result(user_id, state.consultation_id, store=store)


@pytest.mark.asyncio
async def test_uses_shared_store_when_not_specified():
    from app.features.consultations.store import get_consultation_store

    shared = get_consultation_store()
    user_id = uuid4()
    state = make_save_confirmation_state(shared, user_id)
    try:
        approved = await get_approved_result(user_id, state.consultation_id)
        assert approved.consultation_id == state.consultation_id
    finally:
        await discard_consultation(user_id, state.consultation_id)
