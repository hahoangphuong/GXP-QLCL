from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE7_DIR = ROOT / "artifacts" / "phase7"
READINESS_PATH = PHASE7_DIR / "cutover_readiness.json"
CHECKLIST_PATH = PHASE7_DIR / "cutover_execution_checklist.template.json"
CHECKLIST_SUMMARY_PATH = PHASE7_DIR / "cutover_checklist_summary.json"
OUT_DIR = ROOT / "artifacts" / "phase7b"
JSON_OUT = OUT_DIR / "cutover_operational_pack.json"
CSV_OUT = OUT_DIR / "cutover_operational_pack.csv"
MD_OUT = OUT_DIR / "cutover_operational_pack.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def item_execution_notes(item_id: str) -> str:
    notes = {
        "desktop_phase6_complete": "Collect final private-share evidence and rerun Phase 6 validator/final closeout on the office-connected machine.",
        "legacy_write_freeze_window_approved": "Record the approved freeze window, approver, start time, and end time.",
        "legacy_write_freeze_announced": "Send stakeholder notice and archive the exact announcement text plus timestamp.",
        "final_phase2_import_rerun": "Run the final migration import/reconciliation sequence against the frozen legacy baseline and archive outputs.",
        "final_reconciliation_signed_off": "Obtain explicit business/data sign-off on the final reconciliation outputs.",
        "rollback_contacts_confirmed": "Confirm rollback owner, backup contact, and escalation path for the cutover window.",
        "excel_read_only_archive_mode": "Record the exact operational step that moves legacy Excel into read-only/archive mode after go-live.",
    }
    return notes.get(item_id, "Capture operational execution evidence.")


def required_fields(item_id: str) -> list[str]:
    base = ["owner", "status", "executed_on", "notes", "evidence_refs"]
    if item_id == "legacy_write_freeze_window_approved":
        return base + ["approver", "freeze_start", "freeze_end", "approval_ref"]
    if item_id == "legacy_write_freeze_announced":
        return base + ["audience", "announcement_channel", "announcement_ref"]
    if item_id == "final_phase2_import_rerun":
        return base + ["command_refs", "reconciliation_ref", "operator"]
    if item_id == "final_reconciliation_signed_off":
        return base + ["signoff_by", "signoff_ref"]
    if item_id == "rollback_contacts_confirmed":
        return base + ["primary_contact", "backup_contact", "escalation_path"]
    if item_id == "excel_read_only_archive_mode":
        return base + ["archive_owner", "archive_step_ref"]
    if item_id == "desktop_phase6_complete":
        return base + ["phase6_summary_ref"]
    return base


def build_operational_pack() -> dict[str, Any]:
    readiness = load_json(READINESS_PATH)
    checklist = load_json(CHECKLIST_PATH)
    checklist_summary = load_json(CHECKLIST_SUMMARY_PATH)

    items: list[dict[str, Any]] = []
    for row in checklist.get("items", []):
        item_id = str(row["item_id"])
        if row.get("status") == "pass":
            continue
        items.append(
            {
                "item_id": item_id,
                "current_status": row["status"],
                "required_for_cutover": bool(row.get("required_for_cutover")),
                "current_notes": row.get("notes", ""),
                "execution_notes": item_execution_notes(item_id),
                "required_fields": required_fields(item_id),
                "evidence_template": {field: "" if field != "evidence_refs" else [] for field in required_fields(item_id)},
            }
        )

    blocked_gates = [
        gate_name for gate_name, payload in readiness.get("gates", {}).items() if payload.get("status") == "blocked"
    ]

    return {
        "generated_on": "2026-08-16",
        "phase7_status": readiness.get("phase7_status"),
        "checklist_status": checklist_summary.get("overall_status"),
        "blocked_gates": blocked_gates,
        "required_outstanding_count": len(checklist_summary.get("required_outstanding", [])),
        "pending_items": items,
    }


def write_csv(items: list[dict[str, Any]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "item_id",
                "current_status",
                "required_for_cutover",
                "current_notes",
                "execution_notes",
                "required_fields",
            ],
        )
        writer.writeheader()
        for row in items:
            writer.writerow(
                {
                    "item_id": row["item_id"],
                    "current_status": row["current_status"],
                    "required_for_cutover": row["required_for_cutover"],
                    "current_notes": row["current_notes"],
                    "execution_notes": row["execution_notes"],
                    "required_fields": "; ".join(row["required_fields"]),
                }
            )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 7 Operational Pack",
        "",
        f"- Generated on: `{report['generated_on']}`",
        f"- Phase 7 status: `{report['phase7_status']}`",
        f"- Checklist status: `{report['checklist_status']}`",
        f"- Required outstanding count: `{report['required_outstanding_count']}`",
        "",
        "## Blocked Gates",
        "",
    ]
    if report["blocked_gates"]:
        for gate_name in report["blocked_gates"]:
            lines.append(f"- `{gate_name}`")
    else:
        lines.append("- none")

    for item in report["pending_items"]:
        lines.extend(
            [
                "",
                f"## {item['item_id']}",
                "",
                f"- Current status: `{item['current_status']}`",
                f"- Current notes: {item['current_notes']}",
                f"- Execution notes: {item['execution_notes']}",
                f"- Required fields: `{', '.join(item['required_fields'])}`",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_operational_pack()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report["pending_items"])
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
