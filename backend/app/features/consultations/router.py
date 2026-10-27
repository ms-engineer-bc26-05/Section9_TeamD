"""相談API（docs/api-design.md 6.2〜6.5）。

- Routerの登録（main.py）は結合Issue（I-06）で行う
- 認証は I-01 の get_current_user を使い、内部ユーザーIDで一時状態を分離する
- 相談機能の例外は、http_errors.ConsultationRoute で設計書3.5の形式のエラーへ変換する
  （共通の errors.py・main.py を変更しないため、Routerごとの APIRoute で変換する）
- エラーの本文・ログに、相談内容やAIの出力を含めない
- 相談開始では利用回数を判定・加算する（Issue #57。usage.consultation_gate）
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.features.auth.dependencies import get_current_user
from app.features.auth.schemas import CurrentUser
from app.features.consultations.api_schemas import (
    ConsultationResultView,
    ConsultationView,
    EventDialogueRequest,
    EventSummaryConfirmRequest,
    GuidedDialogueRequest,
    StartConsultationRequest,
)
from app.features.consultations.schemas import (
    ConsultationResultInput,
    ConsultationStatus,
    EmotionInput,
    HandlingChoice,
)
from app.features.consultations.http_errors import ConsultationRoute
from app.features.consultations.service import (
    ConsultationService,
    can_ask_more,
    correction_limit_reached,
    current_guided_topic,
)
from app.features.consultations.state import ConsultationState
from app.features.consultations.store import ConsultationStore, get_consultation_store
from app.features.usage.consultation_gate import (
    ConsultationStartGate,
    get_consultation_start_gate,
)
from app.integrations.openrouter.client import OpenRouterClient, get_ai_client


# ---------------------------------------------------------------------------
# 認証
# ---------------------------------------------------------------------------


async def get_current_user_id(
    current_user: CurrentUser = Depends(get_current_user),
) -> UUID:
    """認証済み内部ユーザーのIDを返す。"""
    return current_user.user_id


# ---------------------------------------------------------------------------
# 依存
# ---------------------------------------------------------------------------


def get_consultation_service(
    store: ConsultationStore = Depends(get_consultation_store),
    ai_client: OpenRouterClient = Depends(get_ai_client),
) -> ConsultationService:
    return ConsultationService(store, ai_client)


router = APIRouter(
    prefix="/api/v1/consultations",
    tags=["consultations"],
    route_class=ConsultationRoute,
)

VIEW = {"response_model": ConsultationView, "response_model_exclude_none": True}


# ---------------------------------------------------------------------------
# レスポンスの組み立て
# ---------------------------------------------------------------------------


def _event_counts(state: ConsultationState) -> dict[str, Any]:
    return {
        "question_count": state.question_count,
        "correction_count": state.correction_count,
        "correction_limit_reached": correction_limit_reached(state),
    }


def _view(state: ConsultationState, *, include_id: bool = False) -> ConsultationView:
    """状態に応じて、画面に必要な内容だけを返す（設計書6.2.2）"""
    fields: dict[str, Any] = {"status": state.status}
    if include_id:
        fields["consultation_id"] = state.consultation_id

    match state.status:
        case ConsultationStatus.EVENT_DIALOGUE:
            fields |= _event_counts(state)
            fields |= {"ai_understanding": state.ai_understanding, "ai_question": state.ai_question}
        case ConsultationStatus.EVENT_SUMMARY_READY:
            fields |= _event_counts(state)
            fields |= {"can_ask_more": can_ask_more(state), "event_details": state.event_details}
        case ConsultationStatus.EMOTION_SELECTION:
            fields |= {"event_details": state.event_details}
        case ConsultationStatus.GUIDED_DIALOGUE:
            fields |= {
                "event_details": state.event_details,
                "emotion_category": state.emotion.category if state.emotion else None,
                "ai_question": state.ai_question,
                "current_topic": current_guided_topic(state),
            }
        case ConsultationStatus.RESULT_READY | ConsultationStatus.HANDLING_SELECTION:
            fields |= {"approved": state.approved}
        case ConsultationStatus.SAVE_CONFIRMATION:
            fields |= {"handling": state.handling}
        case ConsultationStatus.SAFETY_GUIDANCE:
            fields |= {"safety_guidance": state.safety_guidance}
    return ConsultationView(**fields)


def _result_view(state: ConsultationState) -> ConsultationResultView:
    result = state.approved_result or state.result
    return ConsultationResultView(**result.model_dump(), approved=state.approved)


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED, **VIEW)
async def start_consultation(
    body: StartConsultationRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
    usage_gate: ConsultationStartGate = Depends(get_consultation_start_gate),
) -> ConsultationView:
    """相談を開始し、最初の質問を返す（6.2.1）。

    利用回数の上限超過は403（USAGE_LIMIT_EXCEEDED）。開始に失敗した場合と、
    開始時に安全案内へ切り替わった場合は、加算した1回を戻す（Issue #57 質問③）
    """
    async with usage_gate.consultation_start(user_id) as ticket:
        state = await service.start(user_id, body.theme, body.detail)
        if state.status is ConsultationStatus.SAFETY_GUIDANCE:
            await ticket.refund()
    if state.status is ConsultationStatus.EVENT_DIALOGUE:
        # 設計書6.2.1のレスポンス例に合わせ、開始時は最初の質問だけを返す
        return ConsultationView(
            consultation_id=state.consultation_id,
            status=state.status,
            ai_question=state.ai_question,
        )
    return _view(state, include_id=True)


@router.get("/{consultation_id}", **VIEW)
async def get_consultation(
    consultation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationView:
    """相談の状態を取得する（6.2.2）。同じ相談の更新を処理中は409（CONSULTATION_BUSY）"""
    return _view(service.get(user_id, consultation_id), include_id=True)


@router.post("/{consultation_id}/event-dialogue", **VIEW)
async def event_dialogue(
    consultation_id: UUID,
    body: EventDialogueRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationView:
    """出来事の対話・訂正（6.3.1）"""
    state = await service.event_dialogue(user_id, consultation_id, body.action, body.text)
    return _view(state)


@router.post("/{consultation_id}/event-summary/confirm", **VIEW)
async def confirm_event_summary(
    consultation_id: UUID,
    body: EventSummaryConfirmRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationView:
    """出来事要約の確認・編集（6.3.2）"""
    state = await service.confirm_event_summary(
        user_id, consultation_id, body.action, body.event_details
    )
    if state.status is ConsultationStatus.EMOTION_SELECTION:
        return ConsultationView(status=state.status)
    if state.status is ConsultationStatus.EVENT_DIALOGUE:
        return ConsultationView(
            status=state.status,
            ai_question=state.ai_question,
            correction_count=state.correction_count,
            correction_limit_reached=correction_limit_reached(state),
        )
    return _view(state)


@router.post("/{consultation_id}/emotion", **VIEW)
async def submit_emotion(
    consultation_id: UUID,
    body: EmotionInput,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationView:
    """感情の選択・具体化（6.3.3）。本音を聞く最初の質問も返す（Q-22 No.2の案）"""
    state, ai_response = await service.submit_emotion(user_id, consultation_id, body)
    if state.status is ConsultationStatus.GUIDED_DIALOGUE:
        return ConsultationView(
            status=state.status,
            ai_response=ai_response,
            ai_question=state.ai_question,
            current_topic=current_guided_topic(state),
        )
    return _view(state)


@router.post("/{consultation_id}/guided-dialogue", **VIEW)
async def guided_dialogue(
    consultation_id: UUID,
    body: GuidedDialogueRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationView:
    """本音・背景・望みの対話（6.3.4）"""
    state = await service.guided_dialogue(user_id, consultation_id, body.answer, body.skipped)
    if state.status is ConsultationStatus.GUIDED_DIALOGUE:
        return ConsultationView(
            status=state.status,
            ai_question=state.ai_question,
            current_topic=current_guided_topic(state),
        )
    if state.status is ConsultationStatus.RESULT_READY:
        return ConsultationView(status=state.status)
    return _view(state)


@router.get("/{consultation_id}/result", response_model=ConsultationResultView)
async def get_result(
    consultation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResultView:
    """整理結果の取得（6.4.1）。同じ相談の更新を処理中は409（CONSULTATION_BUSY）"""
    return _result_view(service.get_result(user_id, consultation_id))


@router.patch("/{consultation_id}/result", response_model=ConsultationResultView)
async def update_result(
    consultation_id: UUID,
    body: ConsultationResultInput,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResultView:
    """整理結果の編集（6.4.2）。編集した項目だけを送る"""
    return _result_view(await service.update_result(user_id, consultation_id, body))


@router.post("/{consultation_id}/result/approve", **VIEW)
async def approve_result(
    consultation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationView:
    """整理結果の承認（6.4.3）"""
    state = await service.approve_result(user_id, consultation_id)
    if state.status is ConsultationStatus.SAFETY_GUIDANCE:
        # 本人が編集した内容から危機的な内容を検知した場合（承認しない）
        return _view(state)
    return ConsultationView(status=state.status, approved=state.approved)


@router.post("/{consultation_id}/handling", **VIEW)
async def choose_handling(
    consultation_id: UUID,
    body: HandlingChoice,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationView:
    """扱い方の選択（6.5.1）"""
    state = await service.choose_handling(user_id, consultation_id, body.handling)
    return ConsultationView(status=state.status)


@router.delete("/{consultation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consultation(
    consultation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> Response:
    """相談の中断・保存せず終了（6.5.3）。

    本人の相談がある場合だけ破棄する。存在しない・破棄済み・本人のものでない場合も
    204を返し、相談の存在や所有者を区別しない（冪等）。
    """
    service.discard(user_id, consultation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
