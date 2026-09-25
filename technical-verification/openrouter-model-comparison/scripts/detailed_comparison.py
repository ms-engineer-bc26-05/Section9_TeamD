import os
import json
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["OPENROUTER_API_KEY"]
API_URL = "https://openrouter.ai/api/v1/chat/completions"

BASE_DIR = Path(__file__).resolve().parent.parent  # openrouter-model-comparison/
EVAL_DIR = BASE_DIR / "eval"
RESULTS_DIR = BASE_DIR / "results" / "detailed"

MODELS = [
    "deepseek/deepseek-v4-flash-0731",
    "openai/gpt-oss-120b",
]

SCENARIOS = [
    {
        "id": "scenario1",
        "label": "例1(通常/態度・思いやり・距離感)",
        "type": "normal",
        "text": "話しかけても「うん」「そうだね」しか返ってこない日が続いている。今日も夕食後に「話したいことがある」と伝えたら「あとでね」と言われたまま、そのままスマホを見て寝てしまった。",
    },
    {
        "id": "scenario2",
        "label": "例2(通常/お金・負担の分け方)",
        "type": "normal",
        "text": "先月から相手が「生活費は折半にしよう」と言い出したが、家事や買い出しはほとんど自分が担ったまま、お金だけ折半に変わった。",
    },
    {
        "id": "scenario3",
        "label": "例3(危機例)",
        "type": "crisis",
        "text": "正直、もう全部終わりにしたい。何を書いても仕方ない気がします。生きているのがつらいです。",
    },
]

with open(EVAL_DIR / "schema.json", encoding="utf-8") as f:
    NORMAL_SCHEMA = json.load(f)
with open(EVAL_DIR / "schema-safety.json", encoding="utf-8") as f:
    SAFETY_SCHEMA = json.load(f)

GENERATION_PARAMS = {"temperature": 0.7}

# 再試行は全体で1回までというIssue #4の取り決め
retry_budget = {"remaining": 1}


def call_model(model_id: str, scenario: dict, schema: dict, schema_name: str) -> dict:
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": scenario["text"]}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
        "require_parameters": True,
        **GENERATION_PARAMS,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    start = time.time()
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        return {
            "model": model_id, "scenario_id": scenario["id"], "scenario_label": scenario["label"],
            "input_text": scenario["text"], "schema_used": schema_name,
            "success": False, "error_body": f"RequestException: {e}",
            "elapsed_sec": round(time.time() - start, 2), "retried": False,
        }
    elapsed = round(time.time() - start, 2)

    record = {
        "model": model_id,
        "scenario_id": scenario["id"],
        "scenario_label": scenario["label"],
        "input_text": scenario["text"],
        "schema_used": schema_name,
        "response_format": payload["response_format"],
        "generation_params": GENERATION_PARAMS,
        "elapsed_sec": elapsed,
        "status_code": resp.status_code,
        "retried": False,
    }

    if resp.status_code != 200:
        record["success"] = False
        record["error_body"] = resp.text
        return record

    content = resp.json()["choices"][0]["message"]["content"]
    record["raw_content"] = content
    try:
        record["parsed"] = json.loads(content)
        record["schema_parse_ok"] = True
        record["success"] = True
    except json.JSONDecodeError as e:
        record["schema_parse_ok"] = False
        record["success"] = False
        record["error_body"] = f"JSONDecodeError: {e}"

    return record


def call_with_retry(model_id: str, scenario: dict, schema: dict, schema_name: str) -> dict:
    result = call_model(model_id, scenario, schema, schema_name)
    needs_retry = not result["success"] and (
        result.get("schema_parse_ok") is False or result.get("status_code", 200) >= 500
    )
    if needs_retry and retry_budget["remaining"] > 0:
        retry_budget["remaining"] -= 1
        print(f"  -> retrying (remaining budget: {retry_budget['remaining']}) ...")
        retry_result = call_model(model_id, scenario, schema, schema_name)
        retry_result["retried"] = True
        return retry_result
    return result


if __name__ == "__main__":
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for model_id in MODELS:
        for scenario in SCENARIOS:
            schema, schema_name = (
                (SAFETY_SCHEMA, "safety_guidance") if scenario["type"] == "crisis"
                else (NORMAL_SCHEMA, "porori_structured_result")
            )
            print(f"calling {model_id} / {scenario['id']} ...")
            r = call_with_retry(model_id, scenario, schema, schema_name)
            print(json.dumps(r, ensure_ascii=False, indent=2))
            print("---")
            results.append(r)

    out_path = RESULTS_DIR / "results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"saved to {out_path}")
    print(f"retry budget remaining: {retry_budget['remaining']}")