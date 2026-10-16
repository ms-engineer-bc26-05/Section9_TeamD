"""AI呼び出しの再試行のテスト（I-07 #54）。AIはFakeAIClientで模し、外部APIへは接続しない。

待機（sleep）と時計（clock）は差し替え、実際には待たない。テストデータはすべて架空。
"""

import asyncio
import logging
from uuid import uuid4

import pytest

from app.features.consultations import ai_retry
from app.features.consultations.ai_retry import AIRetryPolicy
from app.features.consultations.ai_schemas import AIOutputInvalid
from app.features.consultations.exceptions import ConsultationNotFound
from app.features.consultations.schemas import ConsultationStatus, EmotionInput, ThemeCategory
from app.features.consultations.service import ConsultationService
from app.features.consultations.store import ConsultationStore
from app.integrations.openrouter.client import AIClientError
from tests.features.consultations import fakes

USER = uuid4()
INVALID = {"kind": "normal"}  # Schemaを満たさない出力


def retryable(kind="http_5xx", retry_after=None):
    return AIClientError(kind=kind, retryable=True, retry_after=retry_after)


class Clock:
    """呼ばれるたびに、用意した時刻を順に返す（最後の値はくり返す）"""

    def __init__(self, *times: float) -> None:
        self.times = list(times)

    def __call__(self) -> float:
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


@pytest.fixture
def store():
    return ConsultationStore()


@pytest.fixture
def ai():
    return fakes.FakeAIClient()


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def make_service(store, ai, sleeps):
    def make(clock=None, on_sleep=None):
        async def sleep(seconds):
            sleeps.append(seconds)
            if on_sleep is not None:
                on_sleep()

        policy = AIRetryPolicy(sleep=sleep, clock=clock or (lambda: 0.0))
        return ConsultationService(store, ai, retry_policy=policy)

    return make


async def start(service):
    return await service.start(USER, ThemeCategory.COMMUNICATION, "架空の相談本文")


# --- 再試行する失敗 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        INVALID,  # Schema不正
        retryable("http_5xx"),
        retryable("network"),
        retryable("invalid_response"),
        retryable("http_429"),  # Retry-Afterなし
    ],
)
async def test_retries_once_and_succeeds(make_service, ai, sleeps, failure):
    ai.push(failure, fakes.first_question())
    state = await start(make_service())

    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    assert state.ai_question == "架空の最初の質問"
    assert len(ai.calls) == 2
    assert sleeps == [1.0]  # 再試行の前に1秒待つ


async def test_retries_with_same_messages(make_service, ai):
    ai.push(INVALID, fakes.first_question())
    await start(make_service())

    first, second = ai.calls
    assert first == second


@pytest.mark.parametrize(("retry_after", "wait"), [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)])
async def test_429_waits_retry_after_up_to_one_second(make_service, ai, sleeps, retry_after, wait):
    ai.push(retryable("http_429", retry_after=retry_after), fakes.first_question())
    await start(make_service())

    assert len(ai.calls) == 2
    assert sleeps == [wait]


# --- 再試行しない失敗 -------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        AIClientError(kind="timeout"),
        AIClientError(kind="http_400"),
        AIClientError(kind="http_401"),
        AIClientError(kind="http_402"),
        AIClientError(kind="http_404"),
        AIClientError(kind="no_api_key"),
        retryable("http_429", retry_after=1.5),  # Retry-Afterが1秒を超える
        retryable("http_429", retry_after=float("inf")),  # Retry-Afterを読めない
    ],
)
async def test_does_not_retry(make_service, store, ai, sleeps, failure):
    ai.push(failure, fakes.first_question())
    with pytest.raises(AIClientError):
        await start(make_service())

    assert len(ai.calls) == 1
    assert sleeps == []
    assert store._states == {}  # 失敗した開始は相談を残さない


async def test_does_not_retry_when_first_attempt_was_slow(make_service, ai, sleeps):
    # 1回目の失敗まで26秒（暫定の線25秒を超える）
    ai.push(INVALID, fakes.first_question())
    with pytest.raises(AIOutputInvalid):
        await start(make_service(clock=Clock(0.0, 26.0)))

    assert len(ai.calls) == 1
    assert sleeps == []


async def test_retries_when_first_attempt_is_within_limit(make_service, ai):
    ai.push(INVALID, fakes.first_question())
    await start(make_service(clock=Clock(0.0, 25.0, 25.0)))

    assert len(ai.calls) == 2


@pytest.mark.parametrize(
    ("failures", "error"),
    [
        ([INVALID, INVALID], AIOutputInvalid),
        ([retryable(), retryable()], AIClientError),
        ([INVALID, retryable()], AIClientError),
    ],
)
async def test_retries_only_once(make_service, store, ai, failures, error):
    ai.push(*failures, fakes.first_question())
    with pytest.raises(error):
        await start(make_service())

    assert len(ai.calls) == 2
    assert store._states == {}


async def test_safety_output_is_not_retried(make_service, ai):
    # 安全案内の印を読み取れる出力は不正ではない（Q-28）
    ai.push({"kind": "safety", "ai_question": "架空の不正な項目"})
    state = await start(make_service())

    assert state.status is ConsultationStatus.SAFETY_GUIDANCE
    assert len(ai.calls) == 1


# --- サーバーが指定した進め方と違う出力 -------------------------------------------


