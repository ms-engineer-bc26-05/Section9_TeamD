"""一時状態の巻き戻し・保持時間・破棄のテスト（I-03B）。テストデータはすべて架空。

AIは FakeAIClient で模し、外部APIへは接続しない。
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.consultations import state as state_module
from app.features.consultations.router import get_current_user_id, router
from app.features.consultations.schemas import (
    ConsultationResultDraft,
    ConsultationStatus,
    ThemeCategory,
)
from app.features.consultations.service import ConsultationService
from app.features.consultations.state import ConsultationState, DialogueTurn
from app.features.consultations.store import (
    CONSULTATION_TTL,
    ConsultationNotFound,
    ConsultationStore,
    get_consultation_store,
)
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
def store():
    return ConsultationStore()


@pytest.fixture
def client(ai, user_id, store):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
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


# --- 保持時間（TTL）：最後に更新が成功してから30分 ---------------------------------


class FakeClock:
    """テスト用の時計。advance() で時刻を進める"""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(state_module, "utc_now", clock)
    return clock


def make_state(store, user_id, status=ConsultationStatus.EVENT_DIALOGUE, **fields):
    state = ConsultationState(
        consultation_id=uuid4(),
        user_id=user_id,
        theme=ThemeCategory.COMMUNICATION,
        status=status,
        **fields,
    )
    state.messages.append(DialogueTurn(role="user", content=f"架空の相談本文 {MARKER}_history"))
    state.ai_question = "架空の質問"
    store.add(state)
    return state


def test_ttl_is_thirty_minutes():
    assert CONSULTATION_TTL == timedelta(minutes=30)


def test_state_is_kept_until_just_before_ttl(client, store, user_id, clock):
    state = make_state(store, user_id)
    clock.advance(minutes=29, seconds=59)

    assert client.get(f"{BASE}/{state.consultation_id}").status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "", None),
        ("post", "/event-dialogue", {"action": "answer", "answer": "架空の回答"}),
        ("post", "/emotion", {"category": "sad", "cannot_verbalize": True}),
        ("post", "/guided-dialogue", {"answer": "架空の回答"}),
        ("get", "/result", None),
        ("patch", "/result", {"wish": "架空の望み"}),
        ("post", "/result/approve", None),
        ("post", "/handling", {"handling": "hold"}),
    ],
)
def test_expired_state_returns_same_404_as_missing(
    client, ai, store, user_id, clock, caplog, method, path, payload
):
    # ST-17（保持時間の経過）
    caplog.set_level(logging.DEBUG)
    state = make_state(store, user_id)
    clock.advance(minutes=30)
    kwargs = {"json": payload} if payload is not None else {}

    expired = getattr(client, method)(f"{BASE}/{state.consultation_id}{path}", **kwargs)
    missing = getattr(client, method)(f"{BASE}/{uuid4()}{path}", **kwargs)

    assert expired.status_code == missing.status_code == 404
    assert expired.json() == missing.json()
    assert MARKER not in expired.text
    assert MARKER not in caplog.text
    assert ai.calls == []
    # 期限切れの一時状態は消える
    assert state.consultation_id not in store._states


def test_lost_state_after_restart_returns_404(client, user_id, ai):
    # ST-17（APIプロセスの再起動を想定し、一時状態が空の場合）
    response = client.post(
        f"{BASE}/{uuid4()}/event-dialogue", json={"action": "answer", "answer": "架空の回答"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONSULTATION_NOT_FOUND"
    assert ai.calls == []


def test_get_does_not_extend_ttl(client, store, user_id, clock):
    state = make_state(store, user_id)
    clock.advance(minutes=20)
    assert client.get(f"{BASE}/{state.consultation_id}").status_code == 200

    clock.advance(minutes=10)
    assert client.get(f"{BASE}/{state.consultation_id}").status_code == 404


def test_successful_update_extends_ttl(client, ai, store, user_id, clock):
    state = make_state(store, user_id)
    clock.advance(minutes=20)
    ai.push(fakes.event_ask())
    response = client.post(
        f"{BASE}/{state.consultation_id}/event-dialogue",
        json={"action": "answer", "answer": "架空の回答"},
    )
    assert response.status_code == 200

    clock.advance(minutes=29)
    assert client.get(f"{BASE}/{state.consultation_id}").status_code == 200
    clock.advance(minutes=1)
    assert client.get(f"{BASE}/{state.consultation_id}").status_code == 404


def test_failed_update_does_not_extend_ttl(client, ai, store, user_id, clock):
    state = make_state(store, user_id)
    clock.advance(minutes=20)
    ai.push({"kind": "normal"})  # 不正な出力（502）
    response = client.post(
        f"{BASE}/{state.consultation_id}/event-dialogue",
        json={"action": "answer", "answer": "架空の回答"},
    )
    assert response.status_code == 502

    clock.advance(minutes=10)
    assert client.get(f"{BASE}/{state.consultation_id}").status_code == 404


def test_new_consultation_purges_expired_states_of_all_users(client, ai, store, user_id, clock):
    others = [make_state(store, uuid4()) for _ in range(2)]
    clock.advance(minutes=30)
    fresh = make_state(store, uuid4())  # 登録時に、期限切れの2件が消える

    assert set(store._states) == {fresh.consultation_id}
    assert all(s.consultation_id not in store._states for s in others)


async def test_state_waiting_for_ai_does_not_expire(store, ai, user_id, clock):
    # AIの応答待ちでロック中の相談は、期限切れとして扱わない
    state = make_state(store, user_id)
    clock.advance(minutes=29)
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(fakes.event_ask())
    waiting = asyncio.create_task(
        service.event_dialogue(user_id, state.consultation_id, "answer", "架空の回答")
    )
    await ai.started.wait()

    clock.advance(minutes=5)
    store.purge_expired()
    assert state.consultation_id in store._states

    ai.wait_event.set()
    await waiting
    assert state.question_count == 1
    assert state.updated_at == clock.now  # 成功したので時刻が更新される


async def test_approved_result_is_not_returned_after_ttl(store, user_id, clock):
    # I-05へ公開する関数も、期限切れの相談は404として扱う
    from app.features.consultations.public import get_approved_result

    from tests.features.consultations.factories import make_save_confirmation_state

    state = make_save_confirmation_state(store, user_id)
    clock.advance(minutes=30)

    with pytest.raises(ConsultationNotFound):
        await get_approved_result(user_id, state.consultation_id, store=store)


def test_result_draft_is_not_kept_after_ttl(client, store, user_id, clock):
    result = ConsultationResultDraft(
        event_summary="架空の出来事",
        emotion="架空の感情",
        true_feeling="架空の本音",
        background="",
        wish=f"架空の望み {MARKER}_result",
    )
    state = make_state(store, user_id, ConsultationStatus.RESULT_READY, result=result)
    clock.advance(hours=1)

    response = client.get(f"{BASE}/{state.consultation_id}/result")
    assert response.status_code == 404
    assert MARKER not in response.text
