import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["OPENROUTER_API_KEY"]
API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "deepseek/deepseek-v4-flash-0731",
    "z-ai/glm-4.7-flash",
    "openai/gpt-5-nano",
    "openai/gpt-oss-120b",
    "google/gemma-4-26b-a4b-it",
]

CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok"]},
        "message": {"type": "string"},
    },
    "required": ["status", "message"],
    "additionalProperties": False,
}

def check_model(model_id: str) -> dict:
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "接続確認です。statusに'ok'、messageに短い挨拶を入れたJSONだけを返してください。"}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "first_check", "strict": True, "schema": CHECK_SCHEMA},
        },
        "require_parameters": True,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    start = time.time()
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    elapsed = round(time.time() - start, 2)

    if resp.status_code != 200:
        return {"model": model_id, "success": False, "elapsed_sec": elapsed,
                "status_code": resp.status_code, "error_body": resp.text}

    content = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return {"model": model_id, "success": True, "elapsed_sec": elapsed,
            "raw_content": content, "parsed": parsed}

if __name__ == "__main__":
    results = []
    for m in MODELS:
        print(f"checking {m} ...")
        r = check_model(m)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print("---")
        results.append(r)

    with open("results/first-check/results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("saved to results/first-check/results.json")