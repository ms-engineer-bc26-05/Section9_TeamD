"""一時状態の巻き戻し・保持時間・破棄のテスト（I-03B）。テストデータはすべて架空。

AIは FakeAIClient で模し、外部APIへは接続しない。
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import (
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    register_exception_handlers,
)
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
    ConsultationBusy,
    ConsultationNotFound,
    ConsultationStore,
    get_consultation_store,
)
from app.integrations.openrouter.client import AIClientError, get_ai_client

from tests.features.consultations import fakes

BASE = "/api/v1/consultations"
MARKER = "PORORI_TEST_MARKER_ST-19"
INTERNAL_ERROR_BODY = {"error": {"code": INTERNAL_ERROR_CODE, "message": INTERNAL_ERROR_MESSAGE}}


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
    # 想定外のエラーも、共通のエラー形式で返る（#86）
    assert response.json() == INTERNAL_ERROR_BODY
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
    # 想定外のエラーも、共通のエラー形式で返る（#86）
    assert response.json() == INTERNAL_ERROR_BODY
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


def _st19_state(store, user_id, status):
    """ST-19の前提の一時状態を、テスト設計書3.4に従って直接用意する"""
    from app.features.consultations.schemas import (
        ApprovableResult,
        ConsultationResultDraft,
        EventDetailsDraft,
    )

    result = {
        "event_summary": "架空の出来事",
        "emotion": "架空の感情",
        "true_feeling": "架空の本音",
        "background": "",
        "wish": "架空の望み",
    }
    state = ConsultationState(
        consultation_id=uuid4(),
        user_id=user_id,
        theme=ThemeCategory.COMMUNICATION,
        status=status,
        question_count=1,
    )
    state.messages.append(DialogueTurn(role="user", content="架空の相談本文"))
    state.event_details = EventDetailsDraft(
        what_happened="架空の出来事", what_bothered_me="架空の気がかり"
    )
    if status in (ConsultationStatus.RESULT_READY, ConsultationStatus.HANDLING_SELECTION):
        state.result = ConsultationResultDraft(**result)
    if status is ConsultationStatus.HANDLING_SELECTION:
        state.approved_result = ApprovableResult(**result)
        state.approved_at = datetime(2026, 10, 1, tzinfo=UTC)
    store.add(state)
    return state


def _st19_fields(state):
    """巻き戻しの確認に使う項目（相談内容を含むため、テストの中だけで比べる）"""
    return (
        state.status,
        state.question_count,
        state.correction_count,
        state.ai_question,
        state.ai_understanding,
        state.event_details,
        state.emotion,
        state.guided_turn_count,
        state.result,
        state.edited_result_fields.copy(),
        state.approved_result,
        state.approved_at,
        state.handling,
        len(state.messages),
        state.updated_at,
    )


@pytest.mark.parametrize(
    ("status", "method", "path", "payload", "ai_output"),
    [
        (
            ConsultationStatus.EMOTION_SELECTION,
            "post",
            "/emotion",
            {"category": "sad", "detail": f"架空の具体化 {MARKER}_emotion"},
            fakes.emotion_output(),
        ),
        (
            ConsultationStatus.EVENT_SUMMARY_READY,
            "post",
            "/event-summary/confirm",
            {
                "action": "proceed",
                "event_details": {
                    "what_happened": f"架空の編集 {MARKER}_summary",
                    "what_bothered_me": "架空の気がかり",
                },
            },
            None,
        ),
        (
            ConsultationStatus.EVENT_SUMMARY_READY,
            "post",
            "/event-summary/confirm",
            {"action": "ask_more"},
            fakes.event_ask(question=f"{MARKER}_aiquestion"),
        ),
        (
            ConsultationStatus.RESULT_READY,
            "patch",
            "/result",
            {"wish": f"架空の編集した望み {MARKER}_wish"},
            None,
        ),
        (ConsultationStatus.RESULT_READY, "post", "/result/approve", None, None),
        (ConsultationStatus.HANDLING_SELECTION, "post", "/handling", {"handling": "tell"}, None),
    ],
)
def test_internal_error_in_other_updates_does_not_advance_state(
    client, ai, store, user_id, monkeypatch, caplog, status, method, path, payload, ai_output
):
    # ST-19をほかの更新系APIにも広げる（PRレビュー：るなさん）
    caplog.set_level(logging.DEBUG)
    state = _st19_state(store, user_id, status)
    if ai_output is not None:
        ai.push(ai_output)
    before = _st19_fields(state)
    before_view = client.get(f"{BASE}/{state.consultation_id}").json()

    _fail_after_update(monkeypatch)
    kwargs = {"json": payload} if payload is not None else {}
    response = getattr(client, method)(f"{BASE}/{state.consultation_id}{path}", **kwargs)

    assert response.status_code == 500
    # 想定外のエラーも、共通のエラー形式で返る（#86）
    assert response.json() == INTERNAL_ERROR_BODY
    assert MARKER not in response.text
    assert MARKER not in caplog.text
    assert _st19_fields(state) == before
    assert client.get(f"{BASE}/{state.consultation_id}").json() == before_view

    # 同じ操作を送り直せる
    monkeypatch.undo()
    if ai_output is not None:
        ai.push(ai_output)
    response = getattr(client, method)(f"{BASE}/{state.consultation_id}{path}", **kwargs)
    assert response.status_code == 200


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


# --- DELETE /consultations/{id}：中断・保存せず終了（冪等な204） -------------------


def _ops():
    return [
        ("get", "", None),
        ("post", "/event-dialogue", {"action": "answer", "answer": "架空の回答"}),
        ("get", "/result", None),
        ("post", "/handling", {"handling": "hold"}),
    ]


@pytest.mark.parametrize("status", [s for s in ConsultationStatus])
def test_delete_discards_own_consultation_in_any_status(
    client, store, user_id, caplog, status
):
    # N-18・N-19・ST-13（安全案内からの終了）
    caplog.set_level(logging.DEBUG)
    state = make_state(store, user_id, status)

    response = client.delete(f"{BASE}/{state.consultation_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"{BASE}/{state.consultation_id}").status_code == 404
    # 相談内容が残らない（NP-07・NP-08）
    # 一時状態が残っていない（repr は相談内容を表示しないため、登録の有無で確認する）
    assert state.consultation_id not in store._states
    assert MARKER not in caplog.text


@pytest.mark.parametrize(("method", "path", "payload"), _ops())
def test_deleted_consultation_returns_same_404_as_missing(
    client, ai, store, user_id, method, path, payload
):
    # ST-14
    state = make_state(store, user_id)
    client.delete(f"{BASE}/{state.consultation_id}")
    kwargs = {"json": payload} if payload is not None else {}

    deleted = getattr(client, method)(f"{BASE}/{state.consultation_id}{path}", **kwargs)
    missing = getattr(client, method)(f"{BASE}/{uuid4()}{path}", **kwargs)

    assert deleted.status_code == missing.status_code == 404
    assert deleted.json() == missing.json()
    assert ai.calls == []


def test_delete_is_idempotent(client, store, user_id):
    # ST-14：同じIDで何度呼んでも204
    state = make_state(store, user_id)

    assert client.delete(f"{BASE}/{state.consultation_id}").status_code == 204
    assert client.delete(f"{BASE}/{state.consultation_id}").status_code == 204
    assert client.delete(f"{BASE}/{uuid4()}").status_code == 204


def test_delete_does_not_discard_other_users_consultation(client, store, user_id):
    # AU-12：204を返すが、他人の一時状態は破棄しない
    other = make_state(store, uuid4())

    response = client.delete(f"{BASE}/{other.consultation_id}")

    assert response.status_code == 204
    assert other.consultation_id in store._states


def test_delete_after_ttl_returns_204(client, store, user_id, clock):
    state = make_state(store, user_id)
    clock.advance(minutes=30)

    assert client.delete(f"{BASE}/{state.consultation_id}").status_code == 204


def test_delete_requires_authentication(ai):
    # 認証依存を差し替えない場合は、I-01へ置き換えるまで常に401
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).delete(f"{BASE}/{uuid4()}")

    assert response.status_code == 401


# --- 新しい相談を始めたら、同じユーザーの既存の相談を破棄する（1ユーザー1件） ------


def _start_new(client, ai, detail="架空の新しい相談本文"):
    ai.push(fakes.first_question())
    return client.post(BASE, json={"theme": "other", "detail": detail})


def test_new_consultation_replaces_existing_one(client, ai, store, user_id):
    old = make_state(store, user_id)
    others = make_state(store, uuid4())  # 別のユーザーの相談

    response = _start_new(client, ai)

    assert response.status_code == 201
    new_id = response.json()["consultation_id"]
    # 古い相談は404になり、新しい相談だけが残る
    assert client.get(f"{BASE}/{old.consultation_id}").status_code == 404
    assert client.get(f"{BASE}/{new_id}").status_code == 200
    user_states = [s for s in store._states.values() if s.user_id == user_id]
    assert len(user_states) == 1
    # 別のユーザーの相談は残る
    assert others.consultation_id in store._states


def test_lost_consultation_id_does_not_block_new_consultation(client, ai, store, user_id):
    # フロントが相談IDを失い、APIに一時状態だけが残っている場合でも、新しい相談を始められる
    make_state(store, user_id, ConsultationStatus.GUIDED_DIALOGUE)

    response = _start_new(client, ai)

    assert response.status_code == 201
    assert len([s for s in store._states.values() if s.user_id == user_id]) == 1


@pytest.mark.parametrize("failure", [AIClientError("失敗"), {"kind": "normal"}])
def test_failed_new_consultation_keeps_existing_one(client, ai, store, user_id, failure):
    old = make_state(store, user_id)
    ai.push(failure)

    response = client.post(BASE, json={"theme": "other", "detail": "架空の相談本文"})

    assert response.status_code == 502
    assert client.get(f"{BASE}/{old.consultation_id}").status_code == 200


def test_safety_on_new_consultation_also_replaces_existing_one(client, ai, store, user_id):
    old = make_state(store, user_id)
    ai.push(fakes.safety_output(ai_question=None))

    response = client.post(BASE, json={"theme": "other", "detail": "架空の相談本文"})

    assert response.json()["status"] == "safety_guidance"
    assert client.get(f"{BASE}/{old.consultation_id}").status_code == 404


async def test_second_start_while_starting_is_busy(store, ai, user_id):
    # ⑦：同じユーザーの開始処理中に2つ目の開始が届いたら409（CONSULTATION_BUSY）
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(fakes.first_question())
    first = asyncio.create_task(service.start(user_id, ThemeCategory.OTHER, "架空の相談本文1"))
    await ai.started.wait()

    with pytest.raises(ConsultationBusy):
        # 待たずに409になることを確かめる（待ってしまう場合はタイムアウトで失敗させる）
        await asyncio.wait_for(
            service.start(user_id, ThemeCategory.OTHER, "架空の相談本文2"), timeout=5
        )
    assert len(ai.calls) == 1  # 2つ目はAIを呼ばない

    ai.wait_event.set()
    state = await first
    assert [s for s in store._states.values() if s.user_id == user_id] == [state]

    # 1つ目が終わった後は、新しい相談を開始できる
    ai.wait_event = None
    ai.push(fakes.first_question())
    await service.start(user_id, ThemeCategory.OTHER, "架空の相談本文3")
    assert len([s for s in store._states.values() if s.user_id == user_id]) == 1


async def test_other_users_can_start_while_starting(store, ai, user_id):
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(fakes.first_question())
    first = asyncio.create_task(service.start(user_id, ThemeCategory.OTHER, "架空の相談本文"))
    await ai.started.wait()

    other_ai = fakes.FakeAIClient([fakes.first_question()])
    other = await ConsultationService(store, other_ai).start(
        uuid4(), ThemeCategory.OTHER, "架空の相談本文"
    )
    assert other.consultation_id in store._states

    ai.wait_event.set()
    await first


async def test_concurrent_start_returns_409_busy(ai, store, user_id):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ai.wait_event = asyncio.Event()
        ai.push(fakes.first_question())
        body = {"theme": "other", "detail": f"架空の相談本文 {MARKER}_detail"}
        first = asyncio.create_task(client.post(BASE, json=body))
        await ai.started.wait()

        second = await asyncio.wait_for(client.post(BASE, json=body), timeout=5)
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONSULTATION_BUSY"
        assert MARKER not in second.text

        ai.wait_event.set()
        assert (await first).status_code == 201


@pytest.mark.parametrize("failure", [None, AIClientError("失敗")])
async def test_user_discard_while_starting_does_not_register(store, ai, user_id, failure):
    # ⑨：開始処理中に退会でユーザー単位の破棄が呼ばれたら、AIの応答後も登録しない
    from app.features.consultations.public import discard_user_consultations

    old = make_state(store, user_id)
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(failure or fakes.first_question())
    starting = asyncio.create_task(
        service.start(user_id, ThemeCategory.OTHER, "架空の相談本文")
    )
    await ai.started.wait()

    await discard_user_consultations(user_id, store=store)
    ai.wait_event.set()

    # AIが成功しても失敗しても、破棄された開始は404（502にしない）
    with pytest.raises(ConsultationNotFound):
        await starting
    assert [s for s in store._states.values() if s.user_id == user_id] == []
    assert old.consultation_id not in store._states
    # 予約も残らない（次の開始を妨げない）
    assert user_id not in store._starting


# --- AIの応答待ち中に破棄された場合は、書き込まず404（復活させない） ---------------


async def _wait_ai_then(store, ai, user_id, discard):
    state = make_state(store, user_id)
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(fakes.event_ask())
    waiting = asyncio.create_task(
        service.event_dialogue(user_id, state.consultation_id, "answer", "架空の回答")
    )
    await ai.started.wait()

    await discard(service, state)
    ai.wait_event.set()

    with pytest.raises(ConsultationNotFound):
        await waiting
    assert not store.exists(user_id, state.consultation_id)
    assert state.consultation_id not in store._states
    assert state.question_count == 0
    return state


async def test_delete_while_ai_is_waiting(store, ai, user_id):
    async def discard(service, state):
        service.discard(user_id, state.consultation_id)

    await _wait_ai_then(store, ai, user_id, discard)


async def test_new_consultation_while_ai_is_waiting(store, ai, user_id):
    other_ai = fakes.FakeAIClient([fakes.first_question()])

    async def discard(service, state):
        await ConsultationService(store, other_ai).start(
            user_id, ThemeCategory.OTHER, "架空の新しい相談本文"
        )

    await _wait_ai_then(store, ai, user_id, discard)
    assert len([s for s in store._states.values() if s.user_id == user_id]) == 1


async def test_user_discard_while_ai_is_waiting(store, ai, user_id):
    from app.features.consultations.public import discard_user_consultations

    async def discard(service, state):
        await discard_user_consultations(user_id, store=store)

    await _wait_ai_then(store, ai, user_id, discard)


async def _discard_by_delete(store, user_id, state):
    ConsultationService(store, fakes.FakeAIClient()).discard(user_id, state.consultation_id)


async def _discard_by_new_consultation(store, user_id, state):
    other_ai = fakes.FakeAIClient([fakes.first_question()])
    await ConsultationService(store, other_ai).start(
        user_id, ThemeCategory.OTHER, "架空の新しい相談本文"
    )


async def _discard_by_user(store, user_id, state):
    from app.features.consultations.public import discard_user_consultations

    await discard_user_consultations(user_id, store=store)


DISCARDS = [_discard_by_delete, _discard_by_new_consultation, _discard_by_user]


@pytest.mark.parametrize("discard", DISCARDS)
async def test_discarded_state_is_not_revived_when_ai_fails(store, ai, user_id, discard):
    # ⑧：AIの応答待ち中に破棄され、その後AIが失敗しても、巻き戻しで復活しない。
    # 応答は502ではなく404（PRレビュー：もえさん）
    state = make_state(store, user_id)
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(AIClientError("失敗"))
    waiting = asyncio.create_task(
        service.event_dialogue(user_id, state.consultation_id, "answer", "架空の回答")
    )
    await ai.started.wait()

    await discard(store, user_id, state)
    ai.wait_event.set()

    with pytest.raises(ConsultationNotFound):
        await waiting
    assert state.consultation_id not in store._states
    assert not store.exists(user_id, state.consultation_id)


@pytest.mark.parametrize("failure", [AIClientError("失敗"), {"kind": "normal"}])
async def test_ai_failure_after_delete_returns_404(ai, store, user_id, failure):
    # 応答待ち中にDELETEされ、その後AIが失敗（呼び出し失敗・出力不正）した場合のHTTP応答は404
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    state = make_state(store, user_id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ai.wait_event = asyncio.Event()
        ai.push(failure)
        waiting = asyncio.create_task(
            client.post(
                f"{BASE}/{state.consultation_id}/event-dialogue",
                json={"action": "answer", "answer": f"架空の回答 {MARKER}_answer"},
            )
        )
        await ai.started.wait()
        deleted = await client.delete(f"{BASE}/{state.consultation_id}")
        assert deleted.status_code == 204
        ai.wait_event.set()
        response = await waiting

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONSULTATION_NOT_FOUND"
    assert MARKER not in response.text


def test_ai_failure_without_discard_is_still_502(client, ai, store, user_id):
    # 相談が残っている場合は、これまでどおり502
    state = make_state(store, user_id)
    ai.push(AIClientError("失敗"))

    response = client.post(
        f"{BASE}/{state.consultation_id}/event-dialogue",
        json={"action": "answer", "answer": "架空の回答"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert state.consultation_id in store._states


async def test_new_consultation_ttl_starts_after_ai_responds(store, ai, user_id, clock):
    # 新しい相談の保持時間は、AIの待ち時間を含めず、登録に成功した時点から数える（PRレビュー：もえさん）
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(fakes.first_question())
    starting = asyncio.create_task(service.start(user_id, ThemeCategory.OTHER, "架空の相談本文"))
    await ai.started.wait()
    clock.advance(minutes=10)  # AIの応答に時間がかかった
    ai.wait_event.set()
    state = await starting

    assert state.updated_at == clock.now
    clock.advance(minutes=29, seconds=59)
    assert store.exists(user_id, state.consultation_id)
    clock.advance(seconds=1)
    assert not store.exists(user_id, state.consultation_id)


async def test_safety_start_ttl_starts_at_registration(store, ai, user_id, clock, monkeypatch):
    from app.features.consultations import safety

    monkeypatch.setattr(safety, "CRISIS_KEYWORDS", ("テストキケン",))
    service = ConsultationService(store, ai)
    state = await service.start(user_id, ThemeCategory.OTHER, "架空の相談本文 テストキケン")

    assert state.updated_at == clock.now


@pytest.mark.parametrize("discard", DISCARDS)
async def test_discarded_state_is_not_revived_by_internal_error(
    store, ai, user_id, discard, monkeypatch
):
    # ⑧・ST-19：AIの応答待ち中に破棄され、その後に想定外のエラーが起きても復活しない
    state = make_state(store, user_id)
    service = ConsultationService(store, ai)
    ai.wait_event = asyncio.Event()
    ai.push(fakes.event_ask())

    original_exists = store.exists

    def failing_exists(*args):
        # 破棄の確認の直前に想定外のエラーを起こす
        raise RuntimeError("想定外のエラー")

    waiting = asyncio.create_task(
        service.event_dialogue(user_id, state.consultation_id, "answer", "架空の回答")
    )
    await ai.started.wait()
    await discard(store, user_id, state)
    monkeypatch.setattr(store, "exists", failing_exists)
    ai.wait_event.set()

    with pytest.raises(RuntimeError):
        await waiting
    monkeypatch.setattr(store, "exists", original_exists)
    assert state.consultation_id not in store._states
    assert not store.exists(user_id, state.consultation_id)
    assert state.question_count == 0


# --- ユーザー単位の破棄（F-06：退会処理から呼ぶ） -----------------------------------


async def test_discard_user_consultations(store, user_id):
    from app.features.consultations.public import discard_user_consultations

    mine = [make_state(store, user_id) for _ in range(2)]  # 直接登録した場合も含め、すべて破棄する
    other = make_state(store, uuid4())

    await discard_user_consultations(user_id, store=store)

    assert all(s.consultation_id not in store._states for s in mine)
    assert other.consultation_id in store._states
    assert all(s.user_id != user_id for s in store._states.values())

    # 0件でも、何度呼んでも安全
    await discard_user_consultations(user_id, store=store)
    await discard_user_consultations(uuid4(), store=store)
    assert other.consultation_id in store._states


async def test_discard_user_consultations_while_lock_is_held(store, user_id):
    from app.features.consultations.public import discard_user_consultations

    state = make_state(store, user_id)
    async with store.locked(user_id, state.consultation_id):
        # 処理中でも待たずに破棄できる
        await discard_user_consultations(user_id, store=store)
    assert state.consultation_id not in store._states


# --- 更新の処理中のGET（PRレビュー：めぐさん） --------------------------------------


def _async_app(store, ai, user_id):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return app


def _guided_state(store, user_id):
    """本音に回答済みで、背景を質問している状態"""
    state = ConsultationState(
        consultation_id=uuid4(),
        user_id=user_id,
        theme=ThemeCategory.COMMUNICATION,
        status=ConsultationStatus.GUIDED_DIALOGUE,
        guided_turn_count=1,
    )
    state.messages.append(DialogueTurn(role="user", content="架空の相談本文"))
    state.ai_question = "架空の背景の質問"
    store.add(state)
    return state


async def test_get_while_updating_returns_409_busy(ai, store, user_id):
    # 処理中に更新前の状態を返すと、画面が送り直して古い回答が次の項目へ記録されてしまうため、
    # 処理中のGETは409（CONSULTATION_BUSY）にする
    state = _guided_state(store, user_id)
    cid = state.consultation_id
    transport = httpx.ASGITransport(app=_async_app(store, ai, user_id))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ai.wait_event = asyncio.Event()
        ai.push(fakes.guided_ask(question="架空の望みの質問"))
        posting = asyncio.create_task(
            client.post(
                f"{BASE}/{cid}/guided-dialogue",
                json={"answer": f"架空の背景 {MARKER}_answer"},
            )
        )
        await ai.started.wait()

        for path in ("", "/result"):
            response = await asyncio.wait_for(client.get(f"{BASE}/{cid}{path}"), timeout=5)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "CONSULTATION_BUSY"
            assert MARKER not in response.text

        ai.wait_event.set()
        assert (await posting).status_code == 200

        # 処理が終わった後のGETは、進んだ後の状態を返す
        response = await client.get(f"{BASE}/{cid}")
        assert response.status_code == 200
        assert response.json()["current_topic"] == "wish"
        assert response.json()["ai_question"] == "架空の望みの質問"


async def test_get_after_failed_update_returns_unchanged_state(ai, store, user_id):
    # 処理が失敗した場合は、ロックが外れた後のGETで、送る前の状態を取得できる（送り直してよい）
    state = _guided_state(store, user_id)
    cid = state.consultation_id
    transport = httpx.ASGITransport(app=_async_app(store, ai, user_id))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ai.wait_event = asyncio.Event()
        ai.push(AIClientError("失敗"))
        posting = asyncio.create_task(
            client.post(f"{BASE}/{cid}/guided-dialogue", json={"answer": "架空の背景"})
        )
        await ai.started.wait()
        assert (await client.get(f"{BASE}/{cid}")).status_code == 409

        ai.wait_event.set()
        assert (await posting).status_code == 502

        response = await client.get(f"{BASE}/{cid}")
        assert response.status_code == 200
        assert response.json()["current_topic"] == "background"
        assert response.json()["ai_question"] == "架空の背景の質問"


async def test_delete_and_approved_result_are_not_blocked_while_updating(store, user_id):
    # GETは409になるが、中断（DELETE）とI-05向けの関数は、処理中でも待たずに使える
    from app.features.consultations.public import get_approved_result

    from tests.features.consultations.factories import make_save_confirmation_state

    saved = make_save_confirmation_state(store, user_id)
    async with store.locked(user_id, saved.consultation_id):
        approved = await get_approved_result(user_id, saved.consultation_id, store=store)
        assert approved.consultation_id == saved.consultation_id
        ConsultationService(store, fakes.FakeAIClient()).discard(user_id, saved.consultation_id)
    assert saved.consultation_id not in store._states
