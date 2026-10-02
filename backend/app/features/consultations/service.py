"""相談の状態を進めるService。

- 状態の更新は store.locked() の中で行い、同じ相談への同時更新を防ぐ
- AIを呼ぶ処理では、AIの呼び出しと出力の検証が成功してから状態を書き換える
  （失敗した場合は、訂正回数なども含めて状態を変えない）
- AIの出力は表示用の文字列・整理結果の一次案としてだけ使い、権限判定やDB操作には使わない

I-03Aでは正常系を実装する。次はI-03Bで実装する：
- 質問回数・訂正回数・往復回数の上限に達したときの強制遷移と409
- 安全案内の固定文言・危機の判定方法
- TTL・DELETE・ユーザー単位の破棄
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from app.features.consultations import prompts
from app.features.consultations.ai_schemas import (
    EMOTION,
    EVENT_DIALOGUE,
    FIRST_QUESTION,
    GUIDED_DIALOGUE,
    AIOutputInvalid,
    AIOutputKind,
    parse_ai_output,
)
from app.features.consultations.prompts import PromptStage
from app.features.consultations.schemas import (
    ApprovableResult,
    ConsultationResultInput,
    ConsultationStatus,
    EmotionInput,
    EventDetailsDraft,
    EventDetailsInput,
    HandlingType,
    SafetyGuidance,
    SafetyGuidanceDraft,
    ThemeCategory,
)
from app.features.consultations.state import ConsultationState, utc_now
from app.features.consultations.store import (
    ConsultationNotFound,
    ConsultationStore,
)
from app.integrations.openrouter.client import OpenRouterClient

# 上限値（設計書6.3.1・6.3.2）。上限到達時の強制遷移と409はI-03Bで実装する
QUESTION_LIMIT = 3
CORRECTION_LIMIT = 2

# 安全案内の仮の固定文言。I-03B（Q-09）で、確認済みの相談窓口の案内に差し替える
SAFETY_MESSAGE_PLACEHOLDER = "（仮）安全案内の文言はI-03Bで確定します。"

# 整理結果を返せる状態
RESULT_STATUSES = {
    ConsultationStatus.RESULT_READY,
    ConsultationStatus.HANDLING_SELECTION,
    ConsultationStatus.SAVE_CONFIRMATION,
}


class ConsultationStateConflict(Exception):
    """相談の状態と操作が矛盾している（APIでは409）"""


@dataclass(frozen=True)
class ApprovedConsultation:
    """I-05（保存）へ渡す承認済みの結果。一時状態から切り離したコピー"""

    consultation_id: UUID
    result: ApprovableResult
    approved_at: datetime
    handling: HandlingType


def can_ask_more(state: ConsultationState) -> bool:
    return state.question_count < QUESTION_LIMIT and not correction_limit_reached(state)


def correction_limit_reached(state: ConsultationState) -> bool:
    return state.correction_count >= CORRECTION_LIMIT


def _normalize_safety(draft: SafetyGuidanceDraft | None) -> SafetyGuidance:
    # AIの生成文（draft.safety_message）は使わず、固定文言へ差し替える（設計書4.5）
    return SafetyGuidance(
        risk_detected=True,
        safety_message=SAFETY_MESSAGE_PLACEHOLDER,
        continued_normal_structuring=False,
    )


def _apply_safety(state: ConsultationState, draft: SafetyGuidanceDraft | None) -> None:
    state.clear_content()
    state.safety_guidance = _normalize_safety(draft)
    state.status = ConsultationStatus.SAFETY_GUIDANCE


def _require_status(state: ConsultationState, *allowed: ConsultationStatus) -> None:
    if state.status not in allowed:
        raise ConsultationStateConflict


class ConsultationService:
    def __init__(self, store: ConsultationStore, ai_client: OpenRouterClient) -> None:
        self._store = store
        self._ai = ai_client

    async def _call_ai(self, definition, state, stage, history, **progress):
        model, schema, schema_name = definition
        messages = prompts.build_messages(stage, state.theme, history, **progress)
        result = await self._ai.complete_json(messages, schema, schema_name)
        return parse_ai_output(model, result.content)

    def _ensure_still_exists(self, state: ConsultationState) -> None:
        # AIの応答待ちの間に破棄された相談へは書き込まない（DELETEとの競合の網羅はI-03B）
        if not self._store.exists(state.user_id, state.consultation_id):
            raise ConsultationNotFound

    # ------------------------------------------------------------------
    # 相談開始・状態取得
    # ------------------------------------------------------------------

    async def start(self, user_id: UUID, theme: ThemeCategory, detail: str) -> ConsultationState:
        state = ConsultationState(
            consultation_id=uuid4(),
            user_id=user_id,
            theme=theme,
            status=ConsultationStatus.EVENT_DIALOGUE,
        )
        history = [prompts.user_turn(detail)]
        output = await self._call_ai(FIRST_QUESTION, state, PromptStage.FIRST_QUESTION, history)

        if output.kind is AIOutputKind.SAFETY:
            _apply_safety(state, output.safety)
        else:
            state.messages = [*history, prompts.assistant_turn(output.ai_question)]
            state.ai_question = output.ai_question
        # AIの呼び出しが成功してから登録する（失敗時に空の相談を残さない）
        self._store.add(state)
        return state

    def get(self, user_id: UUID, consultation_id: UUID) -> ConsultationState:
        # GETでは最終操作時刻を更新しない（設計書7章）
        return self._store.get(user_id, consultation_id)

    # ------------------------------------------------------------------
    # 出来事の対話・訂正（6.3.1）
    # ------------------------------------------------------------------

    async def event_dialogue(
        self,
        user_id: UUID,
        consultation_id: UUID,
        action: Literal["answer", "correct"],
        text: str,
    ) -> ConsultationState:
        async with self._store.locked(user_id, consultation_id) as state:
            _require_status(state, ConsultationStatus.EVENT_DIALOGUE)

            new_turn = prompts.user_turn(text)
            if action == "answer":
                stage = PromptStage.EVENT_ANSWER
                answer_count = state.question_count + 1
            else:
                stage = PromptStage.EVENT_CORRECTION
                answer_count = state.question_count
            output = await self._call_ai(
                EVENT_DIALOGUE,
                state,
                stage,
                [*state.messages, new_turn],
                answer_count=answer_count,
            )
            self._ensure_still_exists(state)

            if output.kind is AIOutputKind.SAFETY:
                _apply_safety(state, output.safety)
                state.touch()
                return state

            # AIの呼び出しが成功した時点で回数を確定する
            if action == "answer":
                state.question_count += 1
            else:
                state.correction_count += 1
            state.messages.append(new_turn)

            if output.next_action == "ask":
                state.ai_understanding = output.ai_understanding
                state.ai_question = output.ai_question
                state.messages.append(
                    prompts.assistant_turn(f"{output.ai_understanding}\n{output.ai_question}")
                )
            else:
                self._set_event_summary(state, output.event_details)
            state.touch()
            return state

    def _set_event_summary(self, state: ConsultationState, details: EventDetailsDraft) -> None:
        state.event_details = details
        state.ai_understanding = None
        state.ai_question = None
        state.status = ConsultationStatus.EVENT_SUMMARY_READY
        state.messages.append(
            prompts.assistant_turn(
                "出来事の要約\n"
                f"何があったか：{details.what_happened}\n"
                f"何が気になったか：{details.what_bothered_me}"
            )
        )

    # ------------------------------------------------------------------
    # 出来事要約の確認・編集（6.3.2）
    # ------------------------------------------------------------------

    async def confirm_event_summary(
        self,
        user_id: UUID,
        consultation_id: UUID,
        action: Literal["proceed", "ask_more"],
        event_details: EventDetailsInput | None = None,
    ) -> ConsultationState:
        async with self._store.locked(user_id, consultation_id) as state:
            _require_status(state, ConsultationStatus.EVENT_SUMMARY_READY)

            if action == "proceed":
                if event_details is not None:
                    # 本人が直接編集した要約を採用する
                    state.event_details = EventDetailsDraft(**event_details.model_dump())
                    state.messages.append(prompts.event_details_turn(event_details))
                state.status = ConsultationStatus.EMOTION_SELECTION
                state.touch()
                return state

            if not can_ask_more(state):
                raise ConsultationStateConflict
            output = await self._call_ai(
                EVENT_DIALOGUE,
                state,
                PromptStage.EVENT_ASK_MORE,
                state.messages,
                answer_count=state.question_count,
            )
            self._ensure_still_exists(state)

            if output.kind is AIOutputKind.SAFETY:
                _apply_safety(state, output.safety)
            elif output.next_action != "ask":
                # 追加の質問を求めたのに質問が返らない場合は、AIの出力不正として扱う
                raise AIOutputInvalid("追加の質問がありません")
            else:
                state.ai_understanding = output.ai_understanding
                state.ai_question = output.ai_question
                state.messages.append(prompts.assistant_turn(output.ai_question))
                state.status = ConsultationStatus.EVENT_DIALOGUE
            state.touch()
            return state

    # ------------------------------------------------------------------
    # 感情（6.3.3）
    # ------------------------------------------------------------------

    async def submit_emotion(
        self, user_id: UUID, consultation_id: UUID, emotion: EmotionInput
    ) -> tuple[ConsultationState, str | None]:
        """感情を受け付ける。戻り値の2つ目は受け止めの一言（ai_response）"""
        async with self._store.locked(user_id, consultation_id) as state:
            _require_status(state, ConsultationStatus.EMOTION_SELECTION)

            new_turn = prompts.emotion_turn(emotion)
            output = await self._call_ai(
                EMOTION,
                state,
                PromptStage.EMOTION,
                [*state.messages, new_turn],
                answer_count=state.question_count,
            )
            self._ensure_still_exists(state)

            if output.kind is AIOutputKind.SAFETY:
                _apply_safety(state, output.safety)
                state.touch()
                return state, None

            state.emotion = emotion
            state.ai_question = output.ai_question
            state.messages.extend(
                [new_turn, prompts.assistant_turn(f"{output.ai_response}\n{output.ai_question}")]
            )
            state.status = ConsultationStatus.GUIDED_DIALOGUE
            state.touch()
            return state, output.ai_response

    # ------------------------------------------------------------------
    # 本音・背景・望み（6.3.4）
    # ------------------------------------------------------------------

    async def guided_dialogue(
        self,
        user_id: UUID,
        consultation_id: UUID,
        answer: str | None,
        skipped: bool,
    ) -> ConsultationState:
        async with self._store.locked(user_id, consultation_id) as state:
            _require_status(state, ConsultationStatus.GUIDED_DIALOGUE)

            new_turn = prompts.user_turn(prompts.SKIPPED_ANSWER_TEXT if skipped else answer)
            output = await self._call_ai(
                GUIDED_DIALOGUE,
                state,
                PromptStage.GUIDED,
                [*state.messages, new_turn],
                answer_count=state.question_count,
                guided_turn_count=state.guided_turn_count + 1,
            )
            self._ensure_still_exists(state)

            if output.kind is AIOutputKind.SAFETY:
                _apply_safety(state, output.safety)
                state.touch()
                return state

            state.guided_turn_count += 1
            state.messages.append(new_turn)
            if output.next_action == "ask":
                state.ai_question = output.ai_question
                state.messages.append(prompts.assistant_turn(output.ai_question))
            else:
                state.result = output.result
                state.ai_question = None
                state.status = ConsultationStatus.RESULT_READY
            state.touch()
            return state

    # ------------------------------------------------------------------
    # 整理結果の確認・編集・承認（6.4）
    # ------------------------------------------------------------------

    def get_result(self, user_id: UUID, consultation_id: UUID) -> ConsultationState:
        state = self._store.get(user_id, consultation_id)
        _require_status(state, *RESULT_STATUSES)
        return state

    async def update_result(
        self, user_id: UUID, consultation_id: UUID, changes: ConsultationResultInput
    ) -> ConsultationState:
        async with self._store.locked(user_id, consultation_id) as state:
            _require_status(state, ConsultationStatus.RESULT_READY)
            if state.approved:
                raise ConsultationStateConflict
            state.result = state.result.model_copy(update=changes.model_dump(exclude_unset=True))
            state.touch()
            return state

    async def approve_result(self, user_id: UUID, consultation_id: UUID) -> ConsultationState:
        async with self._store.locked(user_id, consultation_id) as state:
            _require_status(state, ConsultationStatus.RESULT_READY)
            if state.approved:
                raise ConsultationStateConflict
            try:
                approvable = ApprovableResult(**state.result.model_dump())
            except ValueError:
                # 必須項目が空のまま承認しようとした（入力値ではなく状態の矛盾として409）
                raise ConsultationStateConflict from None
            state.approved_result = approvable
            state.approved_at = utc_now()
            state.status = ConsultationStatus.HANDLING_SELECTION
            state.touch()
            return state

    # ------------------------------------------------------------------
    # 扱い方（6.5.1）
    # ------------------------------------------------------------------

    async def choose_handling(
        self, user_id: UUID, consultation_id: UUID, handling: HandlingType
    ) -> ConsultationState:
        async with self._store.locked(user_id, consultation_id) as state:
            # 画面9から画面8へ戻っての選び直しも受け付ける
            _require_status(
                state,
                ConsultationStatus.HANDLING_SELECTION,
                ConsultationStatus.SAVE_CONFIRMATION,
            )
            if not state.approved:
                raise ConsultationStateConflict
            state.handling = handling
            state.status = ConsultationStatus.SAVE_CONFIRMATION
            state.touch()
            return state


# ----------------------------------------------------------------------
# I-05（保存）へ公開するService関数
# ----------------------------------------------------------------------


def get_approved_result(
    store: ConsultationStore, user_id: UUID, consultation_id: UUID
) -> ApprovedConsultation:
    """承認済みの結果を取得する。

    - 状態がない・本人のものでない → ConsultationNotFound（404）
    - 未承認・扱い方が未選択      → ConsultationStateConflict（409）
    """
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
        result=state.approved_result.model_copy(deep=True),
        approved_at=state.approved_at,
        handling=state.handling,
    )


def discard_consultation(store: ConsultationStore, user_id: UUID, consultation_id: UUID) -> None:
    """保存成功後に一時状態を破棄する。何度呼んでも安全"""
    store.discard(user_id, consultation_id)
