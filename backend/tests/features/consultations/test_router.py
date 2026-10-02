"""相談APIのテスト。

main.py への登録は結合Issue（I-06）で行うため、相談Routerだけを載せたテスト用アプリを使う。
認証は dependency_overrides で固定UUIDのユーザーにし、AIは FakeAIClient で模す（外部APIへ接続しない）。
"""

import logging
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.consultations.router import get_current_user_id, router
from app.features.consultations.store import ConsultationStore, get_consultation_store
from app.integrations.openrouter.client import AIClientError, get_ai_client

from tests.features.consultations import fakes

BASE = "/api/v1/consultations"
USER = uuid4()


@pytest.fixture
def ai():
    return fakes.FakeAIClient()


@pytest.fixture
def current_user():
    return {"id": USER}


@pytest.fixture
def client(ai, current_user):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    store = ConsultationStore()
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]
    return TestClient(app)


def start(client, ai):
    ai.push(fakes.first_question())
    response = client.post(BASE, json={"theme": "communication", "detail": "架空の相談本文"})
    assert response.status_code == 201
    return response.json()["consultation_id"]


def test_full_normal_flow(client, ai):
    # 相談開始
    ai.push(fakes.first_question())
    response = client.post(BASE, json={"theme": "communication", "detail": "架空の相談本文"})
    assert response.status_code == 201
    body = response.json()
    cid = body["consultation_id"]
    assert body == {
        "consultation_id": cid,
        "status": "event_dialogue",
        "ai_question": "架空の最初の質問",
    }

    # 出来事：回答
    ai.push(fakes.event_ask())
    response = client.post(
        f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空の回答"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "status": "event_dialogue",
        "question_count": 1,
        "ai_understanding": "架空の理解",
        "ai_question": "架空の次の質問",
        "correction_count": 0,
        "correction_limit_reached": False,
    }

    # 出来事：訂正
    ai.push(fakes.event_ask(understanding="架空の訂正後の理解"))
    response = client.post(
        f"{BASE}/{cid}/event-dialogue",
        json={"action": "correct", "correction_input": "架空の訂正"},
    )
    assert response.json()["correction_count"] == 1
    assert response.json()["ai_understanding"] == "架空の訂正後の理解"

    # 出来事：要約完成
    ai.push(fakes.event_summarize())
    response = client.post(
        f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空の回答2"}
    )
    assert response.json() == {
        "status": "event_summary_ready",
        "question_count": 2,
        "can_ask_more": True,
        "event_details": {"what_happened": "架空の出来事", "what_bothered_me": "架空の気がかり"},
        "correction_count": 1,
        "correction_limit_reached": False,
    }

    # 状態取得（GET）
    response = client.get(f"{BASE}/{cid}")
    assert response.status_code == 200
    assert response.json()["status"] == "event_summary_ready"
    assert response.json()["consultation_id"] == cid

    # 要約確認
    response = client.post(f"{BASE}/{cid}/event-summary/confirm", json={"action": "proceed"})
    assert response.json() == {"status": "emotion_selection"}

    # 感情
    ai.push(fakes.emotion_output())
    response = client.post(
        f"{BASE}/{cid}/emotion", json={"category": "anxious", "detail": "架空の具体化"}
    )
    assert response.json() == {
        "status": "guided_dialogue",
        "ai_response": "架空の受け止め",
        "ai_question": "架空の本音の質問",
    }

    # 本音・背景・望み
    ai.push(fakes.guided_ask())
    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の本音"})
    assert response.json() == {"status": "guided_dialogue", "ai_question": "架空の背景の質問"}

    ai.push(fakes.guided_complete())
    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"skipped": True})
    assert response.json() == {"status": "result_ready"}

    # 整理結果の取得・編集・承認
    response = client.get(f"{BASE}/{cid}/result")
    assert response.json()["approved"] is False
    assert response.json()["background"] == ""

    response = client.patch(f"{BASE}/{cid}/result", json={"wish": "架空の編集した望み"})
    assert response.status_code == 200
    assert response.json()["wish"] == "架空の編集した望み"

    response = client.post(f"{BASE}/{cid}/result/approve")
    assert response.json() == {"status": "handling_selection", "approved": True}

    # 扱い方
    response = client.post(f"{BASE}/{cid}/handling", json={"handling": "hold"})
    assert response.json() == {"status": "save_confirmation"}
    response = client.get(f"{BASE}/{cid}")
    assert response.json() == {"consultation_id": cid, "status": "save_confirmation", "handling": "hold"}


def test_safety_on_start(client, ai):
    ai.push(fakes.safety_output(ai_question=None))
    response = client.post(BASE, json={"theme": "other", "detail": "架空の相談本文"})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "safety_guidance"
    assert body["safety_guidance"]["risk_detected"] is True
    assert "架空" not in response.text  # AIの生成文を返さない


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("event-dialogue", {"action": "answer"}),  # answerがない
        ("event-dialogue", {"action": "answer", "answer": "架空", "correction_input": "架空"}),
        ("event-dialogue", {"action": "answer", "answer": "架空", "question_count": 0}),
        ("guided-dialogue", {"answer": "架空", "skipped": True}),
        ("guided-dialogue", {}),
        ("emotion", {"category": "anxious"}),
    ],
)
def test_invalid_request_returns_422_without_input(client, ai, path, payload):
    cid = start(client, ai)
    response = client.post(f"{BASE}/{cid}/{path}", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "架空" not in response.text


def test_patch_result_rejects_approved_and_empty(client, ai):
    cid = start(client, ai)
    assert client.patch(f"{BASE}/{cid}/result", json={"approved": True}).status_code == 422
    assert client.patch(f"{BASE}/{cid}/result", json={}).status_code == 422


def test_wrong_state_returns_409(client, ai):
    cid = start(client, ai)
    response = client.post(f"{BASE}/{cid}/result/approve")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSULTATION_STATE_CONFLICT"


def test_other_user_and_missing_return_same_404(client, ai, current_user):
    cid = start(client, ai)
    current_user["id"] = uuid4()

    other = client.get(f"{BASE}/{cid}")
    missing = client.get(f"{BASE}/{uuid4()}")
    assert other.status_code == missing.status_code == 404
    assert other.json() == missing.json()


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (AIClientError("失敗"), "AI_UNAVAILABLE"),
        ({"kind": "normal", "ai_question": "架空の不正な出力"}, "AI_OUTPUT_INVALID"),
    ],
)
def test_ai_failure_returns_502_without_content(client, ai, caplog, failure, code):
    caplog.set_level(logging.INFO)
    ai.push(failure)
    response = client.post(BASE, json={"theme": "other", "detail": "架空の相談本文"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == code
    assert "架空" not in response.text
    assert "架空" not in caplog.text


def test_requires_authentication(ai):
    # 認証依存を差し替えない場合は、I-01へ置き換えるまで常に401
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ai_client] = lambda: ai
    response = TestClient(app).post(BASE, json={"theme": "other", "detail": "架空の相談本文"})

    assert response.status_code == 401
    assert ai.calls == []
