"""Fail-closed fan-in for *actual* integrated rehearsal candidate CI jobs.

Only used by an integrated-source push workflow after all five required jobs
have run. CI success on its own (with SKIPPED tests) is NOT release approval.
No GitHub tokens, network calls, deployment, or database access.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping


REQUIRED_JOBS: tuple[str, ...] = (
    "backend",
    "frontend",
    "hygiene",
    "cross-head-integration",
    "b6-postgres-integration",
)


class RehearsalRequiredCiError(ValueError):
    """Required integration CI job did not actually complete successfully."""


def evaluate_rehearsal_ci_results(results: Mapping[str, str]) -> dict[str, object]:
    """Reject every missing or non-success required job, including SKIPPED."""
    normalized: dict[str, str] = {}
    for job in REQUIRED_JOBS:
        status = results.get(job)
        if status != "success":
            raise RehearsalRequiredCiError(
                f"STOP: required rehearsal CI job {job} did not succeed "
                f"({status if status else 'missing'})."
            )
        normalized[job] = status
    return {
        "status": "REHEARSAL_REQUIRED_CI_PASS",
        "required_jobs": normalized,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--frontend", required=True)
    parser.add_argument("--hygiene", required=True)
    parser.add_argument("--cross-head", required=True)
    parser.add_argument("--b6", required=True)
    args = parser.parse_args()
    statuses = {
        "backend": args.backend,
        "frontend": args.frontend,
        "hygiene": args.hygiene,
        "cross-head-integration": args.cross_head,
        "b6-postgres-integration": args.b6,
    }
    try:
        report = evaluate_rehearsal_ci_results(statuses)
    except RehearsalRequiredCiError as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
