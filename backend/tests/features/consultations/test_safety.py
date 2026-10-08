"""安全案内のテスト（I-03B。Q-09・Q-28。テスト設計書 AI-08〜AI-11・ST-13・NP-12）。

テストデータはすべて架空。危機を示す入力は、キーワード一覧を差し替えて架空の語で確かめる。
AIは FakeAIClient で模し、外部APIへは接続しない。
"""

import logging
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.features.consultations import safety
from app.features.consultations.router import get_current_user_id, router
from app.features.consultations.safety import (
    SAFETY_MESSAGE,
    contains_crisis_keyword,
    normalize,
)
from app.features.consultations.schemas import (
    ConsultationStatus,
    EventDetailsDraft,
    ThemeCategory,
)
from app.features.consultations.state import ConsultationState, DialogueTurn
from app.features.consultations.store import ConsultationStore, get_consultation_store
from app.integrations.openrouter.client import get_ai_client

from tests.features.consultations import fakes

BASE = "/api/v1/consultations"
MARKER = "PORORI_TEST_MARKER_SAFETY"
# テスト用の架空のキーワード（実際の一覧はチームで確認して決める）
FAKE_KEYWORD = "テストキケン"


@pytest.fixture
def fake_keywords(monkeypatch):
    monkeypatch.setattr(safety, "CRISIS_KEYWORDS", (FAKE_KEYWORD,))


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
def client(ai, store, user_id):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_consultation_store] = lambda: store
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


def make_state(store, user_id, status, **fields):
    state = ConsultationState(
        consultation_id=uuid4(),
        user_id=user_id,
        theme=ThemeCategory.COMMUNICATION,
        status=status,
        **fields,
    )
    # 相談内容が残っていないことを確かめるため、目印入りの会話を入れておく
    state.messages.append(DialogueTurn(role="user", content=f"架空の相談本文 {MARKER}_history"))
    state.event_details = EventDetailsDraft(
        what_happened="架空の出来事", what_bothered_me="架空の気がかり"
    )
    state.ai_question = "架空の質問"
    store.add(state)
    return state


def assert_switched_to_safety(response, state):
    assert response.status_code == 200
    assert response.json() == {
        "status": "safety_guidance",
        "safety_guidance": {
            "risk_detected": True,
            "safety_message": SAFETY_MESSAGE,
            "continued_normal_structuring": False,
        },
    }
    assert MARKER not in response.text
    # 相談内容を保持しない
    assert state.status is ConsultationStatus.SAFETY_GUIDANCE
    assert state.messages == []
    assert state.event_details is None
    assert state.ai_question is None


# --- キーワードの照合 -------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "テストキケン",
        "ﾃｽﾄｷｹﾝ",  # 半角
        "てすときけん",  # ひらがな
        "テスト　キ ケ ン",  # 空白を挟む
        "前の文 テストキケン 後の文",
    ],
)
def test_keyword_matches_regardless_of_notation(fake_keywords, text):
    assert contains_crisis_keyword(text)


@pytest.mark.parametrize("text", ["テスト", "キケンではない架空の文", "", None])
def test_keyword_does_not_match_other_text(fake_keywords, text):
    assert not contains_crisis_keyword(text)


def test_keyword_checks_every_text(fake_keywords):
    assert contains_crisis_keyword(None, "架空の文", "テストキケン")


def test_normalize():
    assert normalize("ﾀﾋ") == normalize("タヒ") == normalize("たひ")
    assert normalize("Ａ Ｂ") == "ab"


def test_placeholder_keywords_are_normalized_consistently():
    # 仮の一覧の語が、表記をそろえた後も照合できる
    for keyword in safety.CRISIS_KEYWORDS:
        assert contains_crisis_keyword(f"架空の文{keyword}架空の文")


# --- キーワードに該当した場合は、AIを呼ばずに安全案内へ切り替える ------------------


