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
        {"kind": "normal", "ai_question": "架空", "safety": SAFETY},
        {"kind": "safety", "ai_question": "架空", "safety": SAFETY},
        {"kind": "safety", "ai_question": None, "safety": None},
        {"kind": "other", "ai_question": "架空", "safety": None},
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
        _event(kind="safety", safety=SAFETY),  # safetyなのに通常の項目がある
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
