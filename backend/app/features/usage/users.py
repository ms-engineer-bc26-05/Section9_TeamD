"""相談開始時のユーザー状態の確認（Issue #57 質問⑨・#92）。

回数を加算したあとに、ユーザーの状態をDBからもう一度取得する（加算前の認証結果は使い回さない）。
退会処理（F-06）と同時に相談が開始された場合に、退会後のキーを残さないための確認。

状態の取得は、#47（I-01）の users/service.py の get_user_status を使う（#92でもえさんと合意）。
- get_user_status は状態の取得だけを行う。セッションはここで開き、閉じる（読むだけなのでcommitしない）
- ユーザーがいない（None）とDBエラーは区別する
  - None：退会完了で内部ユーザーが物理削除されている（ABSENT）
  - DBの接続障害：UserStatusUnavailable（503 DB_UNAVAILABLE。加算した1回は戻す）
  - それ以外の例外：#47と同じく、そのまま上へ送る（加算した1回は consultation_gate で戻す）
"""

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_session_factory
from app.core.database_errors import is_database_connection_error
from app.core.exceptions import DatabaseUnavailableError
from app.features.usage.exceptions import UserStatusUnavailable
from app.features.users.service import get_user_status


class UserStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"
    ABSENT = "absent"  # 退会完了で内部ユーザーが物理削除されている


class UserStatusChecker(Protocol):
    async def get_status(self, user_id: UUID) -> UserStatus:
        """DBから現在の状態を取得する。確認できない場合は UserStatusUnavailable を送出する"""
        ...


# users.status の値（DBの制約 status_allowed）→ 利用回数側の状態
_STATUSES = {
    "active": UserStatus.ACTIVE,
    "deleting": UserStatus.DELETING,
}


class DbUserStatusChecker:
    """DBの users.status から状態を取得する"""

    def __init__(
        self,
        session_factory: Callable[[], async_sessionmaker[AsyncSession]] = get_session_factory,
    ) -> None:
        # import時にDBへ接続しないよう、作り方（関数）を持ち、確認のたびに呼ぶ
        self._session_factory = session_factory

    async def get_status(self, user_id: UUID) -> UserStatus:
        try:
            async with self._session_factory()() as session:
                status = await get_user_status(session, user_id)
        except DatabaseUnavailableError:
            # 新しい接続を作る処理のタイムアウト（app.core.database）
            raise UserStatusUnavailable from None
        except Exception as error:
            if is_database_connection_error(error):
                # DBの例外のメッセージは接続情報を含みうるため、from None で捨てる
                raise UserStatusUnavailable from None
            raise

        if status is None:
            return UserStatus.ABSENT
        try:
            return _STATUSES[status]
        except KeyError:
            # 想定外の値。#47（auth/service.py）と同じく、推測せずに止める
            raise RuntimeError("Unexpected account status") from None


_checker = DbUserStatusChecker()


def get_user_status_checker() -> UserStatusChecker:
    return _checker
