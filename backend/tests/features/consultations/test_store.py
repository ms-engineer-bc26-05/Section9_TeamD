"""一時状態ストアと相談ID単位のロックのテスト。テストデータはすべて架空。"""

import asyncio
from uuid import uuid4

import pytest

from app.features.consultations.schemas import ConsultationStatus, ThemeCategory
from app.features.consultations.state import ConsultationState, DialogueTurn
from app.features.consultations.store import (
    ConsultationBusy,
    ConsultationNotFound,
    ConsultationStore,
)


def make_state(user_id):
    return ConsultationState(
        consultation_id=uuid4(),
        user_id=user_id,
        theme=ThemeCategory.COMMUNICATION,
        status=ConsultationStatus.EVENT_DIALOGUE,
    )


def test_get_returns_own_state():
    store = ConsultationStore()
    user_id = uuid4()
    state = make_state(user_id)
    store.add(state)

    assert store.get(user_id, state.consultation_id) is state


def test_get_rejects_other_user_and_missing_in_same_way():
    store = ConsultationStore()
    state = make_state(uuid4())
    store.add(state)

    with pytest.raises(ConsultationNotFound):
        store.get(uuid4(), state.consultation_id)  # 他人の相談
    with pytest.raises(ConsultationNotFound):
        store.get(state.user_id, uuid4())  # 存在しない相談


def test_discard_is_idempotent_and_ignores_other_user():
    store = ConsultationStore()
    state = make_state(uuid4())
    store.add(state)

    store.discard(uuid4(), state.consultation_id)  # 他人からは破棄できない
    assert store.exists(state.user_id, state.consultation_id)

    store.discard(state.user_id, state.consultation_id)
    store.discard(state.user_id, state.consultation_id)  # 2回目もエラーにならない
    assert not store.exists(state.user_id, state.consultation_id)


def test_repr_does_not_contain_consultation_content():
    state = make_state(uuid4())
    state.messages.append(DialogueTurn(role="user", content="架空の相談本文"))
    state.ai_question = "架空の質問"

    assert "架空" not in repr(state)


@pytest.mark.asyncio
async def test_locked_rejects_second_request_to_same_consultation():
    store = ConsultationStore()
    state = make_state(uuid4())
    store.add(state)

    async with store.locked(state.user_id, state.consultation_id):
        with pytest.raises(ConsultationBusy):
            async with store.locked(state.user_id, state.consultation_id):
                pass

    # ロック解放後は再び取得できる
    async with store.locked(state.user_id, state.consultation_id) as locked_state:
        assert locked_state is state


@pytest.mark.asyncio
async def test_lock_does_not_block_other_consultations():
    store = ConsultationStore()
    first = make_state(uuid4())
    second = make_state(uuid4())
    store.add(first)
    store.add(second)

    ai_waiting = asyncio.Event()
    release_ai = asyncio.Event()

    async def slow_update():
        # AI応答待ちを模して、ロックを保持したまま待つ
        async with store.locked(first.user_id, first.consultation_id):
            ai_waiting.set()
            await release_ai.wait()

    task = asyncio.create_task(slow_update())
    await ai_waiting.wait()

    # 1件目がロック中でも、別の相談はすぐに処理できる
    async with store.locked(second.user_id, second.consultation_id) as state:
        assert state is second

    release_ai.set()
    await task


@pytest.mark.asyncio
async def test_concurrent_requests_to_same_consultation_only_one_succeeds():
    store = ConsultationStore()
    state = make_state(uuid4())
    store.add(state)

    async def update():
        async with store.locked(state.user_id, state.consultation_id) as s:
            await asyncio.sleep(0.01)  # AI応答待ちを模す
            s.question_count += 1

    results = await asyncio.gather(update(), update(), return_exceptions=True)

    assert sum(r is None for r in results) == 1
    assert sum(isinstance(r, ConsultationBusy) for r in results) == 1
    assert state.question_count == 1
