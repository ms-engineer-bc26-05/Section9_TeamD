"""相談機能が他の機能へ公開する契約。

- I-05（承認済み整理メモの保存）：get_approved_result・discard_consultation
- F-06（退会）：discard_user_consultations（I-03Bで追加）

他の機能からは、このモジュールだけをimportする。
  from app.features.consultations.public import (
      ApprovedConsultation, get_approved_result, discard_consultation,
      discard_user_consultations,
      ConsultationNotFound, ConsultationStateConflict, ConsultationRoute,
  )

- どの関数も相談IDのロックを取らない。そのため、同じ相談の別の処理中でも
  CONSULTATION_BUSY（409）にはならない。
  save_confirmation 状態ではAIを呼ぶ処理がなく、状態の更新は await を挟まずに終わるため、
  1つのイベントループ内では、書き換え途中の状態を読むことはない
- 例外を404・409へ変換するには、Routerに route_class=ConsultationRoute を指定する

テストに限り、次の2つもimportしてよい（AIを通さずに save_confirmation 状態を作るため）。
  from app.features.consultations.store import ConsultationStore
  from tests.features.consultations.factories import make_save_confirmation_state
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.features.consultations.exceptions import (
    ConsultationNotFound,
    ConsultationStateConflict,
)
from app.features.consultations.http_errors import ConsultationRoute
from app.features.consultations.schemas import (
    ApprovableResult,
    ConsultationStatus,
    HandlingType,
)
from app.features.consultations.store import ConsultationStore, get_consultation_store

__all__ = [
    "ApprovedConsultation",
    "ConsultationNotFound",
    "ConsultationRoute",
    "ConsultationStateConflict",
    "discard_consultation",
    "discard_user_consultations",
    "get_approved_result",
]


@dataclass(frozen=True)
class ApprovedConsultation:
    """I-05へ渡す承認済みの結果。一時状態から切り離した、書き換えできないコピー"""

    consultation_id: UUID
    result: ApprovableResult  # frozen（書き換えると例外）
    approved_at: datetime  # タイムゾーン付き（UTC）。TIMESTAMPTZへそのまま保存できる
    handling: HandlingType


async def get_approved_result(
    user_id: UUID,
    consultation_id: UUID,
    *,
    store: ConsultationStore | None = None,
) -> ApprovedConsultation:
    """承認済みの結果を取得する。

    - 状態がない・本人のものでない → ConsultationNotFound（404）
    - 未承認・扱い方が未選択      → ConsultationStateConflict（409）
    """
    store = store or get_consultation_store()
    state = store.get(user_id, consultation_id)
    if (
        state.status is not ConsultationStatus.SAVE_CONFIRMATION
        or state.approved_result is None
        or state.approved_at is None
        or state.handling is None
    ):
        raise ConsultationStateConflict
    return ApprovedConsultation(
        consultation_id=state.consultation_id,
        result=_FrozenApprovableResult(**state.approved_result.model_dump()),
        approved_at=state.approved_at,
        handling=state.handling,
    )


async def discard_consultation(
    user_id: UUID,
    consultation_id: UUID,
    *,
    store: ConsultationStore | None = None,
) -> None:
    """保存成功後に一時状態を破棄する。存在しない・本人のものでない場合も何もせず終わる（冪等）"""
    store = store or get_consultation_store()
    store.discard(user_id, consultation_id)


async def discard_user_consultations(
    user_id: UUID,
    *,
    store: ConsultationStore | None = None,
) -> None:
    """そのユーザーの一時相談をすべて破棄する（F-06：退会処理から呼ぶ）。

    - user_id は、サーバー側で確定した内部ユーザーのID（CurrentUser.user_id）を渡す
    - 他のユーザーの一時状態には影響しない
    - 対象がない・すでに破棄済みの場合も、正常に終了する（何度呼んでも安全）
    - AIの応答待ち中の相談も待たずに破棄し、その処理は応答後に書き込まず404となる
    - 相談の開始処理中だった場合も、AIの応答後に新しい相談を登録しない
    想定外の失敗が起きた場合の扱い・再試行は、F-06（#60）で決める。
    """
    store = store or get_consultation_store()
    store.discard_user(user_id)


class _FrozenApprovableResult(ApprovableResult):
    """ApprovableResult の書き換えできない版（I-05へ渡すコピー用）"""

    model_config = {**ApprovableResult.model_config, "frozen": True}
