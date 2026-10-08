"""Build a B6J ProductionLine plan from explicit local JSON artifacts only."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.production_line_population import canonical_json_bytes
from backend.app.domain.production_line_population_b6j import build_population_plan, canonical_artifact_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B6J source-only ProductionLine population planner.")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--canonical-state", type=Path, required=True)
    parser.add_argument("--candidate-set-sha256", required=True)
    parser.add_argument("--candidate-set-roster", type=Path, required=True)
    parser.add_argument("--candidate-set-roster-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    snapshot_bytes = args.snapshot.read_bytes()
    state = json.loads(args.canonical_state.read_bytes())
    roster_bytes = args.candidate_set_roster.read_bytes()
    roster_raw_sha256 = sha256(roster_bytes).hexdigest()
    if roster_raw_sha256 != args.candidate_set_roster_sha256:
        parser.error("candidate roster raw SHA256 does not match exact file bytes")
    plan = build_population_plan(
        json.loads(snapshot_bytes),
        snapshot_sha256=sha256(snapshot_bytes).hexdigest(),
        canonical_state=state,
        canonical_state_sha256=sha256(canonical_json_bytes(state)).hexdigest(),
        candidate_set_sha256=args.candidate_set_sha256,
        candidate_roster=json.loads(roster_bytes),
        candidate_roster_raw_sha256=roster_raw_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_artifact_bytes(plan))
    print(f"PRODUCTION_LINE_POPULATION_PLAN_SHA256={plan['plan_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
