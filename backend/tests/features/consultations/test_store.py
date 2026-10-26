"""一時状態ストアと相談ID単位のロックのテスト。テストデータはすべて架空。"""

import asyncio
from uuid import uuid4

import pytest

from app.features.consultations.public import discard_user_consultations
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


@pytest.mark.asyncio
async def test_exception_inside_lock_restores_state():
    # テスト設計書 ST-19：状態を書き換えた後に例外が起きた場合は、ロック取得時の状態へ戻す
    store = ConsultationStore()
    state = make_state(uuid4())
    state.messages.append(DialogueTurn(role="user", content="架空の相談本文"))
    state.ai_question = "架空の質問"
    store.add(state)
    before_updated_at = state.updated_at

    with pytest.raises(RuntimeError):
        async with store.locked(state.user_id, state.consultation_id) as s:
            s.question_count += 1
            s.ai_question = "架空の次の質問"
            s.messages.append(DialogueTurn(role="user", content="架空の回答"))
            s.status = ConsultationStatus.EVENT_SUMMARY_READY
            s.touch()
            raise RuntimeError("想定外のエラー")

    assert state.question_count == 0
    assert state.ai_question == "架空の質問"
    assert [t.content for t in state.messages] == ["架空の相談本文"]
    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    assert state.updated_at == before_updated_at
    # ロックは解放されている
    assert not state.lock.locked()


@pytest.mark.asyncio
async def test_successful_update_is_kept():
    store = ConsultationStore()
    state = make_state(uuid4())
    store.add(state)

    async with store.locked(state.user_id, state.consultation_id) as s:
        s.question_count += 1

    assert state.question_count == 1


# --- 退会処理の破棄の後は、相談開始を受け付けない（#96） ---------------------------


def test_start_is_rejected_after_withdrawal_discard():
    store = ConsultationStore()
    user_id = uuid4()
    store.discard_withdrawn_user(user_id)

    with pytest.raises(ConsultationNotFound):
        with store.reserve_start(user_id):
            pass
    # 拒否した場合は予約を残さない
    assert user_id not in store._starting


def test_registration_is_blocked_when_start_arrives_after_withdrawal_discard():
    # deleting の確定前に認証を通過した相談開始が、退会処理の破棄の後に届いた場合を模す
    store = ConsultationStore()
    user_id = uuid4()
    store.discard_withdrawn_user(user_id)

    with pytest.raises(ConsultationNotFound):
        with store.reserve_start(user_id) as reservation:
            reservation.commit(make_state(user_id))
    assert not [s for s in store._states.values() if s.user_id == user_id]


def test_withdrawal_discard_does_not_affect_other_users():
    store = ConsultationStore()
    other = make_state(uuid4())
    store.add(other)

    store.discard_withdrawn_user(uuid4())

    # 他のユーザーの相談は残り、相談開始もできる
    assert store.exists(other.user_id, other.consultation_id)
    new_state = make_state(uuid4())
    with store.reserve_start(new_state.user_id) as reservation:
        reservation.commit(new_state)
    assert store.exists(new_state.user_id, new_state.consultation_id)


def test_withdrawal_discard_is_idempotent():
    store = ConsultationStore()
    state = make_state(uuid4())
    store.add(state)

    store.discard_withdrawn_user(state.user_id)
    store.discard_withdrawn_user(state.user_id)  # 2回目もエラーにならない

    assert not store.exists(state.user_id, state.consultation_id)
    with pytest.raises(ConsultationNotFound):
        with store.reserve_start(state.user_id):
            pass


def test_new_consultation_does_not_block_next_start():
    # 新しい相談の登録時の破棄（discard_user）では記録しないため、続けて相談を開始できる
    store = ConsultationStore()
    user_id = uuid4()
    first = make_state(user_id)
    with store.reserve_start(user_id) as reservation:
        reservation.commit(first)

    second = make_state(user_id)
    with store.reserve_start(user_id) as reservation:
        reservation.commit(second)

    assert not store.exists(user_id, first.consultation_id)  # 1ユーザー1件
    assert store.exists(user_id, second.consultation_id)


def test_discard_user_does_not_block_next_start():
    # discard_user 自体はユーザーを記録しない（退会以外の破棄に影響させない）
    store = ConsultationStore()
    user_id = uuid4()
    store.discard_user(user_id)

    with store.reserve_start(user_id) as reservation:
        assert reservation.active


@pytest.mark.asyncio
async def test_discard_user_consultations_blocks_later_start():
    # 公開関数（F-06から呼ぶ入口）が、退会用の破棄を使っていることを確認する
    store = ConsultationStore()
    user_id = uuid4()
    await discard_user_consultations(user_id, store=store)

    with pytest.raises(ConsultationNotFound):
        with store.reserve_start(user_id):
            pass
