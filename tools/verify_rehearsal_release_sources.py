"""Fail-closed Git source audit for a proposed integrated rehearsal release.

The reviewed backend must be an ancestor of the candidate and ALL tracked
paths outside frontend/ must be unchanged. The candidate's complete
frontend/ Git tree must equal the separately approved frontend source.
This module never fetches, checks out, mutates Git or accesses VM/database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from tools.verify_rehearsal_frontend_source import (
    FrontendReleaseSourceError,
    _commit_and_frontend_tree,
    verify_frontend_source_equivalence,
)


class RehearsalReleaseSourceError(ValueError):
    """A release source cannot be proven to come from both approved commits."""


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True, capture_output=True, check=False,
        )
    except OSError as exc:
        raise RehearsalReleaseSourceError("Git is unavailable for release provenance audit.") from exc


def verify_rehearsal_release_sources(
    repo: Path,
    *,
    target_sha: str,
    approved_backend_sha: str,
    approved_frontend_sha: str,
) -> dict[str, str | int]:
    """Prove one commit has precisely the approved backend + frontend trees."""
    try:
        frontend = verify_frontend_source_equivalence(
            repo, target_sha=target_sha,
            approved_frontend_sha=approved_frontend_sha,
        )
        backend_commit, _backend_frontend_tree = _commit_and_frontend_tree(
            repo, approved_backend_sha,
        )
    except FrontendReleaseSourceError as exc:
        raise RehearsalReleaseSourceError(str(exc)) from exc

    target_commit = frontend["target_commit"]
    ancestor = _run_git(
        repo, "merge-base", "--is-ancestor", backend_commit, target_commit,
    )
    if ancestor.returncode == 1:
        raise RehearsalReleaseSourceError(
            "STOP: approved backend commit is not an ancestor of target release."
        )
    if ancestor.returncode != 0:
        raise RehearsalReleaseSourceError("Could not verify backend ancestry.")

    # A complete tree-level diff includes deletions, permissions, symlinks and
    # added files. Exclude ONLY the top-level frontend/ subtree; CI workflow,
    # release scripts, migrations, application code and docs must remain exact.
    changed = _run_git(
        repo, "diff", "--no-ext-diff", "--name-only",
        backend_commit, target_commit, "--", ".", ":(top,exclude)frontend",
    )
    if changed.returncode != 0:
        raise RehearsalReleaseSourceError("Could not compare tracked backend release paths.")
    if changed.stdout.strip():
        raise RehearsalReleaseSourceError(
            "STOP: unreviewed non-frontend Git paths differ from approved backend commit."
        )

    return {
        "status": "REHEARSAL_SOURCE_EXACT_MATCH",
        "target_commit": target_commit,
        "approved_backend_commit": backend_commit,
        "approved_frontend_commit": frontend["approved_frontend_commit"],
        "frontend_tree": frontend["frontend_tree"],
        "non_frontend_changed_paths": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--approved-backend-sha", required=True)
    parser.add_argument("--approved-frontend-sha", required=True)
    args = parser.parse_args()
    try:
        report = verify_rehearsal_release_sources(
            args.repo, target_sha=args.target_sha,
            approved_backend_sha=args.approved_backend_sha,
            approved_frontend_sha=args.approved_frontend_sha,
        )
    except RehearsalReleaseSourceError as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
