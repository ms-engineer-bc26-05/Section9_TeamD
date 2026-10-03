"""相談Serviceのテスト。AIはFakeAIClientで模し、外部APIへは接続しない。"""

import asyncio
from uuid import uuid4

import pytest

from app.features.consultations.ai_schemas import AIOutputInvalid
from app.features.consultations.schemas import (
    ConsultationResultInput,
    ConsultationStatus,
    EmotionInput,
    EventDetailsInput,
    GuidedTopic,
    HandlingType,
    ThemeCategory,
)
from app.features.consultations.exceptions import (
    ConsultationStateConflict,
    GuidedSkipNotAllowed,
)
from app.features.consultations.public import discard_consultation, get_approved_result
from app.features.consultations.service import (
    SAFETY_MESSAGE_PLACEHOLDER,
    ConsultationService,
    current_guided_topic,
)
from app.features.consultations.store import (
    ConsultationBusy,
    ConsultationNotFound,
    ConsultationStore,
)
from app.integrations.openrouter.client import AIClientError

from tests.features.consultations import fakes

USER = uuid4()


@pytest.fixture
def store():
    return ConsultationStore()


@pytest.fixture
def ai():
    return fakes.FakeAIClient()


@pytest.fixture
def service(store, ai):
    return ConsultationService(store, ai)


async def start(service, ai):
    ai.push(fakes.first_question())
    return await service.start(USER, ThemeCategory.COMMUNICATION, "架空の相談本文")


async def advance_to_result_ready(service, ai):
    state = await start(service, ai)
    cid = state.consultation_id
    ai.push(fakes.event_summarize())
    await service.event_dialogue(USER, cid, "answer", "架空の回答")
    await service.confirm_event_summary(USER, cid, "proceed")
    ai.push(fakes.emotion_output())
    await service.submit_emotion(USER, cid, EmotionInput(category="anxious", detail="架空の具体化"))
    await answer_guided(service, ai, cid)
    return cid


async def answer_guided(service, ai, cid, complete=None):
    """本音 → 背景（まだ分からない）→ 望み の3問に答えて整理結果まで進める"""
    ai.push(fakes.guided_ask(), fakes.guided_ask(question="架空の望みの質問"))
    await service.guided_dialogue(USER, cid, "架空の本音", skipped=False)
    await service.guided_dialogue(USER, cid, None, skipped=True)
    ai.push(complete or fakes.guided_complete())
    return await service.guided_dialogue(USER, cid, "架空の望み", skipped=False)


# --- 正常系の一連の流れ -----------------------------------------------------------


