from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE6_DIR = ROOT / "artifacts" / "phase6"
MATRIX_PATH = PHASE6_DIR / "desktop_validation_matrix.template.json"
ENV_PATH = PHASE6_DIR / "environment_probe.json"
HARNESS_PATH = PHASE6_DIR / "word_desktop_harness.json"
SUMMARY_PATH = PHASE6_DIR / "desktop_validation_summary.json"
OUT_DIR = ROOT / "artifacts" / "phase6b"
JSON_OUT = OUT_DIR / "desktop_operator_pack.json"
CSV_OUT = OUT_DIR / "desktop_operator_pack.csv"
MD_OUT = OUT_DIR / "desktop_operator_pack.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_execution_notes(scenario_id: str) -> str:
    notes = {
        "private_share_mapping_active": "Capture active mapped path, remote share, and screenshot of successful access.",
        "explorer_navigation_private_share": "Open approved scratch/test folder in Explorer and capture screenshot of folder path.",
        "word_open_existing_doc_private_share": "Open an existing DOCX from the private share in Word and capture screenshot plus observed open mode.",
        "word_direct_save_private_share": "Edit the private-share DOCX and save directly in Word without manual upload/download; capture screenshot and saved timestamp.",
        "office_wifi_single_user": "Run single-user Explorer and Word open/save on office Wi-Fi.",
        "hotspot_single_user": "Run the same single-user path on hotspot/mobile network.",
        "disconnect_during_open": "Interrupt network during document open and record visible behavior plus recovery prompt or error.",
        "disconnect_during_save": "Interrupt network during save and record save result, error behavior, and file aftermath.",
        "reconnect_after_disconnect": "Reconnect and verify share/document access recovers as expected.",
        "two_user_lock_contention_private_share": "Use two desktop sessions on the same DOCX and record lock/read-only/save conflict behavior.",
    }
    return notes.get(scenario_id, "Capture execution evidence and outcome.")


def required_evidence_fields(scenario_id: str) -> list[str]:
    fields = [
        "operator",
        "executed_on",
        "machine_name",
        "network_mode",
        "share_path",
        "status",
        "notes",
        "evidence_refs",
    ]
    if scenario_id in {"disconnect_during_open", "disconnect_during_save", "reconnect_after_disconnect"}:
        fields.extend(["disconnect_method", "recovery_observed"])
    if scenario_id == "two_user_lock_contention_private_share":
        fields.extend(["user_a", "user_b", "lock_outcome"])
    if scenario_id in {"word_open_existing_doc_private_share", "word_direct_save_private_share"}:
        fields.extend(["document_path", "word_behavior"])
    return fields


def build_operator_pack() -> dict[str, Any]:
    matrix = load_json(MATRIX_PATH)
    env = load_json(ENV_PATH)
    harness = load_json(HARNESS_PATH)
    summary = load_json(SUMMARY_PATH)

    scenario_rows: list[dict[str, Any]] = []
    for row in matrix.get("scenarios", []):
        scenario_id = str(row["scenario_id"])
        if not row.get("required_for_phase_close"):
            continue
        scenario_rows.append(
            {
                "scenario_id": scenario_id,
                "current_status": row["status"],
                "current_notes": row["notes"],
                "execution_notes": scenario_execution_notes(scenario_id),
                "required_evidence_fields": required_evidence_fields(scenario_id),
                "evidence_template": {
                    "operator": "",
                    "executed_on": "",
                    "machine_name": "",
                    "network_mode": "",
                    "share_path": "",
                    "status": "not_started",
                    "notes": "",
                    "evidence_refs": [],
                },
            }
        )

    return {
        "generated_on": "2026-08-16",
        "phase6_status": summary.get("overall_status"),
        "required_outstanding_count": len(summary.get("required_outstanding", [])),
        "environment_snapshot": {
            "word_com_available": env.get("word_com", {}).get("available", False),
            "explorer_available": bool(env.get("explorer_executable")),
            "tailscale_available": bool(env.get("tailscale_executable")),
            "active_smb_mapping_count": len(env.get("active_smb_mappings", [])),
            "disconnected_smb_mapping_count": len(env.get("disconnected_smb_mappings", [])),
            "local_word_harness_verified": harness.get("document_updated_text_verified", False),
        },
        "scenario_rows": scenario_rows,
    }


def write_csv(rows: list[dict[str, Any]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "scenario_id",
                "current_status",
                "current_notes",
                "execution_notes",
                "required_evidence_fields",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "scenario_id": row["scenario_id"],
                    "current_status": row["current_status"],
                    "current_notes": row["current_notes"],
                    "execution_notes": row["execution_notes"],
                    "required_evidence_fields": "; ".join(row["required_evidence_fields"]),
                }
            )


def render_markdown(report: dict[str, Any]) -> str:
    env = report["environment_snapshot"]
    lines = [
        "# Phase 6 Desktop Operator Pack",
        "",
        f"- Generated on: `{report['generated_on']}`",
        f"- Current Phase 6 status: `{report['phase6_status']}`",
        f"- Required outstanding scenarios: `{report['required_outstanding_count']}`",
        "",
        "## Environment Snapshot",
        "",
        f"- Word COM available: `{env['word_com_available']}`",
        f"- Explorer available: `{env['explorer_available']}`",
        f"- Tailscale available: `{env['tailscale_available']}`",
        f"- Active SMB mappings: `{env['active_smb_mapping_count']}`",
        f"- Disconnected SMB mappings: `{env['disconnected_smb_mapping_count']}`",
        f"- Local Word harness verified: `{env['local_word_harness_verified']}`",
        "",
    ]
    for row in report["scenario_rows"]:
        lines.extend(
            [
                f"## {row['scenario_id']}",
                "",
                f"- Current status: `{row['current_status']}`",
                f"- Current notes: {row['current_notes']}",
                f"- Execution notes: {row['execution_notes']}",
                f"- Required evidence fields: `{', '.join(row['required_evidence_fields'])}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_operator_pack()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report["scenario_rows"])
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
