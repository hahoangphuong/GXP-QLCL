from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "artifacts" / "phase3p" / "current_projection_conflicts.json"
OUT_DIR = ROOT / "artifacts" / "phase3s"
JSON_OUT = OUT_DIR / "current_projection_conflict_decisions.template.json"
MD_OUT = OUT_DIR / "current_projection_conflict_decisions.template.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_template() -> dict[str, Any]:
    source = load_json(INPUT_PATH)
    decisions = []
    for row in source.get("conflicts", []):
        decisions.append(
            {
                "conflict_key": row["conflict_key"],
                "projection_type": row["projection_type"],
                "source_sheet": row["source_sheet"],
                "business_key": row["business_key"],
                "classification": row["classification"],
                "candidate_legacy_ids": row["candidate_legacy_ids"],
                "decision_action": "pending",
                "selected_candidate_legacy_id": None,
                "reviewer": None,
                "reviewed_on": None,
                "decision_rationale": "",
                "promote_policy_candidate": False,
            }
        )
    return {
        "generated_on": "2026-08-14",
        "source_conflict_count": len(decisions),
        "allowed_actions": ["pending", "winner", "no_winner", "defer"],
        "decisions": decisions,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Current Projection Conflict Decisions Template",
        "",
        f"- Generated on: `{payload['generated_on']}`",
        f"- Source conflict count: `{payload['source_conflict_count']}`",
        f"- Allowed actions: `{', '.join(payload['allowed_actions'])}`",
        "",
        "## Conflicts",
        "",
        "| Conflict Key | Projection | Classification | Candidates | Action |",
        "|---|---|---|---|---|",
    ]
    for row in payload["decisions"]:
        lines.append(
            f"| `{row['conflict_key']}` | `{row['projection_type']}` | `{row['classification']}` | "
            f"`{', '.join(row['candidate_legacy_ids'])}` | `{row['decision_action']}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_template()
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(payload), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
