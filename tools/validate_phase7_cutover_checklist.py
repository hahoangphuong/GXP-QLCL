from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "phase7"
CHECKLIST_PATH = OUT_DIR / "cutover_execution_checklist.template.json"
READINESS_PATH = OUT_DIR / "cutover_readiness.json"
JSON_OUT = OUT_DIR / "cutover_checklist_summary.json"
MD_OUT = OUT_DIR / "cutover_checklist_summary.md"

ALLOWED_STATUSES = {"pass", "fail", "blocked", "pending", "not_started"}
AUTHORITATIVE_ITEM_IDS = {
    "desktop_phase6_complete", "projection_conflicts_resolved",
    "legacy_write_freeze_window_approved", "legacy_write_freeze_announced",
    "final_phase2_import_rerun", "final_reconciliation_signed_off",
    "rollback_contacts_confirmed", "excel_read_only_archive_mode",
}

OPERATIONAL_EVIDENCE_FIELDS = {
    "legacy_write_freeze_window_approved": ("owner", "executed_on", "notes", "approver", "freeze_start", "freeze_end", "approval_ref"),
    "legacy_write_freeze_announced": ("owner", "executed_on", "notes", "audience", "announcement_channel", "announcement_ref"),
    "final_phase2_import_rerun": ("owner", "executed_on", "notes", "reconciliation_ref", "operator"),
    "final_reconciliation_signed_off": ("owner", "executed_on", "notes", "signoff_by", "signoff_ref"),
    "rollback_contacts_confirmed": ("owner", "executed_on", "notes", "primary_contact", "backup_contact", "escalation_path"),
    "excel_read_only_archive_mode": ("owner", "executed_on", "notes", "archive_owner", "archive_step_ref"),
}


def _parse_timestamp(value: str) -> datetime | None:
    try:
        if "T" not in value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except ValueError:
        return None


def _nonblank_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            errors.append("checklist row must be an object")
            continue
        item_id = str(row.get("item_id", "")).strip()
        if not item_id:
            errors.append("checklist row missing item_id")
            continue
        if item_id not in AUTHORITATIVE_ITEM_IDS:
            errors.append(f"unknown item_id: {item_id}")
            continue
        if item_id in seen_ids:
            errors.append(f"duplicate item_id: {item_id}")
        seen_ids.add(item_id)
        status = str(row.get("status", "")).strip()
        if status not in ALLOWED_STATUSES:
            errors.append(f"{item_id}: invalid status {status!r}")
            continue
        if status != "pass" or item_id not in OPERATIONAL_EVIDENCE_FIELDS:
            continue
        for field in OPERATIONAL_EVIDENCE_FIELDS[item_id]:
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(f"{item_id}: missing or invalid {field}")
        if not _nonblank_strings(row.get("evidence_refs")):
            errors.append(f"{item_id}: missing or invalid evidence_refs")
        if item_id == "final_phase2_import_rerun" and not _nonblank_strings(row.get("command_refs")):
            errors.append(f"{item_id}: missing or invalid command_refs")
        parsed = {field: _parse_timestamp(str(row.get(field, ""))) for field in ("executed_on", "freeze_start", "freeze_end") if row.get(field) is not None}
        for field, timestamp in parsed.items():
            if timestamp is None:
                errors.append(f"{item_id}: invalid {field}")
        if parsed.get("freeze_start") and parsed.get("freeze_end") and parsed["freeze_end"] < parsed["freeze_start"]:
            errors.append(f"{item_id}: freeze_end precedes freeze_start")
    missing = AUTHORITATIVE_ITEM_IDS - seen_ids
    for item_id in sorted(missing):
        errors.append(f"missing item_id: {item_id}")
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
