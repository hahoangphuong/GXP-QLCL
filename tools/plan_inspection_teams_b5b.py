"""Build the B5B structured inspection-team source plan without DB access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.domain.legacy_inspection_team import build_inspection_team_plan, plan_sha256

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SHA256 = "484cf37603aacc5ff01a7bde5ffab01ed444748d5c7b1a0b30e7fc3a04936caa"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the read-only B5B inspection-team source plan.")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "artifacts/phase3c/legacy_snapshot_v2.json")
    parser.add_argument("--personnel-plan", type=Path, default=ROOT / "artifacts/phase3c/ttvien_personnel_plan_b2.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    roster_plan = json.loads(args.personnel_plan.read_text(encoding="utf-8"))
    plan = build_inspection_team_plan(snapshot, roster_plan, expected_snapshot_sha256=SNAPSHOT_SHA256)
    args.output.write_bytes((json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"plan_sha256": plan_sha256(plan), "team_count": plan["team_count"], "member_count": plan["member_count"], "classification_counts": plan["classification_counts"], "database_accessed": False}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
