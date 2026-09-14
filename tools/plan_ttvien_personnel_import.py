"""Build a deterministic no-write TTviên personnel import plan from DB-state evidence."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from backend.app.domain.legacy_ttvien_personnel_import import classify_personnel_import


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="No-write TTviên personnel import planner.")
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--canonical-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    source_plan = _read_json(args.source_plan)
    canonical_state = _read_json(args.canonical_state)
    if not isinstance(source_plan, dict) or not isinstance(source_plan.get("records"), list):
        raise ValueError("source plan is invalid")
    if not isinstance(canonical_state, dict) or not all(
        isinstance(canonical_state.get(key), list)
        for key in ("legacy_inspector_source_records", "inspector_profiles", "persons")
    ):
        raise ValueError("canonical state is invalid")
    plan = classify_personnel_import(
        source_plan["records"],
        canonical_state["legacy_inspector_source_records"],
        canonical_state["inspector_profiles"],
        canonical_state["persons"],
    )
    content = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    print(f"SHA256={sha256(content).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
