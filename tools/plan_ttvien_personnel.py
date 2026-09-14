"""Create a deterministic, source-only TTviên personnel plan."""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from backend.app.domain.legacy_ttvien_personnel import build_personnel_plan, preview_team_crosswalk


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "artifacts" / "phase3c" / "legacy_snapshot_v2.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only TTviên personnel source planner.")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--expected-snapshot-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.snapshot.read_bytes()
    if sha256(source).hexdigest() != args.expected_snapshot_sha256.lower():
        raise ValueError("snapshot byte SHA256 fence failed")
    snapshot = json.loads(source)
    plan = build_personnel_plan(snapshot, expected_snapshot_sha256=args.expected_snapshot_sha256.lower())
    plan["team_crosswalk_preview"] = preview_team_crosswalk(snapshot, plan)
    content = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    print(f"SHA256={sha256(content).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
