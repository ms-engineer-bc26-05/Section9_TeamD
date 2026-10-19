"""相談開始APIに利用回数を組み込んだテスト（Issue #57 質問③⑨、テスト設計 RL・AI-08・AI-15）。

相談Routerだけを載せたテスト用アプリを使う。AIは FakeAIClient、認証は固定UUID。
利用回数は、偽物のカウンタ（大半のテスト）と実物のRedis（最後のテスト）で確認する。
"""

import asyncio
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.errors import register_exception_handlers
from app.features.consultations import service as consultation_service
from app.features.consultations.router import get_current_user_id, router
from app.features.consultations.store import ConsultationStore, get_consultation_store
from app.features.usage.consultation_gate import (
    ConsultationStartGate,
    get_consultation_start_gate,
)
from app.features.usage.exceptions import AccountDeleting
from app.features.usage.limiter import UsageLimiter, usage_key
from app.features.usage.service import UsageService
from app.features.usage.settings import PlanCode
from app.features.usage.users import DbUserStatusChecker, UserStatus
from app.integrations.openrouter.client import AIClientError, get_ai_client
from tests.features.consultations import fakes as ai_fakes
from tests.features.usage.fakes import (
    FakeDbSession,
    FakeLimiter,
    FakeMemoCounter,
    FakePlanResolver,
    FakeUserStatusChecker,
    make_settings,
    plan_unavailable,
)

BASE = "/api/v1/consultations"
BODY = {"theme": "communication", "detail": "架空の相談本文"}
LIMIT = 3  # 無料プランの既定値


class Harness:
    def __init__(self, limiter, users=None, plans=None, user_id=None):
        self.ai = ai_fakes.FakeAIClient()
        self.limiter = limiter
        self.users = users or FakeUserStatusChecker()
        self.user_id = user_id or uuid4()
        usage = UsageService(
            limiter, plans or FakePlanResolver(), FakeMemoCounter(), make_settings()
        )
        self.gate = ConsultationStartGate(usage, self.users)
        self.store = ConsultationStore()
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router)
        app.dependency_overrides[get_consultation_store] = lambda: self.store
        app.dependency_overrides[get_ai_client] = lambda: self.ai
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        app.dependency_overrides[get_consultation_start_gate] = lambda: self.gate
        self.app = app
        self.client = TestClient(app)

    def start(self):
        return self.client.post(BASE, json=BODY)


def error_code(response):
    return response.json()["error"]["code"]


# ---------------------------------------------------------------------------
# 加算・上限
# ---------------------------------------------------------------------------


def test_start_counts_one():
    h = Harness(FakeLimiter(count=0))
    h.ai.push(ai_fakes.first_question())

    response = h.start()

    assert response.status_code == 201
    assert h.limiter.count == 1
    assert h.users.calls == 1


def test_start_at_limit_is_rejected_without_calling_ai():
    # RL-04：上限を超える相談は開始できない。AIは呼ばれず、回数も増えない
    h = Harness(FakeLimiter(count=LIMIT))

    response = h.start()

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "USAGE_LIMIT_EXCEEDED",
            "message": "現在のプランで利用できる回数に達しました。",
        }
    }
    assert h.ai.calls == []
    assert h.limiter.count == LIMIT
    assert h.users.calls == 0


def test_started_consultation_continues_after_limit_reached():
    # RL-03・RL-05：上限ちょうどになる回は開始でき、開始した相談は途中で止めない
    h = Harness(FakeLimiter(count=LIMIT - 1))
    h.ai.push(ai_fakes.first_question())
    cid = h.start().json()["consultation_id"]
    assert h.limiter.count == LIMIT

    h.ai.push(ai_fakes.event_ask())
    response = h.client.post(
        f"{BASE}/{cid}/event-dialogue", json={"action": "answer", "answer": "架空の回答"}
    )

    assert response.status_code == 200
    assert h.limiter.reserve_calls == [LIMIT]  # 相談の途中では判定しない


def test_premium_plan_uses_premium_limit():
    # RL-14：有料プランは有料の上限値で判定する
    h = Harness(FakeLimiter(count=LIMIT), plans=FakePlanResolver(PlanCode.PREMIUM))
    h.ai.push(ai_fakes.first_question())

    assert h.start().status_code == 201
    assert h.limiter.reserve_calls == [30]


def test_plan_unavailable_returns_503_without_counting():
    h = Harness(FakeLimiter(count=0), plans=plan_unavailable())

    response = h.start()

    assert response.status_code == 503
    assert h.limiter.reserve_calls == []
    assert h.ai.calls == []


def test_redis_failure_allows_start_without_counting():
    # RL-10：Redis障害時も相談を開始できる（フェイルオープン）。戻す処理も行わない
    h = Harness(FakeLimiter(fail=True))
    h.ai.push(ai_fakes.first_question())

    assert h.start().status_code == 201
    assert all(not r.counted for r in h.limiter.refund_calls)


