import json
from pathlib import Path
from jsonschema import Draft202012Validator

BASE_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = BASE_DIR / "eval"
RESULTS_DIR = BASE_DIR / "results"

CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok"]},
        "message": {"type": "string"},
    },
    "required": ["status", "message"],
    "additionalProperties": False,
}

with open(EVAL_DIR / "schema.json", encoding="utf-8") as f:
    NORMAL_SCHEMA = json.load(f)
with open(EVAL_DIR / "schema-safety.json", encoding="utf-8") as f:
    SAFETY_SCHEMA = json.load(f)


def validate_records(records, schema_for_record):
    for r in records:
        if not r.get("success") or "parsed" not in r:
            r["schema_valid"] = None
            r["schema_errors"] = ["skipped: no parsed content (call failed)"]
            continue
        schema = schema_for_record(r)
        errors = list(Draft202012Validator(schema).iter_errors(r["parsed"]))
        r["schema_valid"] = not errors
        r["schema_errors"] = [e.message for e in errors]
    return records


def first_check_schema(_record):
    return CHECK_SCHEMA


def detailed_schema(record):
    return SAFETY_SCHEMA if record.get("scenario_id") == "scenario3" else NORMAL_SCHEMA


if __name__ == "__main__":
    fc_path = RESULTS_DIR / "first-check" / "results.json"
    with open(fc_path, encoding="utf-8") as f:
        fc_records = json.load(f)
    fc_records = validate_records(fc_records, first_check_schema)
    with open(fc_path, "w", encoding="utf-8") as f:
        json.dump(fc_records, f, ensure_ascii=False, indent=2)

    det_path = RESULTS_DIR / "detailed" / "results.json"
    with open(det_path, encoding="utf-8") as f:
        det_records = json.load(f)
    det_records = validate_records(det_records, detailed_schema)
    with open(det_path, "w", encoding="utf-8") as f:
        json.dump(det_records, f, ensure_ascii=False, indent=2)

    all_records = fc_records + det_records
    checked = [r for r in all_records if r.get("schema_valid") is not None]
    print(f"checked: {len(checked)} / valid: {sum(1 for r in checked if r['schema_valid'])}")