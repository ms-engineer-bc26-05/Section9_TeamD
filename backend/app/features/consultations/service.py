"""相談の状態を進めるService。

- 状態の更新は store.locked() の中で行い、同じ相談への同時更新を防ぐ
- AIを呼ぶ処理では、AIの呼び出しと出力の検証が成功してから状態を書き換える
  （失敗した場合は、訂正回数なども含めて状態を変えない）
- AIの出力は表示用の文字列・整理結果の一次案としてだけ使い、権限判定やDB操作には使わない

回数の上限（I-03B）：
- 出来事の回答は QUESTION_LIMIT 回、訂正は CORRECTION_LIMIT 回まで。上限に達する回は、
  AIへ「要約する」と指定し、要約（event_summary_ready）へ進める。AIが従わない場合は502
- 上限を超える操作は、AIを呼ぶ前に409（CONSULTATION_STATE_CONFLICT）
- 本音・背景・望みは3往復（GUIDED_TOPIC_ORDER）で整理完了（Q-33）
- 上限の確認・AI呼び出し・回数の更新はロックの中で行うため、同時リクエストでも上限を超えない
- 成功したAI呼び出しは1回の相談で最大12回
  （開始1・出来事の回答と訂正あわせて最大4・追加質問最大3・感情1・本音・背景・望み3）

安全案内（I-03B。Q-09・Q-28）：
- 利用者の自由入力をAIへ送る4つの処理（開始・出来事の対話・感情・本音〜望み）では、
  AIを呼ぶ前にキーワードで判定し、該当すればAIを呼ばずに安全案内へ切り替える
- AIが安全案内を示した場合（kind="safety" または risk_detected=true）も切り替える
- 安全案内へ切り替えたら相談内容を消去し、サーバーの固定文言だけを返す
"""

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
from app.features.consultations.safety import (
    SAFETY_MESSAGE,
    contains_crisis_keyword,
    fixed_safety_guidance,
)
from app.features.consultations.exceptions import (
    ConsultationNotFound,
    ConsultationStateConflict,
    GuidedSkipNotAllowed,
    ResultNotReady,
)
from app.features.consultations.prompts import PromptStage
from app.features.consultations.schemas import (
    GUIDED_TOPIC_ORDER,
    ApprovableResult,
    ConsultationResultInput,
    ConsultationStatus,
    EmotionInput,
    EventDetailsDraft,
    EventDetailsInput,
    GuidedTopic,
    HandlingType,
    ThemeCategory,
)
from app.features.consultations.state import ConsultationState, utc_now
from app.features.consultations.store import ConsultationStore
from app.integrations.openrouter.client import OpenRouterClient

# 上限値（設計書6.3.1・6.3.2）
QUESTION_LIMIT = 3
CORRECTION_LIMIT = 2

# 安全案内の固定文言（safety.py で管理する。既存のテストのため、この名前でも参照できるようにする）
SAFETY_MESSAGE_PLACEHOLDER = SAFETY_MESSAGE

# 整理結果を返せる状態
RESULT_STATUSES = {
    ConsultationStatus.RESULT_READY,
    ConsultationStatus.HANDLING_SELECTION,
    ConsultationStatus.SAVE_CONFIRMATION,
}


def can_ask_more(state: ConsultationState) -> bool:
    return state.question_count < QUESTION_LIMIT and not correction_limit_reached(state)


def correction_limit_reached(state: ConsultationState) -> bool:
    return state.correction_count >= CORRECTION_LIMIT


def current_guided_topic(state: ConsultationState) -> GuidedTopic | None:
    """本音・背景・望みの対話で、いま質問している項目（サーバーが回答回数から決める）"""
    if state.status is not ConsultationStatus.GUIDED_DIALOGUE:
        return None
    if state.guided_turn_count >= len(GUIDED_TOPIC_ORDER):
        return None
    return GUIDED_TOPIC_ORDER[state.guided_turn_count]


