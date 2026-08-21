from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE3_PATH = ROOT / "artifacts" / "phase3r" / "phase3_final_closeout.json"
PHASE4_PATH = ROOT / "artifacts" / "phase4" / "phase4_final_closeout.json"
PHASE5_PATH = ROOT / "artifacts" / "phase5" / "phase5_final_closeout.json"
PHASE6_PATH = ROOT / "artifacts" / "phase6" / "phase6_final_closeout.json"
PHASE3P_PATH = ROOT / "artifacts" / "phase3p" / "current_projection_conflicts.json"
PHASE3S_PATH = ROOT / "artifacts" / "phase3s" / "current_projection_conflict_decisions.summary.json"
OUT_DIR = ROOT / "artifacts" / "phase7"
JSON_OUT = OUT_DIR / "cutover_readiness.json"
MD_OUT = OUT_DIR / "cutover_readiness.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def gate(status: str, reason: str, *, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "detail": detail or {},
    }


def build_current_projection_gate(phase3p: dict[str, Any], phase3s: dict[str, Any] | None) -> dict[str, Any]:
    if phase3s is not None:
        unresolved_count = int(phase3s.get("unresolved_count", 0))
        overall_status = str(phase3s.get("overall_status", ""))
        if overall_status == "ready" and unresolved_count == 0:
            return gate(
                "pass",
                "Current-projection conflicts were adjudicated in Phase 3s.",
                detail={
                    "resolved_count": phase3s.get("resolved_count", 0),
                    "winner_count": phase3s.get("action_counts", {}).get("winner", 0),
                    "no_winner_count": phase3s.get("action_counts", {}).get("no_winner", 0),
                },
            )
        return gate(
            "blocked",
            "Current-projection conflicts still require adjudication or have unresolved decisions in Phase 3s.",
            detail={
                "overall_status": overall_status,
                "unresolved_count": unresolved_count,
                "validation_errors": phase3s.get("validation_errors", []),
            },
        )

    conflict_count = int(phase3p.get("conflict_count", 0))
    return (
        gate("pass", "No current-projection conflicts remain.")
        if conflict_count == 0
        else gate(
            "blocked",
            "Current-projection conflicts still require adjudication outside the structured-import baseline.",
            detail={
                "conflict_count": conflict_count,
                "manual_review_count": phase3p.get("manual_review_count", 0),
            },
        )
    )


def build_readiness() -> dict[str, Any]:
    phase3 = load_json(PHASE3_PATH)
    phase4 = load_json(PHASE4_PATH)
    phase5 = load_json(PHASE5_PATH)
    phase6 = load_json(PHASE6_PATH)
    phase3p = load_json(PHASE3P_PATH)
    phase3s = load_json(PHASE3S_PATH) if PHASE3S_PATH.exists() else None

    gates: dict[str, dict[str, Any]] = {}
    gates["structured_data_baseline"] = (
        gate("pass", "Phase 3 structured migration baseline is closed.")
        if phase3.get("phase3_status") == "closed"
        else gate("blocked", "Phase 3 structured migration baseline is not closed.")
    )
    gates["storage_contract_baseline"] = (
        gate("pass", "Phase 4 storage contract/tooling baseline is closed.")
        if phase4.get("phase4_status") == "closed"
        else gate("blocked", "Phase 4 storage contract/tooling baseline is not closed.")
    )
    gates["document_contract_baseline"] = (
        gate("pass", "Phase 5 document/runtime baseline is closed.")
        if phase5.get("phase5_status") == "closed"
        else gate("blocked", "Phase 5 document/runtime baseline is not closed.")
    )
    gates["desktop_private_share_validation"] = (
        gate("pass", "Phase 6 desktop/private-share evidence is complete.")
        if phase6.get("phase6_status") == "closed"
        else gate(
            "blocked",
            "Phase 6 desktop/private-share evidence is not closed.",
            detail={"required_outstanding": phase6.get("required_outstanding", [])},
        )
    )

    gates["current_projection_conflicts"] = build_current_projection_gate(phase3p, phase3s)

    gates["legacy_write_freeze_execution"] = gate(
        "pending",
        "Legacy write freeze cannot be executed until desktop/private-share evidence and cutover window approval are complete.",
    )
    gates["rollback_window_execution"] = gate(
        "pending",
        "Rollback execution remains pending until production cutover window is approved.",
    )

    statuses = [payload["status"] for payload in gates.values()]
    if any(status == "blocked" for status in statuses):
        overall_status = "blocked"
    elif any(status == "pending" for status in statuses):
        overall_status = "pending"
    else:
        overall_status = "ready"

    return {
        "generated_on": "2026-08-14",
        "phase7_status": overall_status,
        "gates": gates,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 7 Cutover Readiness",
        "",
        "Generated by `tools/build_phase7_cutover_readiness.py`.",
        "",
        f"- Overall cutover status: `{report['phase7_status']}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Reason |",
        "|---|---|---|",
    ]
    for gate_name, payload in report["gates"].items():
        lines.append(f"| `{gate_name}` | `{payload['status']}` | {payload['reason']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_readiness()
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