def test_keyword_on_start_returns_safety_without_ai(
    client, ai, store, user_id, fake_keywords, caplog
):
    # AI-08（キーワード判定の場合）
    caplog.set_level(logging.DEBUG)
    response = client.post(
        BASE, json={"theme": "other", "detail": f"架空の相談本文 {FAKE_KEYWORD} {MARKER}_detail"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "safety_guidance"
    assert body["safety_guidance"]["safety_message"] == SAFETY_MESSAGE
    assert ai.calls == []
    state = store.get(user_id, UUID(body["consultation_id"]))
    assert state.messages == []
    assert MARKER not in response.text
    assert MARKER not in caplog.text


@pytest.mark.parametrize(
    ("status", "path", "payload"),
    [
        (
            ConsultationStatus.EVENT_DIALOGUE,
            "event-dialogue",
            {"action": "answer", "answer": f"架空の回答 {FAKE_KEYWORD}"},
        ),
        (
            ConsultationStatus.EVENT_DIALOGUE,
            "event-dialogue",
            {"action": "correct", "correction_input": f"架空の訂正 {FAKE_KEYWORD}"},
        ),
        (
            ConsultationStatus.EMOTION_SELECTION,
            "emotion",
            {"category": "sad", "detail": f"架空の具体化 {FAKE_KEYWORD}"},
        ),
        (
            ConsultationStatus.GUIDED_DIALOGUE,
            "guided-dialogue",
            {"answer": f"架空の本音 {FAKE_KEYWORD}"},
        ),
    ],
)
def test_keyword_during_consultation_returns_safety_without_ai(
    client, ai, store, user_id, fake_keywords, status, path, payload
):
    state = make_state(store, user_id, status)

    response = client.post(f"{BASE}/{state.consultation_id}/{path}", json=payload)

    assert_switched_to_safety(response, state)
    assert ai.calls == []


def test_keyword_check_comes_before_limit_check(client, ai, store, user_id, fake_keywords):
    # 回数の上限を超えた回答でも、危機を示す入力には安全案内を優先する
    state = make_state(store, user_id, ConsultationStatus.EVENT_DIALOGUE, question_count=3)

    response = client.post(
        f"{BASE}/{state.consultation_id}/event-dialogue",
        json={"action": "answer", "answer": f"架空の回答 {FAKE_KEYWORD}"},
    )

    assert_switched_to_safety(response, state)


# --- AIが安全案内を示した場合（AI-09〜AI-11・Q-28） -------------------------------


@pytest.mark.parametrize(
    "ai_output",
    [
        # AI-11：正しい安全案内
        fakes.safety_output(next_action=None, ai_question=None, result=None),
        # AI-09：risk_detected=true なのに continued_normal_structuring=true（矛盾）
        {
            "kind": "safety",
            "next_action": None,
            "ai_question": None,
            "result": None,
            "safety": {**fakes.SAFETY, "continued_normal_structuring": True},
        },
        # AI-10（Q-28）：kind=safety だが safety が null
        {"kind": "safety", "next_action": None, "ai_question": None, "result": None, "safety": None},
        # AI-10（Q-28）：safety_message が欠落
        {
            "kind": "safety",
            "next_action": None,
            "ai_question": None,
            "result": None,
            "safety": {"risk_detected": True, "continued_normal_structuring": False},
        },
        # AI-10（Q-28）：kind=safety なのに通常の項目がある
        {
            "kind": "safety",
            "next_action": "ask",
            "ai_question": f"架空の質問 {MARKER}_aiquestion",
            "result": None,
            "safety": fakes.SAFETY,
        },
        # Q-28：kind=normal でも risk_detected=true なら安全側に倒す
        {
            "kind": "normal",
            "next_action": "ask",
            "ai_question": f"架空の質問 {MARKER}_aiquestion",
            "result": None,
            "safety": fakes.SAFETY,
        },
    ],
)
def test_ai_safety_sign_returns_fixed_guidance(client, ai, store, user_id, ai_output):
    state = make_state(store, user_id, ConsultationStatus.GUIDED_DIALOGUE)
    ai.push(ai_output)

    response = client.post(
        f"{BASE}/{state.consultation_id}/guided-dialogue", json={"answer": "架空の回答"}
    )

    assert_switched_to_safety(response, state)
    # AIが生成した文（架空の電話番号を含む想定の文）は返さない
    assert fakes.SAFETY["safety_message"] not in response.text


@pytest.mark.parametrize(
    "ai_output",
    [
        # kind も risk_detected も読み取れない
        {"next_action": None, "ai_question": None, "result": None, "safety": None},
        {"kind": "normal", "safety": {"risk_detected": "yes"}},
    ],
)
def test_unreadable_output_returns_502_without_changing_state(client, ai, store, user_id, ai_output):
    state = make_state(store, user_id, ConsultationStatus.GUIDED_DIALOGUE)
    ai.push(ai_output)

    response = client.post(
        f"{BASE}/{state.consultation_id}/guided-dialogue", json={"answer": "架空の回答"}
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_OUTPUT_INVALID"
    assert state.status is ConsultationStatus.GUIDED_DIALOGUE
    assert len(state.messages) == 1


# --- ST-13：安全案内の状態では通常の整理を続けられない ------------------------------


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "event-dialogue", {"action": "answer", "answer": "架空の回答"}),
        ("post", "event-summary/confirm", {"action": "proceed"}),
        ("post", "event-summary/confirm", {"action": "ask_more"}),
        ("post", "emotion", {"category": "sad", "cannot_verbalize": True}),
        ("post", "guided-dialogue", {"answer": "架空の回答"}),
        ("get", "result", None),
        ("patch", "result", {"wish": "架空の望み"}),
        ("post", "result/approve", None),
        ("post", "handling", {"handling": "hold"}),
    ],
)
def test_operations_in_safety_guidance_are_conflict(
    client, ai, store, user_id, method, path, payload
):
    ai.push(fakes.safety_output(ai_question=None))
    cid = client.post(BASE, json={"theme": "other", "detail": "架空の相談本文"}).json()[
        "consultation_id"
    ]
    calls = len(ai.calls)

    kwargs = {"json": payload} if payload is not None else {}
    response = getattr(client, method)(f"{BASE}/{cid}/{path}", **kwargs)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSULTATION_STATE_CONFLICT"
    assert len(ai.calls) == calls

    response = client.get(f"{BASE}/{cid}")
    assert response.status_code == 200
    assert response.json()["status"] == "safety_guidance"
    assert response.json()["safety_guidance"]["safety_message"] == SAFETY_MESSAGE