# ---------------------------------------------------------------------------
# 回数を戻す（質問③）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (AIClientError("失敗"), "AI_UNAVAILABLE"),
        ({"kind": "normal", "ai_question": "架空の不正な出力"}, "AI_OUTPUT_INVALID"),
    ],
)
def test_ai_failure_on_start_refunds(failure, code):
    # AI-15：開始時のAI失敗では相談が作成されず、加算した1回を戻す
    h = Harness(FakeLimiter(count=1))
    h.ai.push(failure)

    response = h.start()

    assert response.status_code == 502
    assert error_code(response) == code
    assert h.limiter.count == 1


def test_ai_safety_on_start_refunds():
    # AI-08：開始時にAIが安全案内を示した場合は、回数に含めない
    h = Harness(FakeLimiter(count=1))
    h.ai.push(ai_fakes.safety_output(ai_question=None))

    response = h.start()

    assert response.status_code == 201
    assert response.json()["status"] == "safety_guidance"
    assert h.limiter.count == 1


def test_keyword_safety_on_start_refunds(monkeypatch):
    # キーワード判定で安全案内へ切り替わった場合も、回数に含めない（AIは呼ばない）
    monkeypatch.setattr(consultation_service, "contains_crisis_keyword", lambda *texts: True)
    h = Harness(FakeLimiter(count=1))

    response = h.start()

    assert response.status_code == 201
    assert response.json()["status"] == "safety_guidance"
    assert h.ai.calls == []
    assert h.limiter.count == 1


def test_unexpected_error_on_start_refunds():
    # 500になる想定外の例外でも戻す
    h = Harness(FakeLimiter(count=0))
    h.ai.push(RuntimeError("架空の想定外の例外"))
    client = TestClient(h.app, raise_server_exceptions=False)

    response = client.post(BASE, json=BODY)

    assert response.status_code == 500
    assert h.limiter.count == 0


async def test_concurrent_start_busy_refunds_only_the_second():
    # 同じユーザーの開始処理中に2つ目の開始が届いた場合（409）は、2つ目の分だけ戻す
    h = Harness(FakeLimiter(count=0))
    h.ai.wait_event = asyncio.Event()
    h.ai.push(ai_fakes.first_question())
    transport = httpx.ASGITransport(app=h.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = asyncio.create_task(client.post(BASE, json=BODY))
        await h.ai.started.wait()

        second = await client.post(BASE, json=BODY)
        assert second.status_code == 409
        assert error_code(second) == "CONSULTATION_BUSY"
        assert h.limiter.count == 1  # 1つ目の分だけ残る

        h.ai.wait_event.set()
        assert (await first).status_code == 201
    assert h.limiter.count == 1


# ---------------------------------------------------------------------------
# 加算後のユーザー状態の確認（質問⑨）
# ---------------------------------------------------------------------------


def test_deleting_user_is_rejected_and_key_deleted():
    h = Harness(FakeLimiter(count=2), users=FakeUserStatusChecker(UserStatus.DELETING))

    response = h.start()

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "ACCOUNT_DELETING", "message": "退会処理中のため利用できません。"}
    }
    assert h.ai.calls == []
    assert h.limiter.delete_calls == 1
    assert h.limiter.count == 0


def test_absent_user_is_unauthorized_and_key_deleted():
    # 退会完了で内部ユーザーがいない場合は401（#47の契約）
    h = Harness(FakeLimiter(count=2), users=FakeUserStatusChecker(UserStatus.ABSENT))

    response = h.start()

    assert response.status_code == 401
    assert error_code(response) == "UNAUTHORIZED"
    assert h.ai.calls == []
    assert h.limiter.delete_calls == 1


def test_user_status_unavailable_refunds():
    # DB障害で状態を確認できない場合は開始せず、加算した1回を戻す
    h = Harness(FakeLimiter(count=1), users=FakeUserStatusChecker(None))

    response = h.start()

    assert response.status_code == 503
    assert h.ai.calls == []
    assert h.limiter.count == 1
    assert h.limiter.delete_calls == 0


def test_unexpected_error_in_status_check_refunds():
    # 状態の確認中に想定外の例外が起きても、加算した1回を残さない（PR #90 レビュー①）
    h = Harness(FakeLimiter(count=1), users=FakeUserStatusChecker(error=RuntimeError("架空")))
    client = TestClient(h.app, raise_server_exceptions=False)

    response = client.post(BASE, json=BODY)

    assert response.status_code == 500
    assert h.ai.calls == []
    assert h.limiter.count == 1


async def test_cancel_during_status_check_refunds():
    # 状態の確認中に処理が中断（キャンセル）されても、加算した1回を残さない（PR #90 レビュー①）
    limiter = FakeLimiter(count=1)
    usage = UsageService(limiter, FakePlanResolver(), FakeMemoCounter(), make_settings())
    users = FakeUserStatusChecker(error=asyncio.CancelledError())
    gate = ConsultationStartGate(usage, users)

    with pytest.raises(asyncio.CancelledError):
        async with gate.consultation_start(uuid4()):
            pytest.fail("状態の確認に失敗したのに相談開始へ進んだ")

    assert limiter.count == 1
    assert len(limiter.refund_calls) == 1


