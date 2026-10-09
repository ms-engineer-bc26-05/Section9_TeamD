"""テスト用のAIクライアント。外部APIへは接続せず、用意した出力を順番に返す。"""

import asyncio
from typing import Any

from app.integrations.openrouter.client import AICallResult, AIClientError


class FakeAIClient:
    def __init__(self, outputs: list[dict[str, Any] | Exception] | None = None) -> None:
        self.outputs = list(outputs or [])
        self.calls: list[dict[str, Any]] = []
        # 設定すると、AIの応答待ちを模してイベントが立つまで待つ
        self.wait_event: asyncio.Event | None = None
        self.started = asyncio.Event()

    def push(self, *outputs: dict[str, Any] | Exception) -> None:
        self.outputs.extend(outputs)

    async def complete_json(self, messages, schema, schema_name) -> AICallResult:
        self.calls.append({"messages": messages, "schema_name": schema_name})
        self.started.set()
        if self.wait_event is not None:
            await self.wait_event.wait()
        if not self.outputs:
            raise AIClientError("テスト用の出力がありません")
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return AICallResult(content=output, model="fake/model", provider="Fake")


# --- AIの出力例（すべて架空） ---------------------------------------------------

SAFETY = {
    "risk_detected": True,
    "safety_message": "架空のAI生成文",
    "continued_normal_structuring": False,
}


def first_question(question="架空の最初の質問"):
    return {"kind": "normal", "ai_question": question, "safety": None}


def event_ask(understanding="架空の理解", question="架空の次の質問"):
    return {
        "kind": "normal",
        "next_action": "ask",
        "ai_understanding": understanding,
        "ai_question": question,
        "event_details": None,
        "safety": None,
    }


def event_summarize():
    return {
        "kind": "normal",
        "next_action": "summarize",
        "ai_understanding": None,
        "ai_question": None,
        "event_details": {"what_happened": "架空の出来事", "what_bothered_me": "架空の気がかり"},
        "safety": None,
    }


def emotion_output():
    return {
        "kind": "normal",
        "ai_response": "架空の受け止め",
        "ai_question": "架空の本音の質問",
        "safety": None,
    }


def guided_ask(question="架空の背景の質問"):
    return {
        "kind": "normal",
        "next_action": "ask",
        "ai_question": question,
        "result": None,
        "safety": None,
    }


def guided_complete(**overrides):
    result = {
        "event_summary": "架空の出来事",
        "emotion": "架空の感情",
        "true_feeling": "架空の本音",
        "background": "",
        "wish": "架空の望み",
    }
    result.update(overrides)
    return {
        "kind": "normal",
        "next_action": "complete",
        "ai_question": None,
        "result": result,
        "safety": None,
    }


def safety_output(**null_fields):
    return {"kind": "safety", "safety": SAFETY, **{k: None for k in null_fields}}