# --- 決定したキーワード一覧での照合（Issue #50 B） ---------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # 安全側として反応を許容する（否定・引用・一般的な説明）
        "死にたいわけではない",
        "友人から死にたいと相談された",
        "自殺対策の記事を読んだ",
        "小説の遺書の場面",
        # 表記揺れ
        "ｼﾆﾀｲ",
        "死 に たい",
        "死、に、たい",
        "タヒにたい",
        "ﾘｽﾄｶｯﾄ",
        # 活用・具体化した語
        "一緒に死のうと言われた",
        "薬を大量に飲んだ",
        "命を絶とうとした",
    ],
)
def test_agreed_keywords_match(text):
    assert contains_crisis_keyword(text)


@pytest.mark.parametrize(
    "text",
    [
        "タヒチに行きたい",
        "恥ずかしくて消えたい",
        "死ぬほど疲れた",
        "消えるボールペン",
        "締め切りに追われて死んでる",
        "この関係を終わりにしたい",
        "心中お察しします",
        "一緒に死ぬほど笑った",
        "薬を大量に処方された",
        "首をつかまれた",
    ],
)
def test_agreed_keywords_do_not_match_common_expressions(text):
    assert not contains_crisis_keyword(text)


def test_safety_message_is_fixed_text():
    assert "相談窓口" in SAFETY_MESSAGE
    # 電話番号・URLは画面側で管理するため、APIの文言には含めない
    assert "http" not in SAFETY_MESSAGE
    assert not any(ch.isdigit() for ch in SAFETY_MESSAGE)


# --- 直接編集の判定（Issue #50 A） ------------------------------------------------


def test_keyword_in_edited_summary_on_proceed_returns_safety(
    client, ai, store, user_id, fake_keywords
):
    state = make_state(store, user_id, ConsultationStatus.EVENT_SUMMARY_READY)

    response = client.post(
        f"{BASE}/{state.consultation_id}/event-summary/confirm",
        json={
            "action": "proceed",
            "event_details": {
                "what_happened": f"架空の出来事 {FAKE_KEYWORD}",
                "what_bothered_me": "架空の気がかり",
            },
        },
    )

    assert_switched_to_safety(response, state)
    assert ai.calls == []


