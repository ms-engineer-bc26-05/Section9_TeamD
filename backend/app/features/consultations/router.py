"""相談API（docs/api-design.md 6.2〜6.5の正常系）。

- Routerの登録（main.py）は結合Issue（I-06）で行う
- 認証は I-01 の get_current_user に置き換えるまで、仮の依存（常に401）を使う
- 相談機能の例外は、このRouterの中で設計書3.5の形式のエラーへ変換する
  （共通の errors.py・main.py を変更しないため、Routerごとの APIRoute で変換する）
- エラーの本文・ログに、相談内容やAIの出力を含めない
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.features.consultations.ai_schemas import AIOutputInvalid
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
from app.features.consultations.service import (
    ConsultationService,
    ConsultationStateConflict,
    can_ask_more,
    correction_limit_reached,
)
from app.features.consultations.state import ConsultationState
from app.features.consultations.store import (
    ConsultationBusy,
    ConsultationNotFound,
    ConsultationStore,
    get_consultation_store,
)
from app.integrations.openrouter.client import AIClientError, OpenRouterClient, get_ai_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 認証（I-01完了までの仮の依存）
# ---------------------------------------------------------------------------


class NotAuthenticated(Exception):
    pass


async def get_current_user_id() -> UUID:
    """I-01の Depends(get_current_user) の current_user.user_id へ置き換える。

    置き換えるまでは常に401とし、誤って結合しても認証なしで使えないようにする。
    テストでは dependency_overrides で固定UUIDを返す。
    """
    raise NotAuthenticated


# ---------------------------------------------------------------------------
# 例外 → 設計書3.5の形式のエラー
# ---------------------------------------------------------------------------

_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    NotAuthenticated: (401, "UNAUTHORIZED", "ログインしてください。"),
    ConsultationNotFound: (
        404,
        "CONSULTATION_NOT_FOUND",
        "相談が見つかりません。最初からやり直してください。",
    ),
    ConsultationBusy: (409, "CONSULTATION_BUSY", "前の操作を処理しています。"),
    ConsultationStateConflict: (
        409,
        "CONSULTATION_STATE_CONFLICT",
        "現在の相談の状態では、この操作はできません。",
    ),
    AIClientError: (502, "AI_UNAVAILABLE", "AIの応答を取得できませんでした。"),
    AIOutputInvalid: (502, "AI_OUTPUT_INVALID", "AIの応答を取得できませんでした。"),
}


def _error_response(exc: Exception) -> JSONResponse | None:
    for exc_type, (status_code, code, message) in _ERRORS.items():
        if isinstance(exc, exc_type):
            # 例外の種類だけを記録し、メッセージ（内容）は出さない
            logger.info("consultation api error: %s", code)
            return JSONResponse(
                status_code=status_code,
                content={"error": {"code": code, "message": message}},
            )
    return None


class ConsultationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except Exception as exc:
                response = _error_response(exc)
                if response is None:
                    raise
                return response

        return route_handler


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
) -> ConsultationView:
    """相談を開始し、最初の質問を返す（6.2.1）"""
    state = await service.start(user_id, body.theme, body.detail)
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
    """相談の状態を取得する（6.2.2）"""
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
            status=state.status, ai_response=ai_response, ai_question=state.ai_question
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
        return ConsultationView(status=state.status, ai_question=state.ai_question)
    if state.status is ConsultationStatus.RESULT_READY:
        return ConsultationView(status=state.status)
    return _view(state)


@router.get("/{consultation_id}/result", response_model=ConsultationResultView)
async def get_result(
    consultation_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationResultView:
    """整理結果の取得（6.4.1）"""
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
