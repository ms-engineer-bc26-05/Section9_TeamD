"""AI出力Schemaのテスト。AIの出力例はすべて架空。"""

import pytest

from app.features.consultations.ai_schemas import (
    EMOTION,
    EVENT_DIALOGUE,
    FIRST_QUESTION,
    GUIDED_DIALOGUE,
    AIOutputInvalid,
    AIOutputKind,
    EventDialogueAIOutput,
    FirstQuestionAIOutput,
    GuidedDialogueAIOutput,
    SafetyOutput,
    parse_ai_output,
)

SAFETY = {
    "risk_detected": True,
    "safety_message": "架空のAI生成文",
    "continued_normal_structuring": False,
}
EVENT_DETAILS = {"what_happened": "架空の出来事", "what_bothered_me": "架空の気がかり"}
RESULT = {
    "event_summary": "架空の出来事",
    "emotion": "架空の感情",
    "true_feeling": "架空の本音",
    "background": "",
    "wish": "架空の望み",
}


# --- AIへ渡すJSON SchemaとPydanticモデルの整合 --------------------------------


def _assert_strict(schema):
    """strictモードの条件：全項目required・additionalProperties=false（入れ子も含む）"""
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            _assert_strict(sub)
        return
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        for sub in schema["properties"].values():
            _assert_strict(sub)


@pytest.mark.parametrize("definition", [FIRST_QUESTION, EVENT_DIALOGUE, EMOTION, GUIDED_DIALOGUE])
def test_json_schema_is_strict_and_matches_model(definition):
    model, schema, _ = definition
    _assert_strict(schema)
    assert set(schema["properties"]) == set(model.model_fields)


# --- ① 相談開始 -----------------------------------------------------------------


def test_first_question_normal():
    output = parse_ai_output(
        FirstQuestionAIOutput,
        {"kind": "normal", "ai_question": "架空の質問", "safety": None},
    )
    assert output.kind is AIOutputKind.NORMAL


def test_first_question_safety():
    output = parse_ai_output(
        FirstQuestionAIOutput,
        {"kind": "safety", "ai_question": None, "safety": SAFETY},
    )
    assert output.kind is AIOutputKind.SAFETY


@pytest.mark.parametrize(
    "content",
    [
        {"kind": "normal", "ai_question": None, "safety": None},
        {"kind": "normal", "ai_question": "  ", "safety": None},
        {"kind": "other", "ai_question": "架空", "safety": None},
        # risk_detected が true と読み取れない safety（Q-28：安全案内として扱わない）
        {"kind": "normal", "ai_question": "架空", "safety": {**SAFETY, "risk_detected": False}},
        {"kind": "normal", "ai_question": "架空", "safety": {**SAFETY, "risk_detected": "true"}},
        {"kind": "normal", "ai_question": "架空"},  # 項目の欠落
        {"kind": "normal", "ai_question": "架空", "safety": None, "extra": 1},
        {"kind": "normal", "ai_question": "あ" * 201, "safety": None},
    ],
)
def test_first_question_invalid(content):
    with pytest.raises(AIOutputInvalid):
        parse_ai_output(FirstQuestionAIOutput, content)


# --- ② 出来事の対話 ---------------------------------------------------------------


def _event(**overrides):
    base = {
        "kind": "normal",
        "next_action": "ask",
        "ai_understanding": "架空の理解",
        "ai_question": "架空の質問",
        "event_details": None,
        "safety": None,
    }
    return {**base, **overrides}


def test_event_dialogue_ask_and_summarize():
    assert parse_ai_output(EventDialogueAIOutput, _event()).next_action == "ask"
    summarize = _event(
        next_action="summarize",
        ai_understanding=None,
        ai_question=None,
        event_details=EVENT_DETAILS,
    )
    assert parse_ai_output(EventDialogueAIOutput, summarize).event_details is not None


@pytest.mark.parametrize(
    "content",
    [
        _event(ai_question=None),
        _event(ai_understanding=""),
        _event(event_details=EVENT_DETAILS),
        _event(next_action="summarize"),  # 要約がない
        _event(next_action=None),
    ],
)
def test_event_dialogue_invalid(content):
    with pytest.raises(AIOutputInvalid):
        parse_ai_output(EventDialogueAIOutput, content)


# --- ④ 本音・背景・望み -----------------------------------------------------------


def test_guided_dialogue_complete():
    output = parse_ai_output(
        GuidedDialogueAIOutput,
        {
            "kind": "normal",
            "next_action": "complete",
            "ai_question": None,
            "result": RESULT,
            "safety": None,
        },
    )
    assert output.result.background == ""


def test_invalid_error_does_not_contain_ai_output():
    with pytest.raises(AIOutputInvalid) as exc_info:
        parse_ai_output(
            GuidedDialogueAIOutput,
            {"kind": "normal", "next_action": "ask", "ai_question": "架空の秘密", "result": RESULT, "safety": None},
        )
    assert "架空" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


# --- 安全案内の出力が不正な場合（Q-28。I-03Bで決定） ---------------------------------


@pytest.mark.parametrize(
    ("model", "content"),
    [
        # kind が safety と読み取れれば、ほかの項目が不正でも安全案内
        (FirstQuestionAIOutput, {"kind": "safety", "ai_question": "架空", "safety": SAFETY}),
        (FirstQuestionAIOutput, {"kind": "safety", "ai_question": None, "safety": None}),
        (FirstQuestionAIOutput, {"kind": "safety"}),
        (EventDialogueAIOutput, _event(kind="safety", safety=SAFETY)),
        (
            GuidedDialogueAIOutput,
            {"kind": "safety", "safety": {"risk_detected": True}, "extra": "架空"},
        ),
        # kind が normal でも、risk_detected が true と読み取れれば安全側に倒す
        (FirstQuestionAIOutput, {"kind": "normal", "ai_question": "架空", "safety": SAFETY}),
        (GuidedDialogueAIOutput, {"kind": "other", "safety": {"risk_detected": True}}),
    ],
)
def test_output_with_safety_sign_is_treated_as_safety(model, content):
    output = parse_ai_output(model, content)

    assert isinstance(output, SafetyOutput)
    assert output.kind is AIOutputKind.SAFETY
    assert output.safety is None  # AIが返した safety の中身は使わない
