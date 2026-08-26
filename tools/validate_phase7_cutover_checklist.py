from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "phase7"
CHECKLIST_PATH = OUT_DIR / "cutover_execution_checklist.template.json"
READINESS_PATH = OUT_DIR / "cutover_readiness.json"
JSON_OUT = OUT_DIR / "cutover_checklist_summary.json"
MD_OUT = OUT_DIR / "cutover_checklist_summary.md"

ALLOWED_STATUSES = {"pass", "fail", "blocked", "pending", "not_started"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for row in rows:
        item_id = str(row.get("item_id", "")).strip()
        if not item_id:
            errors.append("checklist row missing item_id")
            continue
        if item_id in seen_ids:
            errors.append(f"duplicate item_id: {item_id}")
        seen_ids.add(item_id)
        status = str(row.get("status", "")).strip()
        if status not in ALLOWED_STATUSES:
            errors.append(f"{item_id}: invalid status {status!r}")
    return errors


def build_summary() -> dict[str, Any]:
    checklist = load_json(CHECKLIST_PATH)
    readiness = load_json(READINESS_PATH)
    rows = checklist["items"]
    errors = validate_rows(rows)

    status_counts = {status: 0 for status in sorted(ALLOWED_STATUSES)}
    required_outstanding: list[str] = []
    for row in rows:
        status = row["status"]
        status_counts[status] += 1
        if row.get("required_for_cutover") and status != "pass":
            required_outstanding.append(row["item_id"])

    if errors:
        overall_status = "invalid"
    elif readiness["phase7_status"] == "blocked":
        overall_status = "blocked"
    elif required_outstanding:
        overall_status = "pending"
    else:
        overall_status = "ready"

    return {
        "generated_on": "2026-08-26",
        "overall_status": overall_status,
        "readiness_status": readiness["phase7_status"],
        "status_counts": status_counts,
        "required_outstanding": required_outstanding,
        "validation_errors": errors,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 7 Cutover Checklist Summary",
        "",
        f"- Overall status: `{summary['overall_status']}`",
        f"- Readiness status: `{summary['readiness_status']}`",
        f"- Required outstanding: `{len(summary['required_outstanding'])}`",
        f"- Validation errors: `{len(summary['validation_errors'])}`",
        "",
        "## Outstanding Required Items",
        "",
    ]
    if not summary["required_outstanding"]:
        lines.append("- none")
    else:
        for item in summary["required_outstanding"]:
            lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = build_summary()
    JSON_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    MD_OUT.write_text(render_markdown(summary), encoding="utf-8", newline="\n")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
