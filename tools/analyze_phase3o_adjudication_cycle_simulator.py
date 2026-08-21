from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.phase3o_adjudication_cycle_simulator import PHASE3O_DIR, build_phase3o_simulation


def main() -> None:
    simulation = build_phase3o_simulation()
    PHASE3O_DIR.mkdir(parents=True, exist_ok=True)

    summary_json_path = PHASE3O_DIR / "simulation_summary.json"
    summary_md_path = PHASE3O_DIR / "simulation_summary.md"
    decisions_path = PHASE3O_DIR / "simulated_external_evidence_decisions.json"
    tracker_path = PHASE3O_DIR / "simulated_review_progress_tracker.json"

    summary_json_path.write_text(
        json.dumps({k: v for k, v in simulation.items() if k not in {"decisions", "tracker_rows"}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    decisions_path.write_text(
        json.dumps(simulation["decisions"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tracker_path.write_text(
        json.dumps(simulation["tracker_rows"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Phase 3o Adjudication Cycle Simulator",
        "",
        f"- Generated on: `{simulation['generated_on']}`",
        f"- Simulated decisions: `{simulation['simulated_decision_count']}`",
        f"- Selected review keys: `{', '.join(simulation['selected_review_keys'])}`",
        f"- Gate status: `{simulation['gate_report']['status']}`",
        f"- Tracker completed review keys: `{simulation['tracker_summary']['completed_review_keys']}`",
        f"- Simulated merged override count: `{simulation['merged_override_count']}`",
        f"- Simulated open anomaly delta vs Phase 3f: `{simulation['reimport_summary']['open_anomaly_delta']}`",
        "",
        "## Validation",
    ]
    if simulation["gate_report"]["validation_errors"] or simulation["gate_report"]["quality_errors"]:
        for error in simulation["gate_report"]["validation_errors"]:
            lines.append(f"- validation: {error}")
        for error in simulation["gate_report"]["quality_errors"]:
            lines.append(f"- quality: {error}")
    else:
        lines.append("- No gate validation or quality errors.")
    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