@pytest.mark.asyncio
async def test_full_normal_flow(service, store, ai):
    state = await start(service, ai)
    cid = state.consultation_id
    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    assert state.ai_question == "架空の最初の質問"

    # 出来事：回答 → 訂正 → 回答（要約完成）
    ai.push(fakes.event_ask())
    state = await service.event_dialogue(USER, cid, "answer", "架空の回答1")
    assert (state.question_count, state.correction_count) == (1, 0)
    assert state.ai_understanding == "架空の理解"

    ai.push(fakes.event_ask(understanding="架空の訂正後の理解"))
    state = await service.event_dialogue(USER, cid, "correct", "架空の訂正")
    assert (state.question_count, state.correction_count) == (1, 1)

    ai.push(fakes.event_summarize())
    state = await service.event_dialogue(USER, cid, "answer", "架空の回答2")
    assert state.status is ConsultationStatus.EVENT_SUMMARY_READY
    assert state.event_details.what_happened == "架空の出来事"

    # 要約を直接編集して次へ
    edited = EventDetailsInput(what_happened="架空の編集後", what_bothered_me="架空の気がかり")
    state = await service.confirm_event_summary(USER, cid, "proceed", edited)
    assert state.status is ConsultationStatus.EMOTION_SELECTION
    assert state.event_details.what_happened == "架空の編集後"

    # 感情
    ai.push(fakes.emotion_output())
    state, ai_response = await service.submit_emotion(
        USER, cid, EmotionInput(category="anxious", detail="架空の具体化")
    )
    assert state.status is ConsultationStatus.GUIDED_DIALOGUE
    assert ai_response == "架空の受け止め"
    assert state.ai_question == "架空の本音の質問"

    # 本音・背景・望み（「まだ分からない」を含む）
    ai.push(fakes.guided_ask())
    state = await service.guided_dialogue(USER, cid, "架空の本音", skipped=False)
    ai.push(fakes.guided_ask(question="架空の望みの質問"))
    state = await service.guided_dialogue(USER, cid, None, skipped=True)
    ai.push(fakes.guided_complete())
    state = await service.guided_dialogue(USER, cid, "架空の望み", skipped=False)
    assert state.status is ConsultationStatus.RESULT_READY
    assert state.guided_turn_count == 3

    # 編集・承認・扱い方
    await service.update_result(USER, cid, ConsultationResultInput(wish="架空の編集した望み"))
    state = await service.approve_result(USER, cid)
    assert state.status is ConsultationStatus.HANDLING_SELECTION
    assert state.approved

    state = await service.choose_handling(USER, cid, HandlingType.HOLD)
    assert state.status is ConsultationStatus.SAVE_CONFIRMATION
    # 画面9から画面8へ戻っての選び直し
    state = await service.choose_handling(USER, cid, HandlingType.TELL)
    assert state.handling is HandlingType.TELL

    # I-05へ公開する関数
    approved = await get_approved_result(USER, cid, store=store)
    assert approved.result.wish == "架空の編集した望み"
    assert approved.handling is HandlingType.TELL
    await discard_consultation(USER, cid, store=store)
    await discard_consultation(USER, cid, store=store)  # 2回目も安全
    with pytest.raises(ConsultationNotFound):
        await get_approved_result(USER, cid, store=store)


@pytest.mark.asyncio
async def test_ask_more_returns_to_event_dialogue(service, ai):
    state = await start(service, ai)
    cid = state.consultation_id
    ai.push(fakes.event_summarize())
    await service.event_dialogue(USER, cid, "answer", "架空の回答")

    ai.push(fakes.event_ask(question="架空の追加の質問"))
    state = await service.confirm_event_summary(USER, cid, "ask_more")
    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    assert state.ai_question == "架空の追加の質問"


# --- ユーザー入力とsystemの分離 ---------------------------------------------------


@pytest.mark.asyncio
async def test_user_input_is_sent_only_as_user_role(service, ai):
    await advance_to_result_ready(service, ai)

    for call in ai.calls:
        system_messages = [m for m in call["messages"] if m["role"] == "system"]
        assert len(system_messages) == 1
        assert call["messages"][0]["role"] == "system"
        assert "架空" not in system_messages[0]["content"]


# --- 安全案内の識別 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_safety_on_start(service, store, ai):
    ai.push(fakes.safety_output(ai_question=None))
    state = await service.start(USER, ThemeCategory.OTHER, "架空の相談本文")

    assert state.status is ConsultationStatus.SAFETY_GUIDANCE
    assert state.safety_guidance.safety_message == SAFETY_MESSAGE_PLACEHOLDER  # AIの文は使わない
    assert state.safety_guidance.continued_normal_structuring is False
    assert state.messages == []  # 相談内容を保持しない
    assert store.exists(USER, state.consultation_id)


@pytest.mark.asyncio
async def test_safety_during_event_dialogue(service, ai):
    state = await start(service, ai)
    ai.push(
        fakes.safety_output(
            next_action=None, ai_understanding=None, ai_question=None, event_details=None
        )
    )
    state = await service.event_dialogue(USER, state.consultation_id, "answer", "架空の回答")
    assert state.status is ConsultationStatus.SAFETY_GUIDANCE
    assert state.ai_question is None


# --- AIの失敗時に状態を変えない ---------------------------------------------------


@pytest.mark.asyncio
async def test_start_failure_does_not_leave_state(service, store, ai):
    ai.push(AIClientError("失敗"))
    with pytest.raises(AIClientError):
        await service.start(USER, ThemeCategory.OTHER, "架空の相談本文")
    assert store._states == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [AIClientError("失敗"), {"kind": "normal"}])
