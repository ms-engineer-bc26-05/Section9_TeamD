"""相談APIのリクエスト・レスポンス（docs/api-design.md 6.2〜6.5）。

設計書4章の型（schemas.py）はそのまま使い、ここではAPIの入口・出口の形だけを定義する。
サーバー管理状態（question_count・correction_count・approved・status等）は
リクエストでは受け付けない（extra="forbid"により422）。
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.features.consultations.schemas import (
    ConsultationStatus,
    EmotionCategory,
    EventDetailsDraft,
    EventDetailsInput,
    GuidedTopic,
    HandlingType,
    SafetyGuidance,
    ThemeCategory,
)

# 文字数上限（仮置き。画面設計の確定後に見直す。設計書4章末尾）
DETAIL_MAX_LENGTH = 2000
ANSWER_MAX_LENGTH = 1000


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# リクエスト
# ---------------------------------------------------------------------------


class StartConsultationRequest(_Request):
    """POST /consultations（6.2.1）"""

    theme: ThemeCategory
    detail: str = Field(min_length=1, max_length=DETAIL_MAX_LENGTH)


class EventDialogueRequest(_Request):
    """POST /consultations/{id}/event-dialogue（6.3.1）"""

    action: Literal["answer", "correct"]
    answer: str | None = Field(default=None, min_length=1, max_length=ANSWER_MAX_LENGTH)
    correction_input: str | None = Field(
        default=None, min_length=1, max_length=ANSWER_MAX_LENGTH
    )

    @model_validator(mode="after")
    def check_action(self) -> "EventDialogueRequest":
        if self.action == "answer" and (self.answer is None or self.correction_input is not None):
            raise ValueError("answerだけを指定してください")
        if self.action == "correct" and (
            self.correction_input is None or self.answer is not None
        ):
            raise ValueError("correction_inputだけを指定してください")
        return self

    @property
    def text(self) -> str:
        return self.answer if self.action == "answer" else self.correction_input


class EventSummaryConfirmRequest(_Request):
    """POST /consultations/{id}/event-summary/confirm（6.3.2）"""

    action: Literal["proceed", "ask_more"]
    event_details: EventDetailsInput | None = None  # proceed のときだけ指定できる

    @model_validator(mode="after")
    def check_action(self) -> "EventSummaryConfirmRequest":
        if self.action == "ask_more" and self.event_details is not None:
            raise ValueError("ask_moreではevent_detailsを指定できません")
        return self


class GuidedDialogueRequest(_Request):
    """POST /consultations/{id}/guided-dialogue（6.3.4）。

    「まだ分からない」は skipped=true（Q-13）。背景の質問中だけ指定でき、それ以外は422。
    """

    answer: str | None = Field(default=None, min_length=1, max_length=ANSWER_MAX_LENGTH)
    skipped: bool = False

    @model_validator(mode="after")
    def check_answer_or_skipped(self) -> "GuidedDialogueRequest":
        if self.skipped == (self.answer is not None):
            raise ValueError("answerとskipped=trueのどちらか一方だけを指定してください")
        return self


# ---------------------------------------------------------------------------
# レスポンス（値がない項目は返さない：response_model_exclude_none）
# ---------------------------------------------------------------------------


class ConsultationView(BaseModel):
    """相談の状態と、状態に応じて画面に必要な内容。

    POST /consultations・GET /consultations/{id}・段階的整理の各APIで共通に使う。
    """

    consultation_id: UUID | None = None
    status: ConsultationStatus
    question_count: int | None = None
    can_ask_more: bool | None = None
    correction_count: int | None = None
    correction_limit_reached: bool | None = None
    ai_understanding: str | None = None
    ai_question: str | None = None
    ai_response: str | None = None
    current_topic: GuidedTopic | None = None  # 本音・背景・望みで、いま質問している項目
    event_details: EventDetailsDraft | None = None
    emotion_category: EmotionCategory | None = None
    handling: HandlingType | None = None
    approved: bool | None = None
    safety_guidance: SafetyGuidance | None = None


class ConsultationResultView(BaseModel):
    """GET・PATCH /consultations/{id}/result（6.4.1・6.4.2）"""

    event_summary: str
    emotion: str
    true_feeling: str
    background: str
    wish: str
    approved: bool
