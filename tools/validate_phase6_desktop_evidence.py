from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "phase6"
DEFAULT_MATRIX = OUT_DIR / "desktop_validation_matrix.template.json"
ENV_PROBE = OUT_DIR / "environment_probe.json"
WORD_HARNESS = OUT_DIR / "word_desktop_harness.json"
JSON_OUT = OUT_DIR / "desktop_validation_summary.json"
MD_OUT = OUT_DIR / "desktop_validation_summary.md"

ALLOWED_STATUSES = {"pass", "fail", "blocked", "pending", "not_tested"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_matrix_rows(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for row in rows:
        scenario_id = str(row.get("scenario_id", "")).strip()
        if not scenario_id:
            errors.append("scenario row missing scenario_id")
            continue
        if scenario_id in seen_ids:
            errors.append(f"duplicate scenario_id: {scenario_id}")
        seen_ids.add(scenario_id)
        status = str(row.get("status", "")).strip()
        if status not in ALLOWED_STATUSES:
            errors.append(f"{scenario_id}: invalid status {status!r}")
    return errors


def build_summary() -> dict[str, Any]:
    matrix = load_json(DEFAULT_MATRIX)
    env_probe = load_json(ENV_PROBE)
    word_harness = load_json(WORD_HARNESS)
    rows = matrix["scenarios"]
    errors = validate_matrix_rows(rows)

    status_counts: dict[str, int] = {status: 0 for status in sorted(ALLOWED_STATUSES)}
    required_outstanding: list[str] = []
    for row in rows:
        status = row["status"]
        status_counts[status] += 1
        if row.get("required_for_phase_close") and status != "pass":
            required_outstanding.append(row["scenario_id"])

    if errors:
        overall_status = "invalid"
    elif required_outstanding:
        overall_status = "blocked"
    else:
        overall_status = "closed"

    return {
        "generated_on": "2026-08-14",
        "overall_status": overall_status,
        "status_counts": status_counts,
        "required_outstanding": required_outstanding,
        "validation_errors": errors,
        "environment_probe": {
            "word_com_available": env_probe.get("word_com", {}).get("available", False),
            "explorer_available": bool(env_probe.get("explorer_executable")),
            "active_smb_mapping_count": len(env_probe.get("active_smb_mappings", [])),
            "disconnected_smb_mapping_count": len(env_probe.get("disconnected_smb_mappings", [])),
            "tailscale_available": bool(env_probe.get("tailscale_executable")),
        },
        "word_harness": {
            "document_updated_text_verified": word_harness.get("document_updated_text_verified", False),
            "lock_behavior_observed": word_harness.get("lock_behavior_observed", False),
            "second_open_read_only": word_harness.get("second_open_read_only"),
            "second_open_error": word_harness.get("second_open_error"),
        },
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 6 Desktop Validation Summary",
        "",
        f"- Overall status: `{summary['overall_status']}`",
        f"- Required outstanding scenarios: `{len(summary['required_outstanding'])}`",
        f"- Validation errors: `{len(summary['validation_errors'])}`",
        "",
        "## Environment",
        "",
        f"- Word COM available: `{summary['environment_probe']['word_com_available']}`",
        f"- Explorer available: `{summary['environment_probe']['explorer_available']}`",
        f"- Active SMB mappings: `{summary['environment_probe']['active_smb_mapping_count']}`",
        f"- Disconnected SMB mappings: `{summary['environment_probe']['disconnected_smb_mapping_count']}`",
        f"- Tailscale available: `{summary['environment_probe']['tailscale_available']}`",
        "",
        "## Local Word Harness",
        "",
        f"- Updated text verified: `{summary['word_harness']['document_updated_text_verified']}`",
        f"- Lock behavior observed: `{summary['word_harness']['lock_behavior_observed']}`",
        f"- Second open read-only: `{summary['word_harness']['second_open_read_only']}`",
        f"- Second open error: `{summary['word_harness']['second_open_error']}`",
        "",
        "## Outstanding Required Scenarios",
        "",
    ]
    if not summary["required_outstanding"]:
        lines.append("- none")
    else:
        for scenario_id in summary["required_outstanding"]:
            lines.append(f"- `{scenario_id}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = build_summary()
    JSON_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(summary), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
