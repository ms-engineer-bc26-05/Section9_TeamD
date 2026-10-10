"""回数上限のテスト（I-03B。テスト設計書 ST-01〜ST-06・ST-15）。テストデータはすべて架空。

前提の状態（回数・status）は、テスト設計書3.4に従い、一時状態を直接用意する。
AIは FakeAIClient で模し、外部APIへは接続しない。
"""

import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.consultations.router import get_current_user_id, router
from app.features.consultations.schemas import (
    ConsultationResultDraft,
    ConsultationStatus,
    EventDetailsDraft,
    ThemeCategory,
)
from app.features.consultations.service import (
    CORRECTION_LIMIT,
    QUESTION_LIMIT,
    ConsultationService,
)
from app.features.consultations.state import ConsultationState
from app.features.consultations.store import ConsultationStore, get_consultation_store
from app.integrations.openrouter.client import get_ai_client

from tests.features.consultations import fakes

BASE = "/api/v1/consultations"
SUMMARY_INSTRUCTION = "指定：回答または訂正の回数が上限に達したので、要約する"


@pytest.fixture
def ai():
    return fakes.FakeAIClient()


@pytest.fixture
def store():
    return ConsultationStore()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def app(ai, store, user_id):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def make_state(store, user_id, status, **fields):
    state = ConsultationState(
        consultation_id=uuid4(),
        user_id=user_id,
        theme=ThemeCategory.COMMUNICATION,
        status=status,
        **fields,
    )
    if status is ConsultationStatus.EVENT_DIALOGUE:
        state.ai_understanding = "架空の理解"
        state.ai_question = "架空の質問"
    if status is ConsultationStatus.EVENT_SUMMARY_READY:
        state.event_details = EventDetailsDraft(
            what_happened="架空の出来事", what_bothered_me="架空の気がかり"
        )
    store.add(state)
    return state


def answer(client, state, text="架空の回答"):
    return client.post(
        f"{BASE}/{state.consultation_id}/event-dialogue",
        json={"action": "answer", "answer": text},
    )


def correct(client, state, text="架空の訂正"):
    return client.post(
        f"{BASE}/{state.consultation_id}/event-dialogue",
        json={"action": "correct", "correction_input": text},
    )


def ask_more(client, state):
    return client.post(
        f"{BASE}/{state.consultation_id}/event-summary/confirm", json={"action": "ask_more"}
    )


def assert_conflict(response):
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSULTATION_STATE_CONFLICT"


def test_limits_are_three_answers_and_two_corrections():
    assert QUESTION_LIMIT == 3
    assert CORRECTION_LIMIT == 2


# --- 出来事の回答（上限3回） -------------------------------------------------------


def test_answer_reaching_limit_moves_to_summary(client, ai, store, user_id):
    # ST-01
    state = make_state(store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=2)
    ai.push(fakes.event_summarize())

    response = answer(client, state)

    assert response.status_code == 200
    assert response.json() == {
        "status": "event_summary_ready",
        "question_count": 3,
        "can_ask_more": False,
        "event_details": {"what_happened": "架空の出来事", "what_bothered_me": "架空の気がかり"},
        "correction_count": 0,
        "correction_limit_reached": False,
    }
    # 上限に達する回は、AIへ「要約する」と指定する
    assert SUMMARY_INSTRUCTION in ai.calls[-1]["messages"][0]["content"]


def test_answer_before_limit_does_not_force_summary(client, ai, store, user_id):
    state = make_state(store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=1)
    ai.push(fakes.event_ask())

    response = answer(client, state)

    assert response.status_code == 200
    assert response.json()["question_count"] == 2
    assert SUMMARY_INSTRUCTION not in ai.calls[-1]["messages"][0]["content"]


def test_ai_asking_at_answer_limit_is_invalid(client, ai, store, user_id):
    state = make_state(store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=2)
    ai.push(fakes.event_ask())

    response = answer(client, state)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_OUTPUT_INVALID"
    assert state.question_count == 2
    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    assert state.ai_question == "架空の質問"


def test_answer_after_summary_at_limit_is_conflict(client, ai, store, user_id):
    # ST-02
    state = make_state(store, user_id, ConsultationStatus.EVENT_SUMMARY_READY, question_count=3)

    assert_conflict(answer(client, state))
    assert state.question_count == 3
    assert ai.calls == []


def test_answer_over_limit_in_event_dialogue_is_conflict(client, ai, store, user_id):
    # 通常は要約へ進んでいるため起こらないが、上限を超えた回答はAIを呼ばずに拒否する
    state = make_state(store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=3)

    assert_conflict(answer(client, state))
    assert state.question_count == 3
    assert ai.calls == []


def test_ask_more_after_answer_limit_is_conflict(client, ai, store, user_id):
    # ST-03
    state = make_state(store, user_id, ConsultationStatus.EVENT_SUMMARY_READY, question_count=3)

    assert_conflict(ask_more(client, state))
    assert state.status is ConsultationStatus.EVENT_SUMMARY_READY
    assert ai.calls == []


# --- 訂正（上限2回） ---------------------------------------------------------------


