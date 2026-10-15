"""相談開始時のユーザー状態の確認（Issue #57 質問⑨）。

回数を加算したあとに、ユーザーの状態をDBからもう一度取得する（加算前の認証結果は使い回さない）。
退会処理（F-06）と同時に相談が開始された場合に、退会後のキーを残さないための確認。

状態を取得する本物の関数（配置・引数・DBセッションの扱い）は、#47（I-01）のマージ後に
もえさんと相談して決める。それまでは、誤って結合しても確認なしで相談を開始できないよう、
常に UserStatusUnavailable とする（仮の認証が常に401なのと同じ考え方）。
"""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.features.usage.exceptions import UserStatusUnavailable


class UserStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"
    ABSENT = "absent"  # 退会完了で内部ユーザーが物理削除されている


class UserStatusChecker(Protocol):
    async def get_status(self, user_id: UUID) -> UserStatus:
        """DBから現在の状態を取得する。確認できない場合は UserStatusUnavailable を送出する"""
        ...


class PendingUserStatusChecker:
    """本物の関数につなぐまでの仮実装。常に確認できない扱いにする"""

    async def get_status(self, user_id: UUID) -> UserStatus:
        raise UserStatusUnavailable


_checker = PendingUserStatusChecker()


def get_user_status_checker() -> UserStatusChecker:
    return _checker