async def test_refund_is_not_repeated_after_key_deleted():
    # 退会処理中でキーを丸ごと削除した後は、戻す処理でRedisを重ねて操作しない
    limiter = FakeLimiter(count=2)
    usage = UsageService(limiter, FakePlanResolver(), FakeMemoCounter(), make_settings())
    gate = ConsultationStartGate(usage, FakeUserStatusChecker(UserStatus.DELETING))

    with pytest.raises(AccountDeleting):
        async with gate.consultation_start(uuid4()):
            pytest.fail("退会処理中なのに相談開始へ進んだ")

    assert limiter.delete_calls == 1
    assert limiter.count == 0  # 削除後に、さらに1回減らしていない


# ---------------------------------------------------------------------------
# DBからの状態の再取得（#92。users/service.py の get_user_status へ接続）
# ---------------------------------------------------------------------------


def db_harness(session: FakeDbSession, count: int = 0) -> Harness:
    return Harness(FakeLimiter(count=count), users=DbUserStatusChecker(session.factory))


def test_db_active_user_can_start():
    session = FakeDbSession("active")
    h = db_harness(session)
    h.ai.push(ai_fakes.first_question())

    assert h.start().status_code == 201
    assert h.limiter.count == 1
    # 加算した後に、DBから状態を1回取り直している
    assert len(session.statements) == 1
    assert (session.closed, session.commits) == (1, 0)


@pytest.mark.parametrize(
    ("db_status", "status_code", "code"),
    [
        ("deleting", 403, "ACCOUNT_DELETING"),
        (None, 401, "UNAUTHORIZED"),  # 退会完了で内部ユーザーの行がない
    ],
)
def test_db_not_active_user_cannot_start(db_status, status_code, code):
    # 加算後の再取得で退会処理中・退会完了と分かった場合は、AIを呼ばず、キーを丸ごと削除する
    h = db_harness(FakeDbSession(db_status), count=2)

    response = h.start()

    assert response.status_code == status_code
    assert error_code(response) == code
    assert h.ai.calls == []
    assert h.limiter.delete_calls == 1
    assert h.limiter.count == 0


def test_db_connection_failure_refunds_and_returns_503():
    # DBに接続できず状態を確認できない場合は、加算した1回を戻して503
    error = OperationalError("SELECT", {}, ConnectionRefusedError("DUMMY_DB_ERROR_MARKER"))
    h = db_harness(FakeDbSession(error=error), count=1)

    response = h.start()

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "DB_UNAVAILABLE", "message": "データベースに接続できませんでした。"}
    }
    assert "DUMMY_DB_ERROR_MARKER" not in response.text
    assert h.ai.calls == []
    assert h.limiter.count == 1  # 加算した1回を戻した
    assert h.limiter.delete_calls == 0  # ユーザーがいない扱いにはしない


@pytest.mark.parametrize(
    "session",
    [
        FakeDbSession("unexpected"),
        FakeDbSession(error=RuntimeError("DUMMY_ERROR")),
    ],
)
async def test_db_unexpected_error_refunds_and_propagates(session):
    # 接続障害以外の例外は上へ送る（共通の500）。加算した1回は戻し、キーは削除しない
    limiter = FakeLimiter(count=1)
    usage = UsageService(limiter, FakePlanResolver(), FakeMemoCounter(), make_settings())
    gate = ConsultationStartGate(usage, DbUserStatusChecker(session.factory))

    with pytest.raises(RuntimeError):
        async with gate.consultation_start(uuid4()):
            pytest.fail("状態を確認できないのに相談開始へ進んだ")

    assert limiter.count == 1
    assert limiter.delete_calls == 0


# ---------------------------------------------------------------------------
# 実物のRedisでの通しの確認
# ---------------------------------------------------------------------------


async def test_with_real_redis(redis_client, new_user):
    user = new_user()
    h = Harness(None, user_id=user)
    usage = UsageService(
        UsageLimiter(redis_client, 60), FakePlanResolver(), FakeMemoCounter(), make_settings()
    )
    h.gate = ConsultationStartGate(usage, FakeUserStatusChecker())
    transport = httpx.ASGITransport(app=h.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # AIの失敗は戻す。0になったのでキーごと消えている
        h.ai.push(AIClientError("失敗"))
        assert (await client.post(BASE, json=BODY)).status_code == 502
        assert await redis_client.exists(usage_key(user)) == 0

        # 上限まで開始でき、超えると403（拒否した分は加算しない）
        for _ in range(LIMIT):
            h.ai.push(ai_fakes.first_question())
            assert (await client.post(BASE, json=BODY)).status_code == 201
        assert (await client.post(BASE, json=BODY)).status_code == 403
    assert await redis_client.hget(usage_key(user), "count") == str(LIMIT)
