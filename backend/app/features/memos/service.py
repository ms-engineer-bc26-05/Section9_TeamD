"""承認済み整理メモの保存（docs/api-design.md 6.5.2・DB設計「保存処理」）。

保存の順序：
  1. 保存済みメモを検索する（あれば一時状態を確認せずに返す。保存成功後の再試行に対応する）
  2. 相談機能の public.get_approved_result で、承認済み・扱い方選択済みの結果を取得する
     一時状態がない場合は保存済みメモを再検索する（1の後に別のリクエストが保存・破棄した場合に、
     404ではなく保存済みのメモを返す）
  3. 整理結果・扱い方・理由を暗号化する（暗号文の中に user_id・memo_id を含めて結び付ける）
  4. トランザクション内でユーザー行をロック（ユーザーの存在・status=active を再確認）
     → 保存済みメモを再検索 → INSERT
  5. commit に成功してから、返すメモを復号・照合し、一時状態を破棄する
     （commit に失敗した場合は一時状態を残し、再試行できるようにする）
     破棄だけが失敗しても保存は成功として返す。残った一時状態は、再試行時に既存のメモを返して破棄する

相談機能からは app.features.consultations.public だけをimportする。
本文・鍵・暗号文をログ・例外のメッセージに含めない。
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cryptography.fernet import Fernet

from app.features.consultations.public import (
    ApprovedConsultation,
    ConsultationNotFound,
    discard_consultation,
    get_approved_result,
)
from app.features.memos.crypto import encrypt_payload
from app.features.memos.payload import (
    ENCRYPTION_VERSION,
    KEY_VERSION,
    PAYLOAD_VERSION,
    MemoHandling,
    MemoPayload,
    decrypt_memo,
)
from app.features.memos.repository import (
    DuplicateMemo,
    MemoRepository,
    NewMemo,
    StoredMemo,
)

logger = logging.getLogger(__name__)

GetApproved = Callable[[UUID, UUID], Awaitable[ApprovedConsultation]]
Discard = Callable[[UUID, UUID], Awaitable[None]]

@dataclass(frozen=True)
class SavedMemo:
    memo_id: UUID
    created_at: datetime
    handling: MemoHandling
    reason: str | None
    event_summary: str


class MemoSaveService:
    def __init__(
        self,
        repository: MemoRepository,
        cipher: Fernet,
        *,
        get_approved: GetApproved = get_approved_result,
        discard: Discard = discard_consultation,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._get_approved = get_approved
        self._discard = discard

    async def save(
        self, user_id: UUID, consultation_id: UUID, reason: str | None
    ) -> tuple[SavedMemo, bool]:
        """保存したメモと、新規に作成したかどうかを返す（新規なら201、保存済みなら200）"""
        existing = await self._repository.find_by_consultation(user_id, consultation_id)
        if existing is not None:
            return await self._return_saved(existing, user_id, consultation_id), False

        # 状態がない・本人のものでない → 404、未承認・扱い方未選択 → 409
        try:
            approved = await self._get_approved(user_id, consultation_id)
        except ConsultationNotFound:
            # 最初の検索の後に、別のリクエスト（二度押し・再試行）が保存して一時状態を破棄した
            stored = await self._repository.find_by_consultation(user_id, consultation_id)
            if stored is None:
                raise
            return await self._return_saved(stored, user_id, consultation_id), False
        new_memo = self._build_new_memo(user_id, approved, reason)

        created = False
        try:
            async with self._repository.transaction() as tx:
                # ユーザー不在・active でない場合は例外で抜け、INSERT・一時状態の破棄へ進まない
                await tx.lock_user(user_id)
                stored = await tx.find_by_consultation(user_id, consultation_id)
                if stored is None:
                    # 保存件数の上限（403）はここで判定する。上限値が未定のため未実装
                    stored = await tx.insert(new_memo)
                    created = True
        except DuplicateMemo:
            # 同時リクエストが先に保存した（INSERT・commit のどちらで分かった場合も）。
            # rollback 後に保存済みのメモを取得して返す
            stored = await self._repository.find_by_consultation(user_id, consultation_id)
            if stored is None:
                raise
            created = False

        # commit に成功した後だけ一時状態を破棄する
        return await self._return_saved(stored, user_id, consultation_id), created

    async def _return_saved(
        self, stored: StoredMemo, user_id: UUID, consultation_id: UUID
    ) -> SavedMemo:
        """保存済みのメモを復号・照合してから、一時状態を破棄する。

        復号・照合に失敗した場合は破棄せず、一時状態を残す。
        """
        saved = self._to_saved(stored, user_id)
        await self._discard_after_save(user_id, consultation_id)
        return saved

    async def _discard_after_save(self, user_id: UUID, consultation_id: UUID) -> None:
        """保存済みのメモがある状態で一時状態を破棄する。失敗しても保存の失敗とは扱わない"""
        try:
            await self._discard(user_id, consultation_id)
        except Exception as exc:
            # 例外の種類だけを記録し、メッセージは出さない
            logger.warning("consultation discard failed after memo save: %s", type(exc).__name__)

    def _build_new_memo(
        self, user_id: UUID, approved: ApprovedConsultation, reason: str | None
    ) -> NewMemo:
        memo_id = uuid4()
        payload = MemoPayload(
            **approved.result.model_dump(),
            handling=approved.handling.value,
            reason=reason,
        )
        ciphertext = encrypt_payload(
            payload.model_dump(), user_id=user_id, memo_id=memo_id, cipher=self._cipher
        )
        return NewMemo(
            id=memo_id,
            user_id=user_id,
            source_consultation_id=approved.consultation_id,
            encrypted_payload=ciphertext,
            encryption_version=ENCRYPTION_VERSION,
            key_version=KEY_VERSION,
            payload_version=PAYLOAD_VERSION,
            approved_at=approved.approved_at,
            # 保存同意日時は、このAPIの呼び出し時にサーバー側で設定する
            save_consented_at=datetime.now(UTC),
        )

    def _to_saved(self, stored: StoredMemo, user_id: UUID) -> SavedMemo:
        payload = decrypt_memo(stored, user_id, self._cipher)
        return SavedMemo(
            memo_id=stored.id,
            created_at=stored.created_at,
            handling=payload.handling,
            reason=payload.reason,
            event_summary=payload.event_summary,
        )
