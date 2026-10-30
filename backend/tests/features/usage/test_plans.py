"""利用回数側のプラン判定（DbPlanResolver。#92）のテスト。

DBの代わりに偽物のセッションを使い、plans/public.py の get_current_plan を通して確認する。
- 有料の利用権限の有無を premium / free に変換できること
- 接続障害だけを PlanUnavailable（503）にし、それ以外の例外は上へ送ること
- セッションは開いて閉じるだけで、commitしないこと
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.exceptions import DatabaseUnavailableError
from app.features.plans.public import PlanCode
from app.features.usage import plans
from app.features.usage.exceptions import PlanUnavailable
from app.features.usage.plans import DbPlanResolver
from tests.features.usage.fakes import FakeDbSession

MARKER = "DUMMY_DB_ERROR_MARKER"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def resolver(session: FakeDbSession) -> DbPlanResolver:
    return DbPlanResolver(session.factory, now=lambda: NOW)


@pytest.mark.parametrize(("paid", "expected"), [(True, PlanCode.PREMIUM), (False, PlanCode.FREE)])
async def test_resolves_plan(paid, expected):
    session = FakeDbSession(paid)

    assert await resolver(session).resolve(uuid4()) is expected
    assert len(session.statements) == 1
    assert (session.opened, session.closed, session.commits) == (1, 1, 0)


async def test_uses_current_time():
    session = FakeDbSession(False)

    await resolver(session).resolve(uuid4())

    params = session.statements[0].compile().params
    assert NOW in params.values()


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, ConnectionRefusedError(MARKER)),
        DatabaseUnavailableError(MARKER),
    ],
)
async def test_connection_failure_is_unavailable(error):
    # 無料にも有料にもせず、503にする
    session = FakeDbSession(error=error)

    with pytest.raises(PlanUnavailable) as caught:
        await resolver(session).resolve(uuid4())

    assert MARKER not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    assert session.closed == 1


async def test_other_db_errors_are_not_unavailable():
    # 接続障害でないDBエラーは、無料扱い・503にせず、そのまま上へ送る
    error = ProgrammingError("SELECT", {}, Exception(MARKER))
    session = FakeDbSession(error=error)

    with pytest.raises(ProgrammingError) as caught:
        await resolver(session).resolve(uuid4())

    assert caught.value is error
    assert session.closed == 1


async def test_cancel_is_not_converted():
    session = FakeDbSession(error=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await resolver(session).resolve(uuid4())

    assert session.closed == 1


def test_does_not_connect_on_creation():
    factory = Mock()

    DbPlanResolver(factory)

    factory.assert_not_called()


def test_default_resolver_reads_db():
    assert isinstance(plans.get_plan_resolver(), DbPlanResolver)
