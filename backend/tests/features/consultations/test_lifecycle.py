"""一時状態の巻き戻し・保持時間・破棄のテスト（I-03B）。テストデータはすべて架空。

AIは FakeAIClient で模し、外部APIへは接続しない。
"""

import logging
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.consultations.router import get_current_user_id, router
from app.features.consultations.state import ConsultationState
from app.features.consultations.store import ConsultationStore, get_consultation_store
from app.integrations.openrouter.client import get_ai_client

from tests.features.consultations import fakes

BASE = "/api/v1/consultations"
MARKER = "PORORI_TEST_MARKER_ST-19"


@pytest.fixture
def ai():
    return fakes.FakeAIClient()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def client(ai, user_id):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    store = ConsultationStore()
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    # 想定外のエラーを、例外ではなく500のレスポンスとして受け取る
    return TestClient(app, raise_server_exceptions=False)


def _start(client, ai):
    ai.push(fakes.first_question())
    response = client.post(BASE, json={"theme": "communication", "detail": "架空の相談本文"})
    assert response.status_code == 201
    return response.json()["consultation_id"]


def _advance_to_background(client, ai, cid):
    """current_topic=background（本音に回答済み）まで進める"""
    ai.push(fakes.event_summarize())
    client.post(f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空の回答"})
    client.post(f"{BASE}/{cid}/event-summary/confirm", json={"action": "proceed"})
    ai.push(fakes.emotion_output())
    client.post(f"{BASE}/{cid}/emotion", json={"category": "sad", "cannot_verbalize": True})
    ai.push(fakes.guided_ask(question="架空の背景の質問"))
    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の本音"})
    assert response.json()["current_topic"] == "background"


def _fail_after_update(monkeypatch):
    """状態を書き換えた後（最終操作時刻の更新時）に、想定外の例外を起こす"""

    def failing_touch(self):
        raise RuntimeError("想定外のエラー")

    monkeypatch.setattr(ConsultationState, "touch", failing_touch)


# --- ST-19：想定外の内部エラーでも相談の状態が進まない ---------------------------


def test_internal_error_in_event_dialogue_does_not_advance_state(
    client, ai, monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)
    cid = _start(client, ai)
    ai.push(fakes.event_ask(question="架空の質問1"))
    client.post(f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空の回答1"})
    before = client.get(f"{BASE}/{cid}").json()
    assert before["question_count"] == 1

    _fail_after_update(monkeypatch)
    ai.push(fakes.event_ask(understanding=f"{MARKER}_aiunderstanding", question=f"{MARKER}_aiquestion"))
    response = client.post(
        f"{BASE}/{cid}/event-dialogue",
        json={"action": "answer", "answer": f"架空の回答 {MARKER}_answer"},
    )

    assert response.status_code == 500
    assert MARKER not in response.text
    # 送信前の状態（直近の質問・回数）へ戻っている
    assert client.get(f"{BASE}/{cid}").json() == before

    # 同じ回答を送り直せる
    monkeypatch.undo()
    ai.push(fakes.event_ask(question="架空の質問2"))
    response = client.post(
        f"{BASE}/{cid}/event-dialogue",
        json={"action": "answer", "answer": f"架空の回答 {MARKER}_answer"},
    )
    assert response.status_code == 200
    assert response.json()["question_count"] == 2
    assert MARKER not in caplog.text


def test_internal_error_in_guided_dialogue_does_not_advance_state(
    client, ai, monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)
    cid = _start(client, ai)
    _advance_to_background(client, ai, cid)
    before = client.get(f"{BASE}/{cid}").json()

    _fail_after_update(monkeypatch)
    ai.push(fakes.guided_ask(question=f"{MARKER}_aiquestion"))
    response = client.post(
        f"{BASE}/{cid}/guided-dialogue", json={"answer": f"架空の背景 {MARKER}_answer"}
    )

    assert response.status_code == 500
    assert MARKER not in response.text
    after = client.get(f"{BASE}/{cid}").json()
    assert after == before
    assert after["current_topic"] == "background"
    assert after["ai_question"] == "架空の背景の質問"

    monkeypatch.undo()
    ai.push(fakes.guided_ask(question="架空の望みの質問"))
    response = client.post(
        f"{BASE}/{cid}/guided-dialogue", json={"answer": f"架空の背景 {MARKER}_answer"}
    )
    assert response.status_code == 200
    assert response.json()["current_topic"] == "wish"
    assert MARKER not in caplog.text
