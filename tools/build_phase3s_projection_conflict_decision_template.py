from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "artifacts" / "phase3p" / "current_projection_conflicts.json"
OUT_DIR = ROOT / "artifacts" / "phase3s"
JSON_OUT = OUT_DIR / "current_projection_conflict_decisions.template.json"
MD_OUT = OUT_DIR / "current_projection_conflict_decisions.template.md"

OWNER_APPROVED_BY = "business_owner"
OWNER_APPROVED_ON = "2026-08-16"
ALLOWED_DECISION_TYPES = ("winner", "no_winner")

OWNER_DECISIONS: dict[str, dict[str, Any]] = {
    "db.ktra::GMP-103C": {
        "decision_type": "winner",
        "winner_legacy_id": "1194",
        "business_rationale": "Row 1095 is older incomplete legacy data; row 1194 is the current row confirmed by owner review.",
        "rule_basis": "Owner confirmed current row after reviewing legacy history.",
    },
    "db.ktra::GMP-310A": {
        "decision_type": "winner",
        "winner_legacy_id": "1160",
        "business_rationale": "Current row is the row with the latest dossier receipt date.",
        "rule_basis": "Latest dossier receipt date wins for this adjudicated conflict.",
    },
    "db.ktra::GMP-52A": {
        "decision_type": "winner",
        "winner_legacy_id": "1509",
        "business_rationale": "Current row is the row with the latest dossier receipt date.",
        "rule_basis": "Latest dossier receipt date wins for this adjudicated conflict.",
    },
    "db.ktra::GMP-75B": {
        "decision_type": "winner",
        "winner_legacy_id": "1460",
        "business_rationale": "Current row is the row with the latest dossier receipt date.",
        "rule_basis": "Latest dossier receipt date wins for this adjudicated conflict.",
    },
}

for conflict_key in (
    "db.cc::GMP-104",
    "db.cc::GMP-128",
    "db.cc::GMP-129",
    "db.cc::GMP-144",
    "db.cc::GMP-2",
    "db.cc::GMP-24",
    "db.cc::GMP-264",
    "db.cc::GMP-337",
    "db.cc::GMP-50",
    "db.cc::GMP-69",
):
    OWNER_DECISIONS[conflict_key] = {
        "decision_type": "no_winner",
        "winner_legacy_id": None,
        "business_rationale": (
            "These foreign-regulator GMP certificates are reference-only rows kept for lookup. "
            "They do not link to a specific inspection, case, or production line, so no current case-backed certificate winner may be selected."
        ),
        "rule_basis": "Reference-only foreign-regulator certificate rows must not produce a current winner.",
    }


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


def _owner_decision_spec(conflict_key: str) -> dict[str, Any]:
    try:
        return OWNER_DECISIONS[conflict_key]
    except KeyError as exc:
        raise RuntimeError(f"Missing owner decision for Phase 3p conflict: {conflict_key}") from exc


def _validate_owner_decision_key_set(conflicts: list[dict[str, Any]]) -> None:
    conflict_keys = {str(row["conflict_key"]) for row in conflicts}
    owner_keys = set(OWNER_DECISIONS)
    missing = sorted(conflict_keys - owner_keys)
    extra = sorted(owner_keys - conflict_keys)
    if missing:
        raise RuntimeError(f"Owner decision map is missing Phase 3p conflicts: {', '.join(missing)}")
    if extra:
        raise RuntimeError(f"Owner decision map contains stale conflict keys: {', '.join(extra)}")


def build_template() -> dict[str, Any]:
    source, source_sha256 = load_json(INPUT_PATH)
    conflicts = source.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise RuntimeError("Phase 3p conflict artifact must contain a conflicts list.")
    _validate_owner_decision_key_set(conflicts)

    decisions = []
    for row in conflicts:
        conflict_key = str(row["conflict_key"])
        spec = _owner_decision_spec(conflict_key)
        decision_type = str(spec["decision_type"])
        if decision_type not in ALLOWED_DECISION_TYPES:
            raise RuntimeError(f"Unsupported owner decision type for {conflict_key}: {decision_type}")
        winner_legacy_id = spec["winner_legacy_id"]
        decisions.append(
            {
                "conflict_key": conflict_key,
                "projection_type": row["projection_type"],
                "source_sheet": row["source_sheet"],
                "business_key": row["business_key"],
                "classification": row["classification"],
                "candidate_legacy_ids": row["candidate_legacy_ids"],
                "decision_type": decision_type,
                "decision_action": decision_type,
                "selected_candidate_legacy_id": winner_legacy_id,
                "decision_status": "owner_approved",
                "reviewer": OWNER_APPROVED_BY,
                "reviewed_on": OWNER_APPROVED_ON,
                "owner_approved_by": OWNER_APPROVED_BY,
                "owner_approved_on": OWNER_APPROVED_ON,
                "decision_rationale": spec["business_rationale"],
                "owner_business_rationale": spec["business_rationale"],
                "rule_basis": spec["rule_basis"],
                "promote_policy_candidate": False,
            }
        )

    return {
        "generated_on": "2026-08-26",
        "decision_contract_status": "owner_approved",
        "allowed_actions": list(ALLOWED_DECISION_TYPES),
        "source_conflict_path": _display_path(INPUT_PATH),
        "source_conflict_sha256": source_sha256,
        "source_snapshot_path": source.get("snapshot_path"),
        "source_snapshot_sha256": source.get("snapshot_sha256"),
        "source_conflict_count": len(conflicts),
        "owner_approved_by": OWNER_APPROVED_BY,
        "owner_approved_on": OWNER_APPROVED_ON,
        "decisions": decisions,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Current Projection Conflict Decision Contract",
        "",
        f"- Generated on: `{payload['generated_on']}`",
        f"- Decision contract status: `{payload['decision_contract_status']}`",
        f"- Source conflict path: `{payload['source_conflict_path']}`",
        f"- Source conflict sha256: `{payload['source_conflict_sha256']}`",
        f"- Source snapshot path: `{payload['source_snapshot_path']}`",
        f"- Source snapshot sha256: `{payload['source_snapshot_sha256']}`",
        f"- Source conflict count: `{payload['source_conflict_count']}`",
        f"- Owner approved by: `{payload['owner_approved_by']}`",
        f"- Owner approved on: `{payload['owner_approved_on']}`",
        "",
        "## Decisions",
        "",
        "| Conflict Key | Classification | Candidates | Decision | Winner |",
        "|---|---|---|---|---|",
    ]
    for row in payload["decisions"]:
        winner = row["selected_candidate_legacy_id"] or "-"
        lines.append(
            f"| `{row['conflict_key']}` | `{row['classification']}` | `{', '.join(row['candidate_legacy_ids'])}` | "
            f"`{row['decision_type']}` | `{winner}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        payload = build_template()
        _write_utf8(JSON_OUT, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        _write_utf8(MD_OUT, render_markdown(payload))
        print(f"Wrote {JSON_OUT}")
        print(f"Wrote {MD_OUT}")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
