from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.template.json"
JSON_OUT = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.summary.json"
MD_OUT = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.summary.md"

ALLOWED_ACTIONS = {"pending", "winner", "no_winner", "defer"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def validate_decisions(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_keys: set[str] = set()
    for row in rows:
        conflict_key = str(row.get("conflict_key", "")).strip()
        if not conflict_key:
            errors.append("decision row missing conflict_key")
            continue
        if conflict_key in seen_keys:
            errors.append(f"duplicate conflict_key: {conflict_key}")
        seen_keys.add(conflict_key)

        action = normalize_text(row.get("decision_action", ""))
        if action not in ALLOWED_ACTIONS:
            errors.append(f"{conflict_key}: invalid decision_action {action!r}")
            continue

        selected = row.get("selected_candidate_legacy_id")
        candidates = {str(item) for item in row.get("candidate_legacy_ids", [])}
        rationale = normalize_text(row.get("decision_rationale", ""))
        reviewer = normalize_text(row.get("reviewer", ""))
        reviewed_on = normalize_text(row.get("reviewed_on", ""))

        if action == "winner":
            if selected is None:
                errors.append(f"{conflict_key}: winner action requires selected_candidate_legacy_id")
            elif str(selected) not in candidates:
                errors.append(f"{conflict_key}: selected winner is not in candidate_legacy_ids")
            if not rationale:
                errors.append(f"{conflict_key}: winner action requires decision_rationale")
            if not reviewer:
                errors.append(f"{conflict_key}: winner action requires reviewer")
            if not reviewed_on:
                errors.append(f"{conflict_key}: winner action requires reviewed_on")
        elif action in {"no_winner", "defer"}:
            if selected is not None:
                errors.append(f"{conflict_key}: {action} action must not set selected_candidate_legacy_id")
            if not rationale:
                errors.append(f"{conflict_key}: {action} action requires decision_rationale")
            if not reviewer:
                errors.append(f"{conflict_key}: {action} action requires reviewer")
            if not reviewed_on:
                errors.append(f"{conflict_key}: {action} action requires reviewed_on")
        else:  # pending
            if selected is not None:
                errors.append(f"{conflict_key}: pending action must not set selected_candidate_legacy_id")
            if rationale or reviewer or reviewed_on:
                errors.append(f"{conflict_key}: pending action must not include reviewer/rationale/date")
    return errors


def build_summary() -> dict[str, Any]:
    payload = load_json(INPUT_PATH)
    rows = payload["decisions"]
    errors = validate_decisions(rows)
    action_counts = {action: 0 for action in sorted(ALLOWED_ACTIONS)}
    for row in rows:
        action = str(row["decision_action"])
        if action in action_counts:
            action_counts[action] += 1
    resolved_count = action_counts["winner"] + action_counts["no_winner"]
    unresolved_count = action_counts["pending"] + action_counts["defer"]
    overall_status = "invalid" if errors else ("ready" if unresolved_count == 0 else "blocked")
    return {
        "generated_on": "2026-08-14",
        "overall_status": overall_status,
        "source_conflict_count": len(rows),
        "resolved_count": resolved_count,
        "unresolved_count": unresolved_count,
        "action_counts": action_counts,
        "validation_errors": errors,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Current Projection Conflict Decision Summary",
        "",
        f"- Overall status: `{summary['overall_status']}`",
        f"- Source conflict count: `{summary['source_conflict_count']}`",
        f"- Resolved count: `{summary['resolved_count']}`",
        f"- Unresolved count: `{summary['unresolved_count']}`",
        "",
        "## Action Counts",
        "",
    ]
    for action, count in summary["action_counts"].items():
        lines.append(f"- `{action}`: `{count}`")
    lines.extend(["", "## Validation Errors", ""])
    if not summary["validation_errors"]:
        lines.append("- none")
    else:
        for error in summary["validation_errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    summary = build_summary()
    JSON_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(summary), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