def test_correction_reaching_limit_moves_to_summary(client, ai, store, user_id):
    # ST-04
    state = make_state(
        store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=1, correction_count=1
    )
    ai.push(fakes.event_summarize())

    response = correct(client, state)

    assert response.status_code == 200
    assert response.json() == {
        "status": "event_summary_ready",
        "question_count": 1,
        "can_ask_more": False,
        "event_details": {"what_happened": "架空の出来事", "what_bothered_me": "架空の気がかり"},
        "correction_count": 2,
        "correction_limit_reached": True,
    }
    assert SUMMARY_INSTRUCTION in ai.calls[-1]["messages"][0]["content"]


def test_ai_asking_at_correction_limit_is_invalid(client, ai, store, user_id):
    state = make_state(
        store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=1, correction_count=1
    )
    ai.push(fakes.event_ask())

    response = correct(client, state)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_OUTPUT_INVALID"
    assert state.correction_count == 1
    assert state.status is ConsultationStatus.EVENT_DIALOGUE


def test_correction_after_limit_is_conflict(client, ai, store, user_id):
    # ST-05
    state = make_state(
        store, user_id, ConsultationStatus.EVENT_SUMMARY_READY, question_count=1, correction_count=2
    )

    assert_conflict(correct(client, state))
    assert state.correction_count == 2
    assert state.status is ConsultationStatus.EVENT_SUMMARY_READY
    assert ai.calls == []


def test_correction_over_limit_in_event_dialogue_is_conflict(client, ai, store, user_id):
    state = make_state(
        store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=1, correction_count=2
    )

    assert_conflict(correct(client, state))
    assert state.correction_count == 2
    assert ai.calls == []


def test_ask_more_after_correction_limit_is_conflict_but_proceed_works(client, ai, store, user_id):
    # ST-06
    state = make_state(
        store, user_id, ConsultationStatus.EVENT_SUMMARY_READY, question_count=1, correction_count=2
    )

    assert_conflict(ask_more(client, state))
    assert state.status is ConsultationStatus.EVENT_SUMMARY_READY

    response = client.post(
        f"{BASE}/{state.consultation_id}/event-summary/confirm",
        json={
            "action": "proceed",
            "event_details": {"what_happened": "架空の編集後", "what_bothered_me": "架空の気がかり"},
        },
    )
    assert response.json() == {"status": "emotion_selection"}
    assert ai.calls == []


# --- 本音・背景・望み（3往復。Q-33） ------------------------------------------------


def test_guided_dialogue_after_result_ready_is_conflict(client, ai, store, user_id):
    # ST-15
    result = ConsultationResultDraft(
        event_summary="架空の出来事",
        emotion="架空の感情",
        true_feeling="架空の本音",
        background="",
        wish="架空の望み",
    )
    state = make_state(
        store, user_id, ConsultationStatus.RESULT_READY, guided_turn_count=3, result=result
    )

    response = client.post(
        f"{BASE}/{state.consultation_id}/guided-dialogue", json={"answer": "架空の回答"}
    )

    assert_conflict(response)
    assert state.result == result
    assert ai.calls == []


# --- 同時リクエストでも上限を超えない -----------------------------------------------


async def test_concurrent_answers_at_limit_count_only_once(app, ai, store, user_id):
    state = make_state(store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=2)
    ai.wait_event = asyncio.Event()
    ai.push(fakes.event_summarize(), fakes.event_summarize())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        url = f"{BASE}/{state.consultation_id}/event-dialogue"
        body = {"action": "answer", "answer": "架空の回答"}
        first = asyncio.create_task(client.post(url, json=body))
        await ai.started.wait()

        second = await client.post(url, json=body)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONSULTATION_BUSY"

        ai.wait_event.set()
        assert (await first).status_code == 200

        # 1件目が終わった後の送り直しは、上限を超えるため409
        third = await client.post(url, json=body)
        assert third.status_code == 409

    assert state.question_count == 3
    assert len(ai.calls) == 1


# --- 1回の相談でAIを呼ぶ回数の上限 --------------------------------------------------


async def test_successful_ai_calls_are_at_most_twelve(store, ai, user_id):
    """追加質問を最も多く使う進め方でも、成功したAI呼び出しは12回で整理結果まで進む"""
    from app.features.consultations.schemas import EmotionInput

    service = ConsultationService(store, ai)
    ai.push(fakes.first_question())
    state = await service.start(user_id, ThemeCategory.COMMUNICATION, "架空の相談本文")
    cid = state.consultation_id

    # 回答1・訂正1・回答2で要約へ進み、そのたびに追加質問を選ぶ
    for action in ("answer", "correct", "answer"):
        ai.push(fakes.event_summarize())
        await service.event_dialogue(user_id, cid, action, "架空の入力")
        assert state.status is ConsultationStatus.EVENT_SUMMARY_READY
        ai.push(fakes.event_ask())
        await service.confirm_event_summary(user_id, cid, "ask_more")

    # 回答3で上限に達し、要約へ進む。追加質問・訂正はもう選べない
    ai.push(fakes.event_summarize())
    await service.event_dialogue(user_id, cid, "answer", "架空の入力")
    assert (state.question_count, state.correction_count) == (3, 1)
    await service.confirm_event_summary(user_id, cid, "proceed")

    ai.push(fakes.emotion_output())
    await service.submit_emotion(user_id, cid, EmotionInput(category="sad", cannot_verbalize=True))
    ai.push(fakes.guided_ask(), fakes.guided_ask(), fakes.guided_complete())
    for _ in range(3):
        await service.guided_dialogue(user_id, cid, "架空の回答", skipped=False)

    assert state.status is ConsultationStatus.RESULT_READY
    assert len(ai.calls) == 12