async def test_ai_failure_does_not_count_correction(service, ai, failure):
    state = await start(service, ai)
    ai.push(failure)
    with pytest.raises((AIClientError, AIOutputInvalid)):
        await service.event_dialogue(USER, state.consultation_id, "correct", "架空の訂正")

    assert state.correction_count == 0
    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    # ロックは解放されている
    ai.push(fakes.event_ask())
    await service.event_dialogue(USER, state.consultation_id, "correct", "架空の訂正")
    assert state.correction_count == 1


# --- 状態と操作の矛盾 -------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_state_operations_conflict(service, ai):
    state = await start(service, ai)
    cid = state.consultation_id

    with pytest.raises(ConsultationStateConflict):
        await service.confirm_event_summary(USER, cid, "proceed")
    with pytest.raises(ConsultationStateConflict):
        service.get_result(USER, cid)
    with pytest.raises(ConsultationStateConflict):
        await service.approve_result(USER, cid)
    with pytest.raises(ConsultationStateConflict):
        await service.choose_handling(USER, cid, HandlingType.HOLD)


@pytest.mark.asyncio
async def test_approve_rejects_blank_required_field(service, ai):
    # AIの一次案は空文字を許容するため、本人が編集しないまま承認しようとした場合は409
    state = await start(service, ai)
    cid = state.consultation_id
    ai.push(fakes.event_summarize())
    await service.event_dialogue(USER, cid, "answer", "架空の回答")
    await service.confirm_event_summary(USER, cid, "proceed")
    ai.push(fakes.emotion_output())
    await service.submit_emotion(USER, cid, EmotionInput(category="anxious", cannot_verbalize=True))
    await answer_guided(service, ai, cid, complete=fakes.guided_complete(wish=""))

    with pytest.raises(ConsultationStateConflict):
        await service.approve_result(USER, cid)


@pytest.mark.asyncio
async def test_cannot_edit_after_approval(service, store, ai):
    cid = await advance_to_result_ready(service, ai)
    await service.approve_result(USER, cid)

    with pytest.raises(ConsultationStateConflict):
        await service.update_result(USER, cid, ConsultationResultInput(wish="架空"))
    with pytest.raises(ConsultationStateConflict):
        await service.approve_result(USER, cid)
    # 扱い方が未選択のうちは、I-05へ承認済み結果を渡さない
    with pytest.raises(ConsultationStateConflict):
        await get_approved_result(USER, cid, store=store)


@pytest.mark.asyncio
async def test_other_user_cannot_access(service, store, ai):
    state = await start(service, ai)
    other = uuid4()

    with pytest.raises(ConsultationNotFound):
        service.get(other, state.consultation_id)
    with pytest.raises(ConsultationNotFound):
        await service.event_dialogue(other, state.consultation_id, "answer", "架空")


# --- 同時実行 ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_consultation_rejects_while_ai_is_waiting(service, ai):
    state = await start(service, ai)
    cid = state.consultation_id

    ai.wait_event = asyncio.Event()
    ai.started.clear()
    ai.push(fakes.event_ask())
    first = asyncio.create_task(service.event_dialogue(USER, cid, "answer", "架空の回答1"))
    await ai.started.wait()

    with pytest.raises(ConsultationBusy):
        await service.event_dialogue(USER, cid, "answer", "架空の回答2")

    ai.wait_event.set()
    await first
    assert state.question_count == 1


@pytest.mark.asyncio
async def test_other_consultation_is_not_blocked_while_ai_is_waiting(store):
    slow_ai = fakes.FakeAIClient([fakes.first_question()])
    fast_ai = fakes.FakeAIClient([fakes.first_question(), fakes.event_ask()])
    slow = ConsultationService(store, slow_ai)
    fast = ConsultationService(store, fast_ai)

    slow_state = await slow.start(USER, ThemeCategory.OTHER, "架空の相談本文")
    slow_ai.wait_event = asyncio.Event()
    slow_ai.started.clear()
    slow_ai.push(fakes.event_ask())
    waiting = asyncio.create_task(
        slow.event_dialogue(USER, slow_state.consultation_id, "answer", "架空の回答")
    )
    await slow_ai.started.wait()

    # 1件目がAIの応答待ちでも、別の相談は最後まで処理できる
    other = await fast.start(uuid4(), ThemeCategory.OTHER, "架空の相談本文")
    other = await fast.event_dialogue(other.user_id, other.consultation_id, "answer", "架空の回答")
    assert other.question_count == 1
    assert not waiting.done()

    slow_ai.wait_event.set()
    await waiting