def _apply_safety(state: ConsultationState) -> None:
    """安全案内へ切り替える。相談内容を消去し、AIの生成文は使わず固定文言を入れる（設計書4.5）"""
    state.clear_content()
    state.safety_guidance = fixed_safety_guidance()
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
        if contains_crisis_keyword(detail):
            # AIを呼ばずに安全案内へ切り替える（Q-09）
            _apply_safety(state)
            self._store.add(state)
            return state

        history = [prompts.user_turn(detail)]
        output = await self._call_ai(FIRST_QUESTION, state, PromptStage.FIRST_QUESTION, history)

        if output.kind is AIOutputKind.SAFETY:
            _apply_safety(state)
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
            if contains_crisis_keyword(text):
                _apply_safety(state)
                state.touch()
                return state

            # 上限を超える操作は、AIを呼ぶ前に拒否する（通常は状態が先に進んでいるため起こらない）
            if action == "answer":
                if state.question_count >= QUESTION_LIMIT:
                    raise ConsultationStateConflict
                stage = PromptStage.EVENT_ANSWER
                answer_count = state.question_count + 1
                # この回答で上限に達する場合は、要約へ進める
                must_summarize = answer_count >= QUESTION_LIMIT
            else:
                if correction_limit_reached(state):
                    raise ConsultationStateConflict
                stage = PromptStage.EVENT_CORRECTION
                answer_count = state.question_count
                # この訂正で上限に達する場合は、訂正を反映した要約へ進める（設計書6.3.1）
                must_summarize = state.correction_count + 1 >= CORRECTION_LIMIT

            new_turn = prompts.user_turn(text)
            output = await self._call_ai(
                EVENT_DIALOGUE,
                state,
                stage,
                [*state.messages, new_turn],
                answer_count=answer_count,
                event_must_summarize=must_summarize,
            )
            self._ensure_still_exists(state)

            if output.kind is AIOutputKind.SAFETY:
                _apply_safety(state)
                state.touch()
                return state

            if must_summarize and output.next_action != "summarize":
                # 上限に達したのに要約が返らない場合は、AIの出力不正として回数を増やさない
                raise AIOutputInvalid("指定と異なる進め方が返されました")

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
                _apply_safety(state)
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
            if contains_crisis_keyword(emotion.detail):
                _apply_safety(state)
                state.touch()
                return state, None

            new_turn = prompts.emotion_turn(emotion)
            output = await self._call_ai(
                EMOTION,
                state,
                PromptStage.EMOTION,
                [*state.messages, new_turn],
                answer_count=state.question_count,
                guided_next_topic=GUIDED_TOPIC_ORDER[0],
            )
            self._ensure_still_exists(state)

            if output.kind is AIOutputKind.SAFETY:
                _apply_safety(state)
                state.touch()
                return state, None

            state.emotion = emotion
            state.guided_turn_count = 0
            state.background_skipped = False
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
        """本音 → 背景 → 望みの順に1問ずつ進める。

        順序と完了のタイミングはサーバーが回答回数から決める（AIの判断より優先する）。
        AIが指定と違う動作（完了の前に complete、完了すべきときに ask）を返した場合は、
        AIの出力不正（502）として状態を変えない。
        """
        async with self._store.locked(user_id, consultation_id) as state:
            _require_status(state, ConsultationStatus.GUIDED_DIALOGUE)
            if contains_crisis_keyword(answer):
                _apply_safety(state)
                state.touch()
                return state
            topic = current_guided_topic(state)
            if topic is None:
                raise ConsultationStateConflict
            if skipped and topic is not GuidedTopic.BACKGROUND:
                # 「まだ分からない」は背景の質問中だけ選べる（画面設計に合わせる）
                raise GuidedSkipNotAllowed

            answered = state.guided_turn_count + 1
            completes = answered >= len(GUIDED_TOPIC_ORDER)
            next_topic = None if completes else GUIDED_TOPIC_ORDER[answered]

            new_turn = prompts.user_turn(prompts.SKIPPED_ANSWER_TEXT if skipped else answer)
            output = await self._call_ai(
                GUIDED_DIALOGUE,
                state,
                PromptStage.GUIDED,
                [*state.messages, new_turn],
                answer_count=state.question_count,
                guided_turn_count=answered,
                guided_next_topic=next_topic,
                guided_complete=completes,
            )
            self._ensure_still_exists(state)

            if output.kind is AIOutputKind.SAFETY:
                _apply_safety(state)
                state.touch()
                return state

            expected = "complete" if completes else "ask"
            if output.next_action != expected:
                raise AIOutputInvalid("指定と異なる進め方が返されました")

            state.guided_turn_count = answered
            if skipped:
                state.background_skipped = True
            state.messages.append(new_turn)
            if completes:
                result = output.result
                if state.background_skipped:
                    # 背景が「まだ分からない」の場合は、AIが補った内容があっても空にする
                    result = result.model_copy(update={"background": ""})
                state.result = result
                state.ai_question = None
                state.status = ConsultationStatus.RESULT_READY
            else:
                state.ai_question = output.ai_question
                state.messages.append(prompts.assistant_turn(output.ai_question))
            state.touch()
            return state

    # ------------------------------------------------------------------
    # 整理結果の確認・編集・承認（6.4）
    # ------------------------------------------------------------------

    def get_result(self, user_id: UUID, consultation_id: UUID) -> ConsultationState:
        state = self._store.get(user_id, consultation_id)
        if state.status in RESULT_STATUSES:
            return state
        if state.status is ConsultationStatus.SAFETY_GUIDANCE:
            # 安全案内へ切り替わった相談には整理結果がない
            raise ConsultationStateConflict
        raise ResultNotReady

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