async def test_retries_when_summary_is_missing_at_limit(make_service, ai):
    service = make_service()
    ai.push(fakes.first_question())
    state = await start(service)
    cid = state.consultation_id
    ai.push(fakes.event_ask(), fakes.event_ask())
    await service.event_dialogue(USER, cid, "answer", "架空の回答1")
    await service.event_dialogue(USER, cid, "answer", "架空の回答2")

    # 3回目（上限）は要約の指定。1回目は質問を返し、再試行で要約を返す
    ai.push(fakes.event_ask(), fakes.event_summarize())
    state = await service.event_dialogue(USER, cid, "answer", "架空の回答3")

    assert state.status is ConsultationStatus.EVENT_SUMMARY_READY
    assert state.question_count == 3  # 回数は1回分だけ増える
    assert len(ai.calls) == 5


async def test_retries_when_ask_more_returns_summary(make_service, ai):
    service = make_service()
    ai.push(fakes.first_question())
    state = await start(service)
    cid = state.consultation_id
    ai.push(fakes.event_summarize())
    await service.event_dialogue(USER, cid, "answer", "架空の回答")

    ai.push(fakes.event_summarize(), fakes.event_ask(question="架空の追加の質問"))
    state = await service.confirm_event_summary(USER, cid, "ask_more")

    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    assert state.ai_question == "架空の追加の質問"


async def test_retries_when_guided_dialogue_completes_too_early(make_service, ai):
    service = make_service()
    ai.push(fakes.first_question())
    state = await start(service)
    cid = state.consultation_id
    ai.push(fakes.event_summarize())
    await service.event_dialogue(USER, cid, "answer", "架空の回答")
    await service.confirm_event_summary(USER, cid, "proceed")
    ai.push(fakes.emotion_output())
    await service.submit_emotion(USER, cid, EmotionInput(category="anxious", detail="架空の具体化"))

    # 本音への回答（1問目）なのに整理完了を返す → 再試行で次の質問を返す
    ai.push(fakes.guided_complete(), fakes.guided_ask())
    state = await service.guided_dialogue(USER, cid, "架空の本音", skipped=False)

    assert state.status is ConsultationStatus.GUIDED_DIALOGUE
    assert state.guided_turn_count == 1
    assert state.ai_question == "架空の背景の質問"


# --- 破棄された相談では再試行しない -----------------------------------------------


async def test_discarded_during_failure_returns_404_without_retry(make_service, ai, sleeps):
    service = make_service()
    ai.push(fakes.first_question())
    state = await start(service)
    cid = state.consultation_id

    ai.wait_event = asyncio.Event()
    ai.started.clear()
    ai.push(INVALID, fakes.event_ask())
    task = asyncio.create_task(service.event_dialogue(USER, cid, "answer", "架空の回答"))
    await ai.started.wait()
    service.discard(USER, cid)  # AIの応答待ちの間に破棄
    ai.wait_event.set()

    with pytest.raises(ConsultationNotFound):
        await task
    assert len(ai.calls) == 2  # 開始の1回＋出来事の1回（再試行しない）
    assert sleeps == []


async def test_discarded_while_waiting_returns_404_without_second_call(make_service, ai):
    holder = {}
    service = make_service(on_sleep=lambda: holder["service"].discard(USER, holder["cid"]))
    holder["service"] = service

    ai.push(fakes.first_question())
    state = await start(service)
    holder["cid"] = state.consultation_id

    ai.push(INVALID, fakes.event_ask())
    with pytest.raises(ConsultationNotFound):
        await service.event_dialogue(USER, state.consultation_id, "answer", "架空の回答")
    assert len(ai.calls) == 2  # 再試行の前に破棄に気づき、AIを呼ばない


async def test_failed_retry_does_not_change_state(make_service, ai):
    service = make_service()
    ai.push(fakes.first_question())
    state = await start(service)

    ai.push(INVALID, INVALID)
    with pytest.raises(AIOutputInvalid):
        await service.event_dialogue(USER, state.consultation_id, "correct", "架空の訂正")

    assert state.correction_count == 0
    assert state.status is ConsultationStatus.EVENT_DIALOGUE
    assert not state.lock.locked()


# --- ログ -------------------------------------------------------------------------


async def test_retry_log_has_only_kind_and_attempt(make_service, ai, caplog):
    caplog.set_level(logging.INFO)
    ai.push(
        AIClientError("架空の内容を含む失敗", kind="http_5xx", retryable=True),
        fakes.first_question(),
    )
    await start(make_service())

    assert "reason=http_5xx attempt=2" in caplog.text
    assert "架空" not in caplog.text


async def test_retry_log_for_invalid_output(make_service, ai, caplog):
    caplog.set_level(logging.INFO)
    ai.push({"kind": "normal", "ai_question": None, "safety": None}, fakes.first_question())
    await start(make_service())

    assert "reason=output_invalid attempt=2" in caplog.text


# --- 既定の方針 -------------------------------------------------------------------


async def test_service_uses_default_policy_when_not_given(monkeypatch, store, ai):
    async def no_sleep(seconds):
        return None

    policy = AIRetryPolicy(sleep=no_sleep)
    monkeypatch.setattr(ai_retry, "_policy_provider", lambda: policy)
    ai.push(INVALID, fakes.first_question())

    await start(ConsultationService(store, ai))
    assert len(ai.calls) == 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 25.0), ("40", 40.0), ("0", 0.0), ("abc", 25.0), ("-1", 25.0), ("nan", 25.0)],
)
def test_default_policy_reads_env(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("AI_RETRY_MAX_FIRST_ATTEMPT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("AI_RETRY_MAX_FIRST_ATTEMPT_SECONDS", value)

    policy = ai_retry._default_policy()
    assert policy.max_first_attempt_seconds == expected
    assert policy.max_attempts == 2