def test_proceed_without_edit_is_not_judged(client, ai, store, user_id, fake_keywords):
    # 編集せずに進む場合は、AIが作った要約を判定しない
    state = make_state(store, user_id, ConsultationStatus.EVENT_SUMMARY_READY)
    state.event_details = EventDetailsDraft(
        what_happened=f"架空の出来事 {FAKE_KEYWORD}", what_bothered_me="架空の気がかり"
    )

    response = client.post(
        f"{BASE}/{state.consultation_id}/event-summary/confirm", json={"action": "proceed"}
    )

    assert response.json() == {"status": "emotion_selection"}


def _result_ready_state(store, user_id, **overrides):
    from app.features.consultations.schemas import ConsultationResultDraft

    result = {
        "event_summary": "架空の出来事",
        "emotion": "架空の感情",
        "true_feeling": "架空の本音",
        "background": "",
        "wish": "架空の望み",
        **overrides,
    }
    return make_state(
        store, user_id, ConsultationStatus.RESULT_READY, result=ConsultationResultDraft(**result)
    )


def test_keyword_in_edited_result_on_approve_returns_safety(
    client, ai, store, user_id, fake_keywords
):
    state = _result_ready_state(store, user_id)
    cid = state.consultation_id

    response = client.patch(f"{BASE}/{cid}/result", json={"wish": f"架空の望み {FAKE_KEYWORD}"})
    assert response.status_code == 200  # 編集の時点では判定しない

    response = client.post(f"{BASE}/{cid}/result/approve")

    assert_switched_to_safety(response, state)
    # 承認されず、編集内容も含めて整理結果が消去される
    assert state.approved is False
    assert state.approved_at is None
    assert state.result is None
    assert state.approved_result is None
    assert state.edited_result_fields == set()
    assert ai.calls == []


async def test_approve_switched_to_safety_cannot_be_saved(store, ai, user_id, fake_keywords):
    # 承認で安全案内に切り替わった相談は、I-05へ承認済み結果を渡さない（メモを保存できない）
    from app.features.consultations.exceptions import ConsultationStateConflict
    from app.features.consultations.public import get_approved_result
    from app.features.consultations.schemas import ConsultationResultInput
    from app.features.consultations.service import ConsultationService

    state = _result_ready_state(store, user_id)
    service = ConsultationService(store, ai)
    await service.update_result(
        user_id, state.consultation_id, ConsultationResultInput(true_feeling=FAKE_KEYWORD)
    )
    await service.approve_result(user_id, state.consultation_id)

    with pytest.raises(ConsultationStateConflict):
        await get_approved_result(user_id, state.consultation_id, store=store)
    with pytest.raises(ConsultationStateConflict):
        await service.choose_handling(user_id, state.consultation_id, "hold")


def test_unedited_ai_result_is_not_judged_on_approve(client, store, user_id, fake_keywords):
    # AIが作った項目は判定しない（本人が編集した項目だけを判定する）
    state = _result_ready_state(store, user_id, true_feeling=f"架空の本音 {FAKE_KEYWORD}")
    cid = state.consultation_id
    client.patch(f"{BASE}/{cid}/result", json={"wish": "架空の編集した望み"})

    response = client.post(f"{BASE}/{cid}/result/approve")

    assert response.json() == {"status": "handling_selection", "approved": True}


def test_edited_back_to_safe_text_is_approved(client, store, user_id, fake_keywords):
    # 判定は承認時点の値で行う
    state = _result_ready_state(store, user_id)
    cid = state.consultation_id
    client.patch(f"{BASE}/{cid}/result", json={"wish": f"架空の望み {FAKE_KEYWORD}"})
    client.patch(f"{BASE}/{cid}/result", json={"wish": "架空の書き直した望み"})

    response = client.post(f"{BASE}/{cid}/result/approve")

    assert response.json() == {"status": "handling_selection", "approved": True}
