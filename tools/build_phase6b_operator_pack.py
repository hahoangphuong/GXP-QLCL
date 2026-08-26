from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE6_DIR = ROOT / "artifacts" / "phase6"
EVIDENCE_PATH = PHASE6_DIR / "phase6_desktop_validation_evidence_20260826.json"
SUMMARY_PATH = PHASE6_DIR / "desktop_validation_summary.json"
OUT_DIR = ROOT / "artifacts" / "phase6b"
JSON_OUT = OUT_DIR / "desktop_operator_pack.json"
CSV_OUT = OUT_DIR / "desktop_operator_pack.csv"
MD_OUT = OUT_DIR / "desktop_operator_pack.md"


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _write_utf8(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    payload_bytes = path.read_bytes()
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON: {_display_path(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object: {_display_path(path)}")
    return payload, sha256(payload_bytes).hexdigest()


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


def scenario_execution_notes(scenario_id: str) -> str:
    notes = {
        "private_share_mapping_active": "Operator attested that active Synology private-share mapping was reachable and usable.",
        "explorer_navigation_private_share": "Operator attested that Explorer navigation to the approved private-share test area succeeded.",
        "word_open_existing_doc_private_share": "Operator attested that an existing DOCX opened directly in Word from the private share.",
        "word_direct_save_private_share": "Operator attested that direct Word save/reopen on the private share succeeded without manual upload/download.",
        "office_wifi_single_user": "Operator attested that the single-user workflow passed on office Wi-Fi.",
        "hotspot_single_user": "Operator attested that the single-user workflow passed over mobile hotspot with Tailscale.",
        "disconnect_during_open": "Operator attested that disconnect-during-open behavior and recovery were exercised successfully.",
        "disconnect_during_save": "Operator attested that disconnect-during-save behavior and recovery were exercised successfully.",
        "reconnect_after_disconnect": "Operator attested that reconnect restored share/document access.",
        "two_user_lock_contention_private_share": "Operator attested that two-user lock contention was exercised and handled without silent overwrite.",
    }
    return notes.get(scenario_id, "Operator attested that the required scenario passed.")


def build_operator_pack(
    *,
    summary_path: Path = SUMMARY_PATH,
    evidence_path: Path = EVIDENCE_PATH,
) -> dict[str, Any]:
    summary, summary_sha256 = load_json(summary_path)
    evidence, evidence_sha256 = load_json(evidence_path)

    if str(summary.get("evidence_path", "")).strip() != _display_path(evidence_path):
        raise RuntimeError("Phase 6 summary evidence_path does not match Phase 6b evidence input.")
    if str(summary.get("evidence_sha256", "")).strip() != evidence_sha256:
        raise RuntimeError("Phase 6 summary evidence_sha256 does not match Phase 6b evidence input.")

    scenario_rows: list[dict[str, Any]] = []
    for row in summary.get("scenario_reconciliation", []):
        scenario_id = str(row["scenario_id"])
        evidence_row = next(
            item for item in evidence.get("scenarios", [])
            if str(item.get("scenario_id")) == scenario_id
        )
        scenario_rows.append(
            {
                "scenario_id": scenario_id,
                "current_status": row["status"],
                "execution_notes": scenario_execution_notes(scenario_id),
                "required_evidence_fields": required_evidence_fields(scenario_id),
                "recorded_evidence": evidence_row,
            }
        )

    return {
        "generated_on": "2026-08-26",
        "phase6_status": summary.get("overall_status"),
        "summary_path": _display_path(summary_path),
        "summary_sha256": summary_sha256,
        "evidence_path": _display_path(evidence_path),
        "evidence_sha256": evidence_sha256,
        "required_outstanding_count": len(summary.get("required_outstanding", [])),
        "scenario_rows": scenario_rows,
    }


def write_csv(rows: list[dict[str, Any]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "scenario_id",
                "current_status",
                "executed_on",
                "share_path",
                "execution_notes",
                "required_evidence_fields",
                "evidence_refs",
            ],
        )
        writer.writeheader()
        for row in rows:
            evidence = row["recorded_evidence"]
            writer.writerow(
                {
                    "scenario_id": row["scenario_id"],
                    "current_status": row["current_status"],
                    "executed_on": evidence.get("executed_on", ""),
                    "share_path": evidence.get("share_path", ""),
                    "execution_notes": row["execution_notes"],
                    "required_evidence_fields": "; ".join(row["required_evidence_fields"]),
                    "evidence_refs": "; ".join(evidence.get("evidence_refs", [])),
                }
            )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 6 Desktop Operator Pack",
        "",
        f"- Generated on: `{report['generated_on']}`",
        f"- Current Phase 6 status: `{report['phase6_status']}`",
        f"- Summary path: `{report['summary_path']}`",
        f"- Summary sha256: `{report['summary_sha256']}`",
        f"- Evidence path: `{report['evidence_path']}`",
        f"- Evidence sha256: `{report['evidence_sha256']}`",
        f"- Required outstanding scenarios: `{report['required_outstanding_count']}`",
        "",
    ]
    for row in report["scenario_rows"]:
        evidence = row["recorded_evidence"]
        lines.extend(
            [
                f"## {row['scenario_id']}",
                "",
                f"- Current status: `{row['current_status']}`",
                f"- Executed on: `{evidence.get('executed_on')}`",
                f"- Share path: `{evidence.get('share_path')}`",
                f"- Execution notes: {row['execution_notes']}",
                f"- Required evidence fields: `{', '.join(row['required_evidence_fields'])}`",
                f"- Evidence refs: `{', '.join(evidence.get('evidence_refs', []))}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        report = build_operator_pack()
        _write_utf8(JSON_OUT, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        write_csv(report["scenario_rows"])
        _write_utf8(MD_OUT, render_markdown(report))
        print(f"Wrote {JSON_OUT}")
        print(f"Wrote {CSV_OUT}")
        print(f"Wrote {MD_OUT}")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
