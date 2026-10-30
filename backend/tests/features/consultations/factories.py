"""テスト用に、相談の一時状態を直接作るヘルパー。

AIを呼ばずに、I-05（保存）などのテストを進めるために使う。テストデータはすべて架空。

使い方（I-05のテスト）：
    from app.features.consultations.store import ConsultationStore
    from tests.features.consultations.factories import make_save_confirmation_state

    store = ConsultationStore()
    state = make_save_confirmation_state(store, user_id)
    approved = await get_approved_result(user_id, state.consultation_id, store=store)
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.features.consultations.schemas import (
    ApprovableResult,
    ConsultationResultDraft,
    ConsultationStatus,
    HandlingType,
    ThemeCategory,
)
from app.features.consultations.state import ConsultationState
from app.features.consultations.store import ConsultationStore

FICTIONAL_RESULT = {
    "event_summary": "架空の出来事の要約",
    "emotion": "架空の感情",
    "true_feeling": "架空の本音",
    "background": "",
    "wish": "架空の望み",
}


def make_save_confirmation_state(
    store: ConsultationStore,
    user_id: UUID | None = None,
    *,
    handling: HandlingType = HandlingType.HOLD,
    approved_at: datetime | None = None,
    **result_overrides: str,
) -> ConsultationState:
    """承認済み・扱い方選択済み（save_confirmation）の一時状態を作り、ストアへ登録する"""
    result = {**FICTIONAL_RESULT, **result_overrides}
    state = ConsultationState(
        consultation_id=uuid4(),
        user_id=user_id or uuid4(),
        theme=ThemeCategory.COMMUNICATION,
        status=ConsultationStatus.SAVE_CONFIRMATION,
        result=ConsultationResultDraft(**result),
        approved_result=ApprovableResult(**result),
        approved_at=approved_at or datetime.now(UTC),
        handling=handling,
    )
    store.add(state)
    return state
