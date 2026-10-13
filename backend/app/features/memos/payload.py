"""暗号化して保存するメモの中身と、その復号・検証。

保存（I-05 #52）と、一覧・詳細（F-01 #55）の両方から使う。
本文・鍵・暗号文をログ・例外のメッセージに含めない。
"""

from typing import Literal
from uuid import UUID

from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, ValidationError

from app.features.memos.crypto import MemoEncryptionError, decrypt_payload
from app.features.memos.repository import StoredMemo

# 暗号化の方式・鍵・復号後のデータ構造の版（DB設計 approved_memos）
ENCRYPTION_VERSION = "fernet-v1"
# MVPでは鍵のローテーションを行わないため固定。本番鍵管理は対象外（Issue #52）
KEY_VERSION = "v1"
PAYLOAD_VERSION = 1

# 扱い方（API設計書4.4）。保存する内容とAPIのレスポンスで同じ型を使う
MemoHandling = Literal["tell", "hold", "not_tell"]


class MemoPayload(BaseModel):
    """暗号化して保存する内容（payload_version=1）。復号後もこの形で検証する"""

    model_config = ConfigDict(extra="forbid")

    event_summary: str
    emotion: str
    true_feeling: str
    background: str
    wish: str
    handling: MemoHandling
    reason: str | None


def decrypt_memo(stored: StoredMemo, user_id: UUID, cipher: Fernet) -> MemoPayload:
    """保存済みの行を復号し、中身を検証して返す。

    版が違う・復号できない・user_id やメモIDと結び付かない・中身の形が違う場合は、
    原因を区別せず MemoEncryptionError を送出する（APIでは500）。
    """
    if stored.payload_version != PAYLOAD_VERSION:
        raise MemoEncryptionError("Memo payload version is not supported")
    # 別のユーザー・別のメモの行へ移された暗号文は、ここで復号・照合に失敗する
    data = decrypt_payload(
        stored.encrypted_payload,
        user_id=user_id,
        memo_id=stored.id,
        cipher=cipher,
    )
    try:
        return MemoPayload.model_validate(data)
    except ValidationError:
        raise MemoEncryptionError("Memo payload is invalid") from None
