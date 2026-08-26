from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.template.json"
PHASE3P_PATH = ROOT / "artifacts" / "phase3p" / "current_projection_conflicts.json"
JSON_OUT = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.summary.json"
MD_OUT = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.summary.md"

ALLOWED_ACTIONS = {"winner", "no_winner"}
NO_WINNER_ALLOWED_CLASSIFICATIONS = {"blank_ma_dc_non_case_backed_multi_current"}


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


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _conflict_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    conflicts = payload.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise RuntimeError("Phase 3p conflict artifact must contain a conflicts list.")
    index: dict[str, dict[str, Any]] = {}
    for row in conflicts:
        if not isinstance(row, dict):
            raise RuntimeError("Phase 3p conflict artifact contains a non-object conflict row.")
        conflict_key = normalize_text(row.get("conflict_key"))
        if not conflict_key:
            raise RuntimeError("Phase 3p conflict row missing conflict_key.")
        if conflict_key in index:
            raise RuntimeError(f"Phase 3p conflict artifact contains duplicate conflict_key: {conflict_key}")
        index[conflict_key] = row
    return index


def validate_decisions(
    rows: list[dict[str, Any]],
    *,
    phase3p_index: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    seen_keys: set[str] = set()
    phase3p_index = phase3p_index or {}
    for row in rows:
        conflict_key = normalize_text(row.get("conflict_key"))
        if not conflict_key:
            errors.append("decision row missing conflict_key")
            continue
        if conflict_key in seen_keys:
            errors.append(f"duplicate conflict_key: {conflict_key}")
        seen_keys.add(conflict_key)

        action = normalize_text(row.get("decision_type") or row.get("decision_action"))
        legacy_action = normalize_text(row.get("decision_action"))
        if action not in ALLOWED_ACTIONS:
            errors.append(f"{conflict_key}: invalid decision_type {action!r}")
            continue
        if legacy_action and legacy_action != action:
            errors.append(f"{conflict_key}: decision_action does not match decision_type")

        selected = row.get("selected_candidate_legacy_id")
        candidates = {str(item) for item in row.get("candidate_legacy_ids", [])}
        rationale = normalize_text(row.get("decision_rationale"))
        reviewer = normalize_text(row.get("reviewer"))
        reviewed_on = normalize_text(row.get("reviewed_on"))
        decision_status = normalize_text(row.get("decision_status"))

        if decision_status != "owner_approved":
            errors.append(f"{conflict_key}: decision_status must be 'owner_approved'")

        if action == "winner":
            if selected is None:
                errors.append(f"{conflict_key}: winner action requires selected_candidate_legacy_id")
            elif str(selected) not in candidates:
                errors.append(f"{conflict_key}: selected winner is not in candidate_legacy_ids")
        elif selected is not None:
            errors.append(f"{conflict_key}: no_winner action must not set selected_candidate_legacy_id")

        if not rationale:
            errors.append(f"{conflict_key}: decision rationale is required")
        if not reviewer:
            errors.append(f"{conflict_key}: reviewer is required")
        if not reviewed_on:
            errors.append(f"{conflict_key}: reviewed_on is required")

        source_conflict = phase3p_index.get(conflict_key)
        if source_conflict is None:
            continue

        expected_candidates = [str(item) for item in source_conflict.get("candidate_legacy_ids", [])]
        if [str(item) for item in row.get("candidate_legacy_ids", [])] != expected_candidates:
            errors.append(f"{conflict_key}: candidate_legacy_ids do not match Phase 3p")
        if normalize_text(row.get("projection_type")) != normalize_text(source_conflict.get("projection_type")):
            errors.append(f"{conflict_key}: projection_type does not match Phase 3p")
        if normalize_text(row.get("source_sheet")) != normalize_text(source_conflict.get("source_sheet")):
            errors.append(f"{conflict_key}: source_sheet does not match Phase 3p")
        if normalize_text(row.get("classification")) != normalize_text(source_conflict.get("classification")):
            errors.append(f"{conflict_key}: classification does not match Phase 3p")

        if action == "no_winner":
            if normalize_text(row.get("source_sheet")) != "db.cc":
                errors.append(f"{conflict_key}: no_winner is only approved for db.cc conflicts")
            if normalize_text(row.get("classification")) not in NO_WINNER_ALLOWED_CLASSIFICATIONS:
                errors.append(f"{conflict_key}: no_winner is not approved for this classification")
    return errors


def build_summary(
    *,
    decision_path: Path = INPUT_PATH,
    phase3p_path: Path = PHASE3P_PATH,
) -> dict[str, Any]:
    decisions_payload, decision_sha256 = load_json(decision_path)
    phase3p_payload, phase3p_sha256 = load_json(phase3p_path)
    rows = decisions_payload.get("decisions", [])
    if not isinstance(rows, list):
        raise RuntimeError("Phase 3s decision contract must contain a decisions list.")

    phase3p_index = _conflict_index(phase3p_payload)
    decision_index = {
        normalize_text(row.get("conflict_key")): row
        for row in rows
        if isinstance(row, dict) and normalize_text(row.get("conflict_key"))
    }

    phase3p_keys = set(phase3p_index)
    decision_keys = set(decision_index)
    missing_conflict_keys = sorted(phase3p_keys - decision_keys)
    extra_decision_keys = sorted(decision_keys - phase3p_keys)

    errors = validate_decisions(rows, phase3p_index=phase3p_index)
    if missing_conflict_keys:
        errors.append(f"missing Phase 3p conflict decisions: {', '.join(missing_conflict_keys)}")
    if extra_decision_keys:
        errors.append(f"stale extra decisions not present in Phase 3p: {', '.join(extra_decision_keys)}")

    reported_phase3p_sha256 = normalize_text(decisions_payload.get("source_conflict_sha256"))
    if reported_phase3p_sha256 != phase3p_sha256:
        errors.append(
            "Phase 3s source_conflict_sha256 does not match actual Phase 3p artifact bytes: "
            f"reported {reported_phase3p_sha256!r}, actual {phase3p_sha256!r}"
        )

    actual_snapshot_path = normalize_text(phase3p_payload.get("snapshot_path"))
    actual_snapshot_sha256 = normalize_text(phase3p_payload.get("snapshot_sha256"))
    reported_snapshot_path = normalize_text(decisions_payload.get("source_snapshot_path"))
    reported_snapshot_sha256 = normalize_text(decisions_payload.get("source_snapshot_sha256"))
    if reported_snapshot_path != actual_snapshot_path:
        errors.append(
            "Phase 3s source_snapshot_path does not match Phase 3p provenance: "
            f"reported {reported_snapshot_path!r}, actual {actual_snapshot_path!r}"
        )
    if reported_snapshot_sha256 != actual_snapshot_sha256:
        errors.append(
            "Phase 3s source_snapshot_sha256 does not match Phase 3p provenance: "
            f"reported {reported_snapshot_sha256!r}, actual {actual_snapshot_sha256!r}"
        )

    action_counts = {action: 0 for action in sorted(ALLOWED_ACTIONS)}
    for row in rows:
        action = normalize_text(row.get("decision_type") or row.get("decision_action"))
        if action in action_counts:
            action_counts[action] += 1
    resolved_count = action_counts["winner"] + action_counts["no_winner"]
    unresolved_count = len(rows) - resolved_count
    overall_status = "invalid" if errors else ("ready" if unresolved_count == 0 else "blocked")
    return {
        "generated_on": "2026-08-26",
        "overall_status": overall_status,
        "decision_contract_path": _display_path(decision_path),
        "decision_contract_sha256": decision_sha256,
        "source_phase3p_path": _display_path(phase3p_path),
        "source_phase3p_sha256": phase3p_sha256,
        "source_snapshot_path": actual_snapshot_path,
        "source_snapshot_sha256": actual_snapshot_sha256,
        "source_conflict_count": len(phase3p_index),
        "decision_count": len(rows),
        "resolved_count": resolved_count,
        "unresolved_count": unresolved_count,
        "action_counts": action_counts,
        "missing_conflict_keys": missing_conflict_keys,
        "extra_decision_keys": extra_decision_keys,
        "key_set_matches_phase3p": not missing_conflict_keys and not extra_decision_keys,
        "validation_errors": errors,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Current Projection Conflict Decision Summary",
        "",
        f"- Overall status: `{summary['overall_status']}`",
        f"- Decision contract path: `{summary['decision_contract_path']}`",
        f"- Decision contract sha256: `{summary['decision_contract_sha256']}`",
        f"- Source Phase 3p path: `{summary['source_phase3p_path']}`",
        f"- Source Phase 3p sha256: `{summary['source_phase3p_sha256']}`",
        f"- Source snapshot path: `{summary['source_snapshot_path']}`",
        f"- Source snapshot sha256: `{summary['source_snapshot_sha256']}`",
        f"- Source conflict count: `{summary['source_conflict_count']}`",
        f"- Decision count: `{summary['decision_count']}`",
        f"- Resolved count: `{summary['resolved_count']}`",
        f"- Unresolved count: `{summary['unresolved_count']}`",
        f"- Key set matches Phase 3p: `{summary['key_set_matches_phase3p']}`",
        "",
        "## Action Counts",
        "",
    ]
    for action, count in summary["action_counts"].items():
        lines.append(f"- `{action}`: `{count}`")
    lines.extend(["", "## Missing Conflict Keys", ""])
    if not summary["missing_conflict_keys"]:
        lines.append("- none")
    else:
        for key in summary["missing_conflict_keys"]:
            lines.append(f"- `{key}`")
    lines.extend(["", "## Extra Decision Keys", ""])
    if not summary["extra_decision_keys"]:
        lines.append("- none")
    else:
        for key in summary["extra_decision_keys"]:
            lines.append(f"- `{key}`")
    lines.extend(["", "## Validation Errors", ""])
    if not summary["validation_errors"]:
        lines.append("- none")
    else:
        for error in summary["validation_errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
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
