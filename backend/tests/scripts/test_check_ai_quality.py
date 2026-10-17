"""I-07の実API確認スクリプト（scripts/check_ai_quality.py）のテスト。

外部APIへは接続せず、OpenRouterの応答をまねる偽の通信層で、スクリプト全体を最後まで動かす。
回数・金額の上限（Issue #54で合意）で必ず止まることを確認する。テストデータはすべて架空。
"""

import json

import httpx
import pytest

from app.features.consultations.ai_retry import AIRetryPolicy
from scripts import check_ai_quality as script

CRISIS_TEXTS = {text for _, text in script.FICTIONAL_CRISIS}


async def no_sleep(seconds):
    return None


POLICY = AIRetryPolicy(sleep=no_sleep)


def fake_output(body: dict) -> dict:
    """送られたSchema名と指示から、Schemaどおりの架空の出力を作る"""
    name = body["response_format"]["json_schema"]["name"]
    system = body["messages"][0]["content"]
    last_user = body["messages"][-1]["content"]
    if name in ("porori_strict_probe", "porori_first_question"):
        if last_user in CRISIS_TEXTS:
            return {"kind": "safety", "ai_question": None, "safety": None}
        return {"kind": "normal", "ai_question": "架空の質問", "safety": None}
    if name == "porori_event_dialogue":
        return {
            "kind": "normal",
            "next_action": "ask",
            "ai_understanding": "架空の理解",
            "ai_question": "架空の次の質問",
            "event_details": None,
            "safety": None,
        }
    if name == "porori_emotion":
        return {
            "kind": "normal",
            "ai_response": "架空の受け止め",
            "ai_question": "架空の本音の質問",
            "safety": None,
        }
    # サーバーが整理完了を指定したとき（prompts.build_system_prompt の guided_complete）
    if "指定：本音・背景・望みを聞き終えたので、整理を完了する" in system:
        return {
            "kind": "normal",
            "next_action": "complete",
            "ai_question": None,
            "result": {
                "event_summary": "架空",
                "emotion": "架空",
                "true_feeling": "架空",
                "background": "",
                "wish": "架空",
            },
            "safety": None,
        }
    return {
        "kind": "normal",
        "next_action": "ask",
        "ai_question": "架空の背景の質問",
        "result": None,
        "safety": None,
    }


def openrouter_like(cost=0.0001, usage_extra=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, text="架空のエラー本文")
        body = json.loads(request.content)
        usage = {"prompt_tokens": 1000, "completion_tokens": 500, **(usage_extra or {})}
        if cost is not None:
            usage["cost"] = cost
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-oss-120b",
                "provider": "MockProvider",
                "usage": usage,
                "choices": [{"message": {"content": json.dumps(fake_output(body))}}],
            },
        )

    return handler


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def transport_with(handler, **kwargs):
    return script.CountingTransport(inner=httpx.MockTransport(handler), **kwargs)


async def test_runs_all_checks_within_limits(capsys):
    transport = await script.main(transport_with(openrouter_like()), POLICY)

    # A:2 ＋ B:2 ＋ C:5場面×3回 ＝ 19
    assert len(transport.records) == 19
    assert transport.total_cost == pytest.approx(19 * 0.0001)
    assert {r["provider"] for r in transport.records} == {"MockProvider"}
    out = capsys.readouterr().out
    assert "完了：すべての確認が終わりました" in out
    assert "Schemaどおり（strictが効いている）" in out
    assert "安全案内になった" in out
    assert out.count('"result": "OK"') == 15


async def test_records_do_not_include_content():
    transport = await script.main(transport_with(openrouter_like()), POLICY)

    assert "架空" not in json.dumps(transport.records, ensure_ascii=False)


async def test_stops_before_exceeding_request_limit(capsys):
    transport = await script.main(transport_with(openrouter_like(), max_requests=5), POLICY)

    assert len(transport.records) == 5
    assert "最大5リクエストに達しました" in capsys.readouterr().out


async def test_stops_when_cost_limit_is_reached(capsys):
    transport = await script.main(transport_with(openrouter_like(cost=0.05)), POLICY)

    # 2回で$0.10に達し、3回目は送信しない
    assert len(transport.records) == 2
    assert "料金の上限$0.1に達しました" in capsys.readouterr().out


async def test_estimates_cost_when_not_returned():
    transport = transport_with(openrouter_like(cost=None), max_requests=1)
    await script.main(transport, POLICY)

    record = transport.records[0]
    assert record["cost_estimated"] is True
    # 入力1,000×$0.35 ＋ 出力500×$0.75（100万トークンあたり）
    assert record["cost"] == pytest.approx((1000 * 0.35 + 500 * 0.75) / 1_000_000)


async def test_backend_retries_are_counted(capsys):
    # 常に503：A（再試行なし）2回 ＋ B（相談開始で再試行1回）2×2回 ＋ C1-1（再試行1回）2回 ＝ 8回で停止
    transport = await script.main(transport_with(openrouter_like(status=503)), POLICY)

    assert len(transport.records) == 8
    assert all(r["status"] == 503 for r in transport.records)
    out = capsys.readouterr().out
    assert "中断：1-1 相談開始で失敗しました" in out
    assert "架空のエラー本文" not in out


async def test_runs_only_selected_checks(capsys):
    transport = await script.main(
        transport_with(openrouter_like(), max_requests=6), POLICY, checks="C", runs=1
    )

    assert len(transport.records) == 5
    assert all(r["label"].startswith("C:1-") for r in transport.records)
    out = capsys.readouterr().out
    assert "A. strictの確認" not in out
    assert "完了：すべての確認が終わりました" in out


def test_parse_args_defaults():
    args = script.parse_args([])
    assert (args.checks, args.runs, args.max_requests, args.max_cost) == ("ABC", 3, 25, 0.10)


def test_parse_args_for_remaining_budget():
    args = script.parse_args(
        ["--checks", "C", "--runs", "1", "--max-requests", "6", "--max-cost", "0.09"]
    )
    assert (args.checks, args.runs, args.max_requests, args.max_cost) == ("C", 1, 6, 0.09)


@pytest.mark.parametrize(
    "argv",
    [
        ["--max-requests", "26"],  # 合意した25回を超える
        ["--max-cost", "0.2"],  # 合意した$0.10を超える
        ["--checks", "D"],
        ["--checks", ""],
    ],
)
def test_parse_args_rejects_values_beyond_agreement(argv):
    with pytest.raises(SystemExit):
        script.parse_args(argv)


def test_crisis_texts_do_not_match_keywords():
    # キーワードに一致すると、AIを呼ばずに安全案内になり、AIの読み取りの確認にならない
    for _, text in script.FICTIONAL_CRISIS:
        assert not script.contains_crisis_keyword(text)
