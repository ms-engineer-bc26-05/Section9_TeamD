"""GET /api/v1/usage のテスト（API設計6.7、テスト設計 RL-11・RL-13）。

main.py への登録は結合Issue（I-06）で行うため、利用状況Routerだけを載せたテスト用アプリを使う。
認証・プラン・メモ件数・Redisは偽物にする。
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.core.exceptions import DatabaseUnavailableError
from app.features.auth.schemas import CurrentUser
from app.features.memos.public import MemoDatabaseError
from app.features.usage import memos as usage_memos
from app.features.usage.limiter import get_usage_limiter
from app.features.usage.memos import get_memo_counter
from app.features.usage.plans import get_plan_resolver
from app.features.usage.router import get_current_user_id, router
from app.features.usage.settings import PlanCode, get_usage_settings
from tests.features.usage.fakes import (
    FakeLimiter,
    FakeMemoCounter,
    FakePlanResolver,
    make_settings,
    plan_unavailable,
)

URL = "/api/v1/usage"
USER = uuid4()
RESETS_AT = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def make_client(
    limiter=None,
    plans=None,
    memos=None,
    settings=None,
    authenticated=True,
) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_usage_limiter] = lambda: limiter or FakeLimiter()
    app.dependency_overrides[get_plan_resolver] = lambda: plans or FakePlanResolver()
    app.dependency_overrides[get_memo_counter] = lambda: memos or FakeMemoCounter()
    app.dependency_overrides[get_usage_settings] = lambda: settings or make_settings()
    if authenticated:
        app.dependency_overrides[get_current_user_id] = lambda: USER
    return TestClient(app)


def test_returns_usage():
    # RL-13：利用状況を取得できる
    client = make_client(
        limiter=FakeLimiter(count=2, resets_at=RESETS_AT), memos=FakeMemoCounter(1)
    )

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "plan_code": "free",
        "consultation_count": 2,
        "consultation_limit": 3,
        "can_start_consultation": True,
        "consultation_resets_at": "2026-11-08T12:00:00Z",
        "memo_count": 1,
        "memo_limit": 10,
    }


def test_cannot_start_at_limit():
    client = make_client(limiter=FakeLimiter(count=3, resets_at=RESETS_AT))

    body = client.get(URL).json()

    assert body["can_start_consultation"] is False
    assert body["consultation_resets_at"] == "2026-11-08T12:00:00Z"


def test_not_used_yet_has_no_reset_date():
    body = make_client(limiter=FakeLimiter(count=0, resets_at=None)).get(URL).json()

    assert (body["consultation_count"], body["consultation_resets_at"]) == (0, None)
    assert body["can_start_consultation"] is True


def test_redis_failure_returns_unknown_count():
    # RL-11・質問⑥：Redis障害時も200。回数は null、相談開始は止めない。上限値は返す
    client = make_client(limiter=FakeLimiter(fail=True), memos=FakeMemoCounter(4))

    response = client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["consultation_count"] is None
    assert body["consultation_resets_at"] is None
    assert body["can_start_consultation"] is True
    assert body["consultation_limit"] == 3
    assert body["memo_count"] == 4
    assert "redis" not in response.text.lower()


def test_unlimited_plan():
    # 質問⑤：無制限のときは常に開始でき、リセット日は返さない
    client = make_client(
        limiter=FakeLimiter(count=40, resets_at=RESETS_AT),
        plans=FakePlanResolver(PlanCode.PREMIUM),
        settings=make_settings(USAGE_PREMIUM_CONSULTATION_LIMIT="unlimited"),
    )

    body = client.get(URL).json()

    assert body["plan_code"] == "premium"
    assert body["consultation_limit"] is None
    assert body["consultation_count"] == 40
    assert body["can_start_consultation"] is True
    assert body["consultation_resets_at"] is None


def test_premium_plan_with_limit():
    client = make_client(
        limiter=FakeLimiter(count=29, resets_at=RESETS_AT),
        plans=FakePlanResolver(PlanCode.PREMIUM),
    )

    body = client.get(URL).json()

    assert (body["consultation_limit"], body["can_start_consultation"]) == (30, True)


@pytest.mark.asyncio
async def test_current_user_id_uses_internal_user_id():
    current_user = CurrentUser(user_id=USER)

    assert await get_current_user_id(current_user) == USER


def test_requires_authentication():
    response = make_client(authenticated=False).get(URL)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


UNAVAILABLE_BODY = {
    "error": {
        "code": "DB_UNAVAILABLE",
        "message": "データベースに接続できませんでした。",
    }
}


def test_plan_unavailable_returns_error():
    # プランを確認できない場合は、無料・無制限とみなさずエラーにする
    response = make_client(plans=plan_unavailable()).get(URL)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE_BODY


@pytest.mark.parametrize("error", [DatabaseUnavailableError, MemoDatabaseError])
def test_memo_count_unavailable_returns_error(monkeypatch, error):
    # DBで件数を確認できない場合は、推測した件数（0件など）を返さずエラーにする（#94）
    async def fail(user_id):
        raise error("架空の内部情報")

    monkeypatch.setattr(usage_memos, "count_saved_memos", fail)
    client = make_client()
    client.app.dependency_overrides.pop(get_memo_counter)

    response = client.get(URL)

    assert response.status_code == 503
    assert response.json() == UNAVAILABLE_BODY
    assert "架空の内部情報" not in response.text


def test_memo_count_uses_saved_memo_count(monkeypatch):
    # 保存の上限判定と同じ関数（memos/public.py）の件数を返す
    async def count(user_id):
        return 7

    monkeypatch.setattr(usage_memos, "count_saved_memos", count)
    client = make_client()
    client.app.dependency_overrides.pop(get_memo_counter)

    response = client.get(URL)

    assert response.status_code == 200
    assert response.json()["memo_count"] == 7
