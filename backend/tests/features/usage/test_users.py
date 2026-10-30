"""相談開始時のユーザー状態の確認（#92）のテスト。

DBの代わりに偽物のセッションを使い、users/service.py の get_user_status を通して確認する。
- DBの値（'active' / 'deleting' / 行なし）を利用回数側の状態へ変換できること
- ユーザーがいない（None）とDBエラーを区別すること
- 接続障害だけを UserStatusUnavailable（503）にし、それ以外の例外は上へ送ること
- セッションは開いて閉じるだけで、commitしないこと
"""

import asyncio
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.exceptions import DatabaseUnavailableError
from app.features.usage import users
from app.features.usage.exceptions import UserStatusUnavailable
from app.features.usage.users import DbUserStatusChecker, UserStatus
from tests.features.usage.fakes import FakeDbSession

MARKER = "DUMMY_DB_ERROR_MARKER"


@pytest.mark.parametrize(
    ("db_status", "expected"),
    [
        ("active", UserStatus.ACTIVE),
        ("deleting", UserStatus.DELETING),
        (None, UserStatus.ABSENT),  # 退会完了で内部ユーザーの行がない
    ],
)
async def test_converts_db_status(db_status, expected):
    session = FakeDbSession(db_status)

    status = await DbUserStatusChecker(session.factory).get_status(uuid4())

    assert status is expected
    assert len(session.statements) == 1  # 加算後に1回だけ取り直す
    assert (session.opened, session.closed, session.commits) == (1, 1, 0)


async def test_unexpected_status_is_not_guessed():
    # DBの制約で起きないはずの値。#47と同じく、推測せずに止める（503にはしない）
    session = FakeDbSession("unexpected")

    with pytest.raises(RuntimeError, match="Unexpected account status"):
        await DbUserStatusChecker(session.factory).get_status(uuid4())

    assert session.closed == 1


@pytest.mark.parametrize(
    "error",
    [
        # 接続できない（SQLAlchemyに包まれた接続エラー）
        OperationalError("SELECT", {}, ConnectionRefusedError(MARKER)),
        # 新しい接続を作る処理のタイムアウト（app.core.database が送出する）
        DatabaseUnavailableError(MARKER),
    ],
)
async def test_connection_failure_is_unavailable(error):
    session = FakeDbSession(error=error)

    with pytest.raises(UserStatusUnavailable) as caught:
        await DbUserStatusChecker(session.factory).get_status(uuid4())

    # 元の例外のメッセージ（接続情報を含みうる）を引き継がない
    assert MARKER not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    assert session.closed == 1


async def test_other_db_errors_are_not_unavailable():
    # 接続障害でないDBエラーは、ユーザーがいない扱い・503にせず、そのまま上へ送る
    error = ProgrammingError("SELECT", {}, Exception(MARKER))
    session = FakeDbSession(error=error)

    with pytest.raises(ProgrammingError) as caught:
        await DbUserStatusChecker(session.factory).get_status(uuid4())

    assert caught.value is error
    assert session.closed == 1


async def test_cancel_is_not_converted():
    # 応答の取り消しなどの中断は、503に変えずにそのまま伝える（戻す処理は consultation_gate で行う）
    session = FakeDbSession(error=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await DbUserStatusChecker(session.factory).get_status(uuid4())

    assert session.closed == 1


def test_does_not_connect_on_creation():
    # import時・作成時にはDBへ接続しない（確認のたびにセッションを作る）
    factory = Mock()

    DbUserStatusChecker(factory)

    factory.assert_not_called()


def test_default_checker_reads_db():
    assert isinstance(users.get_user_status_checker(), DbUserStatusChecker)
