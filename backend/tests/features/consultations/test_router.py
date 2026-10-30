"""相談APIのテスト。

main.py への登録は結合Issue（I-06）で行うため、相談Routerだけを載せたテスト用アプリを使う。
認証は dependency_overrides で固定UUIDのユーザーにし、AIは FakeAIClient で模す（外部APIへ接続しない）。
"""

import asyncio
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.auth.schemas import CurrentUser
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


@pytest.mark.asyncio
async def test_current_user_id_uses_internal_user_id():
    current_user = CurrentUser(user_id=USER)

    assert await get_current_user_id(current_user) == USER


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
        "current_topic": "true_feeling",
    }

    # 本音・背景・望み
    ai.push(fakes.guided_ask())
    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の本音"})
    assert response.json() == {
        "status": "guided_dialogue",
        "ai_question": "架空の背景の質問",
        "current_topic": "background",
    }

    ai.push(fakes.guided_ask(question="架空の望みの質問"))
    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"skipped": True})
    assert response.json()["current_topic"] == "wish"

    # 応答を受け取れなかった場合も、GETで直近の質問と項目を取得できる
    response = client.get(f"{BASE}/{cid}")
    assert response.json()["ai_question"] == "架空の望みの質問"
    assert response.json()["current_topic"] == "wish"

    ai.push(fakes.guided_complete())
    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の望み"})
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


def test_skip_outside_background_returns_422(client, ai):
    cid = start(client, ai)
    ai.push(fakes.event_summarize())
    client.post(f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空"})
    client.post(f"{BASE}/{cid}/event-summary/confirm", json={"action": "proceed"})
    ai.push(fakes.emotion_output())
    client.post(f"{BASE}/{cid}/emotion", json={"category": "sad", "cannot_verbalize": True})

    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"skipped": True})
    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"field": "skipped", "reason": "この質問では選択できません。"}
    ]


def test_patch_result_rejects_approved_and_empty(client, ai):
    cid = start(client, ai)
    assert client.patch(f"{BASE}/{cid}/result", json={"approved": True}).status_code == 422
    assert client.patch(f"{BASE}/{cid}/result", json={}).status_code == 422


def test_wrong_state_returns_409(client, ai):
    cid = start(client, ai)
    response = client.post(f"{BASE}/{cid}/result/approve")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSULTATION_STATE_CONFLICT"


def test_result_before_ready_returns_result_not_ready(client, ai):
    cid = start(client, ai)
    response = client.get(f"{BASE}/{cid}/result")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESULT_NOT_READY"


def test_result_in_safety_guidance_returns_state_conflict(client, ai):
    ai.push(fakes.safety_output(ai_question=None))
    cid = client.post(BASE, json={"theme": "other", "detail": "架空の相談本文"}).json()[
        "consultation_id"
    ]
    response = client.get(f"{BASE}/{cid}/result")

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
    # 認証依存を差し替えない場合は、Bearerトークンがないため401
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_ai_client] = lambda: ai
    response = TestClient(app).post(BASE, json={"theme": "other", "detail": "架空の相談本文"})

    assert response.status_code == 401
    assert ai.calls == []


# --- I-04の画面実装が依存する契約（PRレビューでの追加） ----------------------------


def advance_to_result_ready(client, ai):
    cid = start(client, ai)
    ai.push(fakes.event_summarize())
    client.post(f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空"})
    client.post(f"{BASE}/{cid}/event-summary/confirm", json={"action": "proceed"})
    ai.push(fakes.emotion_output())
    client.post(f"{BASE}/{cid}/emotion", json={"category": "sad", "cannot_verbalize": True})
    ai.push(fakes.guided_ask(), fakes.guided_ask())
    client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の本音"})
    client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の背景"})
    ai.push(fakes.guided_complete(background="架空の背景のまとめ"))
    response = client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の望み"})
    assert response.json() == {"status": "result_ready"}
    return cid


def test_result_is_available_after_approval(client, ai):
    cid = advance_to_result_ready(client, ai)

    response = client.post(f"{BASE}/{cid}/result/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "handling_selection"
    response = client.get(f"{BASE}/{cid}/result")  # handling_selection
    assert response.status_code == 200
    assert response.json()["approved"] is True

    # 扱い方の選択が成功し、save_confirmation へ進んだことも確認する
    response = client.post(f"{BASE}/{cid}/handling", json={"handling": "tell"})
    assert response.status_code == 200
    assert response.json() == {"status": "save_confirmation"}
    response = client.get(f"{BASE}/{cid}/result")  # save_confirmation
    assert response.status_code == 200
    assert response.json()["approved"] is True


def test_patch_background_to_empty_returns_whole_result(client, ai):
    cid = advance_to_result_ready(client, ai)

    response = client.patch(f"{BASE}/{cid}/result", json={"background": ""})
    assert response.status_code == 200
    assert response.json() == {
        "event_summary": "架空の出来事",
        "emotion": "架空の感情",
        "true_feeling": "架空の本音",
        "background": "",
        "wish": "架空の望み",
        "approved": False,
    }


@pytest.mark.asyncio
async def test_concurrent_request_returns_409_busy(ai, current_user):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    store = ConsultationStore()
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: current_user["id"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ai.push(fakes.first_question())
        response = await client.post(BASE, json={"theme": "other", "detail": "架空の相談本文"})
        cid = response.json()["consultation_id"]

        # 1件目はAIの応答待ちで止めておく
        ai.wait_event = asyncio.Event()
        ai.started.clear()
        ai.push(fakes.event_ask())
        first = asyncio.create_task(
            client.post(
                f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空の回答1"}
            )
        )
        await ai.started.wait()

        second = await client.post(
            f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空の回答2"}
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONSULTATION_BUSY"
        assert "架空" not in second.text

        ai.wait_event.set()
        response = await first
        assert response.status_code == 200
        assert response.json()["question_count"] == 1