# --- 本音・背景・望みの進め方（サーバー管理） -------------------------------------


async def advance_to_guided(service, ai):
    state = await start(service, ai)
    cid = state.consultation_id
    ai.push(fakes.event_summarize())
    await service.event_dialogue(USER, cid, "answer", "架空の回答")
    await service.confirm_event_summary(USER, cid, "proceed")
    ai.push(fakes.emotion_output())
    state, _ = await service.submit_emotion(
        USER, cid, EmotionInput(category="anxious", detail="架空の具体化")
    )
    return state


@pytest.mark.asyncio
async def test_guided_topics_follow_server_order(service, ai):
    state = await advance_to_guided(service, ai)
    cid = state.consultation_id
    assert current_guided_topic(state) is GuidedTopic.TRUE_FEELING

    ai.push(fakes.guided_ask())
    state = await service.guided_dialogue(USER, cid, "架空の本音", skipped=False)
    assert current_guided_topic(state) is GuidedTopic.BACKGROUND
    # AIへは「次に聞く項目」をsystemで指定する
    assert "次に聞く項目（指定）：背景" in ai.calls[-1]["messages"][0]["content"]

    ai.push(fakes.guided_ask())
    state = await service.guided_dialogue(USER, cid, None, skipped=True)
    assert current_guided_topic(state) is GuidedTopic.WISH

    ai.push(fakes.guided_complete(background="架空のAIが補った背景"))
    state = await service.guided_dialogue(USER, cid, "架空の望み", skipped=False)
    assert state.status is ConsultationStatus.RESULT_READY
    assert current_guided_topic(state) is None
    assert "整理を完了する" in ai.calls[-1]["messages"][0]["content"]
    # 背景が「まだ分からない」の場合は空文字にする
    assert state.result.background == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("answers", [0, 2])
async def test_skip_is_allowed_only_for_background(service, ai, answers):
    state = await advance_to_guided(service, ai)
    cid = state.consultation_id
    for _ in range(answers):
        ai.push(fakes.guided_ask())
        await service.guided_dialogue(USER, cid, "架空の回答", skipped=False)
    calls = len(ai.calls)

    with pytest.raises(GuidedSkipNotAllowed):
        await service.guided_dialogue(USER, cid, None, skipped=True)
    assert len(ai.calls) == calls  # AIを呼ばない
    assert state.guided_turn_count == answers


@pytest.mark.asyncio
async def test_ai_completing_too_early_is_invalid(service, ai):
    state = await advance_to_guided(service, ai)
    ai.push(fakes.guided_complete())

    with pytest.raises(AIOutputInvalid):
        await service.guided_dialogue(USER, state.consultation_id, "架空の本音", skipped=False)
    assert state.status is ConsultationStatus.GUIDED_DIALOGUE
    assert state.guided_turn_count == 0
    assert state.result is None


@pytest.mark.asyncio
async def test_ai_asking_after_last_topic_is_invalid(service, ai):
    state = await advance_to_guided(service, ai)
    cid = state.consultation_id
    ai.push(fakes.guided_ask(), fakes.guided_ask())
    await service.guided_dialogue(USER, cid, "架空の本音", skipped=False)
    await service.guided_dialogue(USER, cid, "架空の背景", skipped=False)

    ai.push(fakes.guided_ask())
    with pytest.raises(AIOutputInvalid):
        await service.guided_dialogue(USER, cid, "架空の望み", skipped=False)
    assert state.guided_turn_count == 2
    assert current_guided_topic(state) is GuidedTopic.WISH
