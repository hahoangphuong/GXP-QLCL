"""Read-only cutover review audit. Does not connect to any database."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

# Direct execution (python tools/audit_*.py) uses tools/ on sys.path,
# not necessarily the repository root. Match the B6J planner CLI contract.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.production_line_cutover_readiness_b6k import audit_b6j_review_alignment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="B6K read-only human review alignment")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--reviewed-roster", type=Path, required=True)
    parser.add_argument("--expected-plan-file-sha256", required=True)
    parser.add_argument("--expected-reviewed-roster-file-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # The report must not overwrite either independently approved input
    # (including aliases via symlinks or relative/absolute path spellings).
    if args.output.resolve() in {args.plan.resolve(), args.reviewed_roster.resolve()}:
        parser.error("B6K report output must differ from both immutable input artifacts")
    pbytes, rbytes = args.plan.read_bytes(), args.reviewed_roster.read_bytes()
    for label, payload, expected in (
        ("plan", pbytes, args.expected_plan_file_sha256),
        ("reviewed roster", rbytes, args.expected_reviewed_roster_file_sha256),
    ):
        if sha256(payload).hexdigest() != expected:
            parser.error(f"B6K {label} file SHA256 differs from independently approved value")
    plan = json.loads(pbytes)
    if plan.get("candidate_set_roster_sha256") != sha256(rbytes).hexdigest():
        parser.error("B6K reviewed roster exact bytes differ from plan-bound roster; replan required")
    report = audit_b6j_review_alignment(plan, json.loads(rbytes))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"B6K_REVIEW_ALIGNMENT={report['status']};"
        f"BLOCKED_CANDIDATES={report['blocked_candidate_count']};"
        f"BLOCKED_SOURCE_ACTIONS={report['blocked_source_action_count']}"
    )
    # Keep the complete audit artifact, but never report success to CI/shell
    # when a human review or planned action remains unresolved.
    return 3 if report["status"] == "REVIEW_ALIGNMENT_BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
