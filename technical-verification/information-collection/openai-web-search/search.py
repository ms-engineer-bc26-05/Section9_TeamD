"""OpenAI APIのWeb検索機能を1回だけ検証するスクリプト。"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

ALLOWED_MODELS = ("gpt-5-nano", "gpt-4o-mini")
SOURCE_URL = "https://mentrecording.jp/snowman/news/"
TIMEOUT_SECONDS = 120.0
MAX_TOOL_CALLS = 8
REQUESTED_ITEMS = 5
RESULT_PATH = Path(__file__).with_name("result.json")
PROMPT = f"""
Web検索を必ず使用してください。
Snow Man公式INFOページ {SOURCE_URL} だけを情報源として、
ページに表示されている最新{REQUESTED_ITEMS}件を上から順に確認してください。

一覧ページだけで判断せず、各記事のリンク先も開いて確認してください。
一覧ページと最新{REQUESTED_ITEMS}件の詳細ページ以外の、
無関係な過去記事や特設ページは開かないでください。
urlには、各記事の詳細ページの完全なURL
（https://mentrecording.jp/snowman/news/detail.php?id=...）を入れてください。

各記事について、次の3項目を公式ページの表記どおりに返してください。
- published_date: 公開日
- title: タイトル
- url: 記事詳細ページのURL

確認できない内容は推測せず、nullにしてください。
回答は説明文やMarkdownを付けず、次の形のJSONだけにしてください。
{{"items": [{{"published_date": "...", "title": "...", "url": "..."}}]}}
""".strip()


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を読み取る。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=ALLOWED_MODELS, default="gpt-5-nano")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="指定した場合だけOpenAI APIへ1回リクエストする",
    )
    return parser.parse_args()


def load_api_key() -> bool:
    """スクリプトと同じフォルダの.envを読み、キーの有無だけを返す。"""
    load_dotenv(Path(__file__).with_name(".env"))
    return bool(os.getenv("OPENAI_API_KEY"))


def error_result(model: str, error: OpenAIError) -> dict[str, Any]:
    """秘密値や入力内容を含めず、エラーの種類だけを返す。"""
    return {
        "model": model,
        "status": "error",
        "error_class": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "code": getattr(error, "code", None),
        "param": getattr(error, "param", None),
    }


def collect_source_urls(response: Any) -> list[str]:
    """Web検索が参照したSnow Man公式サイトのURLだけを取り出す。"""
    urls: list[str] = []

    for item in response.output:
        if item.type != "web_search_call":
            continue

        action = getattr(item, "action", None)
        for source in getattr(action, "sources", None) or []:
            url = getattr(source, "url", None)
            if (
                isinstance(url, str)
                and url.startswith("https://mentrecording.jp/")
                and url not in urls
            ):
                urls.append(url)

    return urls


def parse_items(output_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """モデルが返したJSONからitemsを取り出し、失敗理由も記録する。"""
    try:
        parsed = json.loads(output_text)
    except json.JSONDecodeError:
        return [], ["モデルの回答をJSONとして解析できませんでした。"]

    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return [], ["モデルの回答にitems配列がありませんでした。"]

    return items, []


def load_result_log() -> dict[str, Any]:
    """既存の検証履歴を読み、読み込めない場合は空の履歴を返す。"""
    try:
        result_log = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        result_log = {}

    attempts = result_log.get("attempts")
    if not isinstance(attempts, list):
        attempts = []

    return {
        "artist": "Snow Man",
        "source_url": SOURCE_URL,
        "method": "openai-web-search",
        "attempts": attempts,
    }


def append_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    """APIキーを含まない1回分の結果を検証履歴へ追記する。"""
    result_log = load_result_log()
    attempt["attempt_number"] = len(result_log["attempts"]) + 1
    result_log["attempts"].append(attempt)
    RESULT_PATH.write_text(
        json.dumps(result_log, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return attempt


def save_success_result(
    model: str, response: Any, output_types: list[str]
) -> dict[str, Any]:
    """成功した検証結果を履歴へ保存する。"""
    items, errors = parse_items(response.output_text)
    return append_attempt(
        {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "status": "success",
            "requested_items": REQUESTED_ITEMS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_tool_calls": MAX_TOOL_CALLS,
            "max_retries": 0,
            "used_web_search": "web_search_call" in output_types,
            "source_urls": collect_source_urls(response),
            "items": items,
            "errors": errors,
            "notes": [
                "モデル回答のitemsと、Web検索が参照したsource_urlsは別々に評価する。"
            ],
        }
    )


def save_error_result(model: str, error: OpenAIError) -> dict[str, Any]:
    """秘密値や例外メッセージを含めず、失敗結果を履歴へ保存する。"""
    public_error = error_result(model, error)
    return append_attempt(
        {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            **public_error,
            "requested_items": REQUESTED_ITEMS,
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_tool_calls": MAX_TOOL_CALLS,
            "max_retries": 0,
            "notes": ["APIキー、入力内容、例外メッセージは保存していない。"],
        }
    )


def main() -> None:
    """事前確認、または指定されたモデルで1回だけ検証する。"""
    args = parse_args()

    if not load_api_key():
        print("ERROR: OPENAI_API_KEYを読み込めませんでした。")
        raise SystemExit(1)

    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "dry-run",
                    "model": args.model,
                    "source_url": SOURCE_URL,
                    "api_key": "loaded",
                    "api_request_sent": False,
                    "requested_items": REQUESTED_ITEMS,
                    "timeout_seconds": TIMEOUT_SECONDS,
                    "max_tool_calls": MAX_TOOL_CALLS,
                    "max_retries": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    client = OpenAI(timeout=TIMEOUT_SECONDS, max_retries=0)

    try:
        response = client.responses.create(
            model=args.model,
            tools=[
                {
                    "type": "web_search",
                    "filters": {"allowed_domains": ["mentrecording.jp"]},
                }
            ],
            tool_choice="required",
            max_tool_calls=MAX_TOOL_CALLS,
            include=["web_search_call.action.sources"],
            input=PROMPT,
            store=False,
        )
    except OpenAIError as error:
        saved_error = save_error_result(args.model, error)
        print(json.dumps(saved_error, ensure_ascii=False, indent=2))
        raise SystemExit(1) from None

    output_types = [item.type for item in response.output]
    saved_result = save_success_result(args.model, response, output_types)
    result = {
        "model": args.model,
        "status": "success",
        "used_web_search": "web_search_call" in output_types,
        "output_types": output_types,
        "source_urls": saved_result["source_urls"],
        "saved_to": str(RESULT_PATH),
        "output_text": response.output_text,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
