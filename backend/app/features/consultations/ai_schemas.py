"""AIの出力Schema（AIへ渡すJSON Schemaと、受け取った出力の検証）。

AIを呼ぶ場面ごとにSchemaを分け、どの場面でも kind（normal／safety）を必須にする。
OpenAI系モデルのstrictモードに合わせて、全項目を required とし、使わない項目は null にする。
項目の組み合わせ（例：ask なのに ai_question が null）はPydanticで検証し、不正な場合は
AIOutputInvalid（APIでは502）とする。

ただし、安全案内を示す印（kind="safety"、または safety.risk_detected=true）を読み取れる場合は、
ほかの項目が不正でも安全案内（SafetyOutput）として扱う（Q-28。I-03Bで決定）。
安全案内の文言はもともとAIの出力を使わず固定文言に差し替えるため、印だけを使えば安全に案内できる。

AIへ渡すJSON Schemaは、strictモードで対応が分かれるキーワード（maxLength・default等）を使わず、
型・必須・列挙値・additionalPropertiesだけで書く。文字数はPydantic側で検証する。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.features.consultations.schemas import (
    ConsultationResultDraft,
    EventDetailsDraft,
    SafetyGuidanceDraft,
)

QUESTION_MAX_LENGTH = 200
UNDERSTANDING_MAX_LENGTH = 300
RESPONSE_MAX_LENGTH = 200


class AIOutputKind(str, Enum):
    NORMAL = "normal"  # 通常の出力
    SAFETY = "safety"  # 安全案内


class AIOutputInvalid(Exception):
    """AIの出力がSchemaを満たさない（APIでは502）。メッセージにAIの出力を含めない"""


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


class _AIOutputBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AIOutputKind
    safety: SafetyGuidanceDraft | None


# ---------------------------------------------------------------------------
# ① 相談開始：最初の質問
# ---------------------------------------------------------------------------


class FirstQuestionAIOutput(_AIOutputBase):
    ai_question: str | None = Field(max_length=QUESTION_MAX_LENGTH)

    @model_validator(mode="after")
    def check_combination(self) -> "FirstQuestionAIOutput":
        if self.kind is AIOutputKind.NORMAL:
            if _is_blank(self.ai_question) or self.safety is not None:
                raise ValueError("normalの項目が不正です")
        elif self.safety is None or self.ai_question is not None:
            raise ValueError("safetyの項目が不正です")
        return self


# ---------------------------------------------------------------------------
# ② 出来事の対話：理解と次の質問、または要約完成
# ---------------------------------------------------------------------------


class EventDialogueAIOutput(_AIOutputBase):
    next_action: Literal["ask", "summarize"] | None
    ai_understanding: str | None = Field(max_length=UNDERSTANDING_MAX_LENGTH)
    ai_question: str | None = Field(max_length=QUESTION_MAX_LENGTH)
    event_details: EventDetailsDraft | None

    @model_validator(mode="after")
    def check_combination(self) -> "EventDialogueAIOutput":
        if self.kind is AIOutputKind.SAFETY:
            if self.safety is None or any(
                v is not None
                for v in (
                    self.next_action,
                    self.ai_understanding,
                    self.ai_question,
                    self.event_details,
                )
            ):
                raise ValueError("safetyの項目が不正です")
            return self

        if self.safety is not None:
            raise ValueError("normalの項目が不正です")
        if self.next_action == "ask":
            # ask_more（追加質問）では理解を使わないが、AIには毎回返させて形を揃える
            if (
                _is_blank(self.ai_understanding)
                or _is_blank(self.ai_question)
                or self.event_details is not None
            ):
                raise ValueError("askの項目が不正です")
        elif self.next_action == "summarize":
            if (
                self.event_details is None
                or self.ai_understanding is not None
                or self.ai_question is not None
            ):
                raise ValueError("summarizeの項目が不正です")
        else:
            raise ValueError("next_actionがありません")
        return self


# ---------------------------------------------------------------------------
# ③ 感情入力の後：受け止めと、本音を聞く最初の質問
# ---------------------------------------------------------------------------


class EmotionAIOutput(_AIOutputBase):
    ai_response: str | None = Field(max_length=RESPONSE_MAX_LENGTH)
    ai_question: str | None = Field(max_length=QUESTION_MAX_LENGTH)

    @model_validator(mode="after")
    def check_combination(self) -> "EmotionAIOutput":
        if self.kind is AIOutputKind.NORMAL:
            if (
                _is_blank(self.ai_response)
                or _is_blank(self.ai_question)
                or self.safety is not None
            ):
                raise ValueError("normalの項目が不正です")
        elif self.safety is None or self.ai_response is not None or self.ai_question is not None:
            raise ValueError("safetyの項目が不正です")
        return self


# ---------------------------------------------------------------------------
# ④ 本音・背景・望み：次の質問、または整理完了
# ---------------------------------------------------------------------------


class GuidedDialogueAIOutput(_AIOutputBase):
    next_action: Literal["ask", "complete"] | None
    ai_question: str | None = Field(max_length=QUESTION_MAX_LENGTH)
    result: ConsultationResultDraft | None

    @model_validator(mode="after")
    def check_combination(self) -> "GuidedDialogueAIOutput":
        if self.kind is AIOutputKind.SAFETY:
            if self.safety is None or any(
                v is not None for v in (self.next_action, self.ai_question, self.result)
            ):
                raise ValueError("safetyの項目が不正です")
            return self

        if self.safety is not None:
            raise ValueError("normalの項目が不正です")
        if self.next_action == "ask":
            if _is_blank(self.ai_question) or self.result is not None:
                raise ValueError("askの項目が不正です")
        elif self.next_action == "complete":
            if self.result is None or self.ai_question is not None:
                raise ValueError("completeの項目が不正です")
        else:
            raise ValueError("next_actionがありません")
        return self


# ---------------------------------------------------------------------------
# 検証
# ---------------------------------------------------------------------------

OutputT = TypeVar("OutputT", bound=_AIOutputBase)


@dataclass(frozen=True)
class SafetyOutput:
    """安全案内と判定したAIの出力（Q-28）。

    AIが返した safety の中身（safety_message など）は使わないため、何も持たない。
    呼び出し側は、通常の出力と同じく kind で分岐できる。
    """

    kind: AIOutputKind = AIOutputKind.SAFETY
    safety: None = None


def reads_as_safety(content: dict[str, Any]) -> bool:
    """AIの出力から、安全案内を示す印を読み取れるか（Q-28）。

    - kind が "safety"
    - または safety.risk_detected が true（kind が "normal" でも安全側に倒す）
    値は型まで一致する場合だけ読み取れたとみなす（"true" などの文字列は読み取れない扱い）。
    """
    if content.get("kind") == AIOutputKind.SAFETY.value:
        return True
    safety = content.get("safety")
    return isinstance(safety, dict) and safety.get("risk_detected") is True


def parse_ai_output(model: type[OutputT], content: dict[str, Any]) -> OutputT | SafetyOutput:
    """AIの出力を検証する。

    安全案内を示す印を読み取れる場合は、ほかの項目を検証せずに SafetyOutput を返す（Q-28）。
    PydanticのValidationErrorは入力値（AIの出力）をメッセージに含むため、
    そのまま外へ出さず、内容を含まない AIOutputInvalid に置き換える。
    """
    if reads_as_safety(content):
        return SafetyOutput()
    try:
        return model.model_validate(content)
    except ValidationError:
        raise AIOutputInvalid("AIの出力がSchemaを満たしません") from None


# ---------------------------------------------------------------------------
# AIへ渡すJSON Schema
# ---------------------------------------------------------------------------


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _nullable_enum(values: list[str]) -> dict[str, Any]:
    return {"type": ["string", "null"], "enum": [*values, None]}


_STRING = {"type": "string"}
_NULLABLE_STRING = {"type": ["string", "null"]}
_KIND = {"type": "string", "enum": [k.value for k in AIOutputKind]}
_SAFETY = _nullable(
    _obj(
        {
            "risk_detected": {"type": "boolean"},
            "safety_message": _STRING,
            "continued_normal_structuring": {"type": "boolean"},
        }
    )
)
_EVENT_DETAILS = _nullable(_obj({"what_happened": _STRING, "what_bothered_me": _STRING}))
_RESULT = _nullable(
    _obj(
        {
            "event_summary": _STRING,
            "emotion": _STRING,
            "true_feeling": _STRING,
            "background": _STRING,
            "wish": _STRING,
        }
    )
)

FIRST_QUESTION_SCHEMA = _obj(
    {"kind": _KIND, "ai_question": _NULLABLE_STRING, "safety": _SAFETY}
)
EVENT_DIALOGUE_SCHEMA = _obj(
    {
        "kind": _KIND,
        "next_action": _nullable_enum(["ask", "summarize"]),
        "ai_understanding": _NULLABLE_STRING,
        "ai_question": _NULLABLE_STRING,
        "event_details": _EVENT_DETAILS,
        "safety": _SAFETY,
    }
)
EMOTION_SCHEMA = _obj(
    {
        "kind": _KIND,
        "ai_response": _NULLABLE_STRING,
        "ai_question": _NULLABLE_STRING,
        "safety": _SAFETY,
    }
)
GUIDED_DIALOGUE_SCHEMA = _obj(
    {
        "kind": _KIND,
        "next_action": _nullable_enum(["ask", "complete"]),
        "ai_question": _NULLABLE_STRING,
        "result": _RESULT,
        "safety": _SAFETY,
    }
)

# (Pydanticモデル, AIへ渡すJSON Schema, Schema名) の組
FIRST_QUESTION = (FirstQuestionAIOutput, FIRST_QUESTION_SCHEMA, "porori_first_question")
EVENT_DIALOGUE = (EventDialogueAIOutput, EVENT_DIALOGUE_SCHEMA, "porori_event_dialogue")
EMOTION = (EmotionAIOutput, EMOTION_SCHEMA, "porori_emotion")
GUIDED_DIALOGUE = (GuidedDialogueAIOutput, GUIDED_DIALOGUE_SCHEMA, "porori_guided_dialogue")
