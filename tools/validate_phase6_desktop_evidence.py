from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "artifacts" / "phase6"
DEFAULT_MATRIX = OUT_DIR / "desktop_validation_matrix.template.json"
ENV_PROBE = OUT_DIR / "environment_probe.json"
WORD_HARNESS = OUT_DIR / "word_desktop_harness.json"
EVIDENCE_PATH = OUT_DIR / "phase6_desktop_validation_evidence_20260826.json"
JSON_OUT = OUT_DIR / "desktop_validation_summary.json"
MD_OUT = OUT_DIR / "desktop_validation_summary.md"

ALLOWED_STATUSES = {"pass", "fail", "blocked", "pending", "not_tested"}
COMMON_REQUIRED_FIELDS = [
    "operator",
    "executed_on",
    "machine_name",
    "network_mode",
    "share_path",
    "status",
    "notes",
    "evidence_refs",
]


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


def scenario_specific_required_fields(scenario_id: str) -> list[str]:
    fields: list[str] = []
    if scenario_id in {"word_open_existing_doc_private_share", "word_direct_save_private_share"}:
        fields.extend(["document_path", "word_behavior"])
    if scenario_id in {"disconnect_during_open", "disconnect_during_save", "reconnect_after_disconnect"}:
        fields.extend(["disconnect_method", "recovery_observed"])
    if scenario_id == "two_user_lock_contention_private_share":
        fields.extend(["user_a", "user_b", "lock_outcome"])
    return fields


def required_evidence_fields_for_scenario(scenario_id: str) -> list[str]:
    return COMMON_REQUIRED_FIELDS + scenario_specific_required_fields(scenario_id)


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
        expected_fields = row.get("required_evidence_fields")
        if row.get("required_for_phase_close") and expected_fields is not None:
            if expected_fields != required_evidence_fields_for_scenario(scenario_id):
                errors.append(f"{scenario_id}: required_evidence_fields do not match validator contract")
    return errors


def _scenario_index(
    rows: list[dict[str, Any]],
    *,
    label: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        scenario_id = str(row.get("scenario_id", "")).strip()
        if not scenario_id:
            errors.append(f"{label} row missing scenario_id")
            continue
        if scenario_id in index:
            errors.append(f"duplicate {label} scenario_id: {scenario_id}")
            continue
        index[scenario_id] = row
    return index, errors


def _nonempty_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _validate_evidence_refs(scenario_id: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{scenario_id}: evidence_refs must be a non-empty list")
        return
    for item in value:
        if not _nonempty_text(item):
            errors.append(f"{scenario_id}: evidence_refs must not contain blank entries")
            return


def validate_evidence_against_matrix(
    matrix_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[str], list[str]]:
    errors = validate_matrix_rows(matrix_rows)
    matrix_index, matrix_index_errors = _scenario_index(matrix_rows, label="matrix")
    evidence_index, evidence_index_errors = _scenario_index(evidence_rows, label="evidence")
    errors.extend(matrix_index_errors)
    errors.extend(evidence_index_errors)

    required_matrix_keys = {
        scenario_id
        for scenario_id, row in matrix_index.items()
        if row.get("required_for_phase_close")
    }
    evidence_keys = set(evidence_index)
    missing_required = sorted(required_matrix_keys - evidence_keys)
    extra_unknown = sorted(evidence_keys - set(matrix_index))

    if missing_required:
        errors.append(f"missing required Phase 6 evidence scenarios: {', '.join(missing_required)}")
    if extra_unknown:
        errors.append(f"unknown Phase 6 evidence scenarios: {', '.join(extra_unknown)}")

    reconciled_rows: list[dict[str, Any]] = []
    for scenario_id in sorted(required_matrix_keys):
        matrix_row = matrix_index[scenario_id]
        evidence_row = evidence_index.get(scenario_id)
        if evidence_row is None:
            continue

        if bool(evidence_row.get("required_for_phase_close")) != True:
            errors.append(f"{scenario_id}: evidence row must declare required_for_phase_close=true")

        status = _nonempty_text(evidence_row.get("status"))
        if status not in ALLOWED_STATUSES:
            errors.append(f"{scenario_id}: invalid evidence status {status!r}")
        if status != "pass":
            errors.append(f"{scenario_id}: required scenario must have status 'pass'")

        for field_name in required_evidence_fields_for_scenario(scenario_id):
            if field_name == "evidence_refs":
                _validate_evidence_refs(scenario_id, evidence_row.get(field_name), errors)
                continue
            if not _nonempty_text(evidence_row.get(field_name)):
                errors.append(f"{scenario_id}: missing required evidence field {field_name!r}")

        declared_fields = matrix_row.get("required_evidence_fields")
        if declared_fields is not None and declared_fields != required_evidence_fields_for_scenario(scenario_id):
            errors.append(f"{scenario_id}: matrix required_evidence_fields do not match expected scenario contract")

        if _nonempty_text(evidence_row.get("executed_on")) != "2026-08-26":
            errors.append(f"{scenario_id}: executed_on must be 2026-08-26")

        reconciled_rows.append(
            {
                "scenario_id": scenario_id,
                "status": status,
                "required_for_phase_close": True,
                "matrix_notes": _nonempty_text(matrix_row.get("notes")),
                "evidence": evidence_row,
            }
        )

    return errors, reconciled_rows, missing_required, extra_unknown


def build_summary(
    *,
    matrix_path: Path = DEFAULT_MATRIX,
    evidence_path: Path = EVIDENCE_PATH,
    env_probe_path: Path = ENV_PROBE,
    word_harness_path: Path = WORD_HARNESS,
) -> dict[str, Any]:
    matrix, matrix_sha256 = load_json(matrix_path)
    evidence, evidence_sha256 = load_json(evidence_path)
    env_probe, env_probe_sha256 = load_json(env_probe_path)
    word_harness, word_harness_sha256 = load_json(word_harness_path)

    matrix_rows = matrix.get("scenarios", [])
    evidence_rows = evidence.get("scenarios", [])
    if not isinstance(matrix_rows, list):
        raise RuntimeError("Phase 6 matrix must contain a scenarios list.")
    if not isinstance(evidence_rows, list):
        raise RuntimeError("Phase 6 evidence must contain a scenarios list.")

    errors, reconciled_rows, missing_required, extra_unknown = validate_evidence_against_matrix(
        matrix_rows,
        evidence_rows,
    )

    status_counts: dict[str, int] = {status: 0 for status in sorted(ALLOWED_STATUSES)}
    required_outstanding: list[str] = []
    for row in reconciled_rows:
        status = row["status"]
        status_counts[status] += 1
        if status != "pass":
            required_outstanding.append(row["scenario_id"])

    if errors:
        overall_status = "invalid"
    elif required_outstanding:
        overall_status = "blocked"
    else:
        overall_status = "closed"

    return {
        "generated_on": "2026-08-26",
        "overall_status": overall_status,
        "matrix_path": _display_path(matrix_path),
        "matrix_sha256": matrix_sha256,
        "evidence_path": _display_path(evidence_path),
        "evidence_sha256": evidence_sha256,
        "environment_probe_path": _display_path(env_probe_path),
        "environment_probe_sha256": env_probe_sha256,
        "word_harness_path": _display_path(word_harness_path),
        "word_harness_sha256": word_harness_sha256,
        "operator_attested_source": _nonempty_text(evidence.get("source")),
        "evidence_status": _nonempty_text(evidence.get("evidence_status")),
        "required_scenario_count": len(reconciled_rows),
        "required_pass_count": status_counts["pass"],
        "required_fail_count": status_counts["fail"],
        "required_blocked_count": status_counts["blocked"],
        "required_pending_count": status_counts["pending"],
        "required_not_tested_count": status_counts["not_tested"],
        "required_outstanding": required_outstanding,
        "missing_required_scenarios": missing_required,
        "extra_unknown_scenarios": extra_unknown,
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
        "scenario_reconciliation": [
            {
                "scenario_id": row["scenario_id"],
                "status": row["status"],
                "executed_on": row["evidence"]["executed_on"],
                "evidence_refs": row["evidence"]["evidence_refs"],
                "document_path": row["evidence"].get("document_path"),
                "word_behavior": row["evidence"].get("word_behavior"),
                "disconnect_method": row["evidence"].get("disconnect_method"),
                "recovery_observed": row["evidence"].get("recovery_observed"),
                "user_a": row["evidence"].get("user_a"),
                "user_b": row["evidence"].get("user_b"),
                "lock_outcome": row["evidence"].get("lock_outcome"),
            }
            for row in reconciled_rows
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 6 Desktop Validation Summary",
        "",
        f"- Overall status: `{summary['overall_status']}`",
        f"- Matrix path: `{summary['matrix_path']}`",
        f"- Matrix sha256: `{summary['matrix_sha256']}`",
        f"- Evidence path: `{summary['evidence_path']}`",
        f"- Evidence sha256: `{summary['evidence_sha256']}`",
        f"- Operator-attested source: `{summary['operator_attested_source']}`",
        f"- Required scenarios: `{summary['required_scenario_count']}`",
        f"- Required pass: `{summary['required_pass_count']}`",
        f"- Required fail: `{summary['required_fail_count']}`",
        f"- Required blocked: `{summary['required_blocked_count']}`",
        f"- Required pending: `{summary['required_pending_count']}`",
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
        "## Required Scenario Reconciliation",
        "",
    ]
    for row in summary["scenario_reconciliation"]:
        lines.append(f"- `{row['scenario_id']}`: `{row['status']}` on `{row['executed_on']}`")
    lines.extend(["", "## Outstanding Required Scenarios", ""])
    if not summary["required_outstanding"]:
        lines.append("- none")
    else:
        for scenario_id in summary["required_outstanding"]:
            lines.append(f"- `{scenario_id}`")
    lines.extend(["", "## Validation Errors", ""])
    if not summary["validation_errors"]:
        lines.append("- none")
    else:
        for error in summary["validation_errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        summary = build_summary()
        _write_utf8(JSON_OUT, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        _write_utf8(MD_OUT, render_markdown(summary))
        print(f"Wrote {JSON_OUT}")
        print(f"Wrote {MD_OUT}")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
