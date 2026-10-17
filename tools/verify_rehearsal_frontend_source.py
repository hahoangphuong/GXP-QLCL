"""Pure Git-tree identity gate for explicitly approved rehearsal frontend source.

No server access, storage access, network fetch, DB connection, or Git writes.
The operator must provide BOTH commit SHAs. Git object identity, not branch
names or CI-only overlays, determines whether deployable frontend source matches.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


class FrontendReleaseSourceError(ValueError):
    """Stop the rehearsal release before staging or any runtime mutation."""


_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def _commit_and_frontend_tree(repo: Path, text: str) -> tuple[str, str]:
    if not _SHA.fullmatch(text):
        raise FrontendReleaseSourceError("Frontend gate requires an exact 40-hex commit SHA.")
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"{text}^{{commit}}"],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"{commit}:frontend"],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        kind = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-t", tree],
            text=True, capture_output=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise FrontendReleaseSourceError(
            "Required commit/frontend tree not found locally; verify approved SHA and fetch before deploying."
        ) from exc
    if commit.lower() != text.lower() or kind != "tree" or not _SHA.fullmatch(tree):
        raise FrontendReleaseSourceError("Unverified commit/frontend Git tree object.")
    return commit, tree


def verify_frontend_source_equivalence(
    repo: Path, *, target_sha: str, approved_frontend_sha: str,
) -> dict[str, str]:
    """Require identical tracked frontend/ Git tree at both explicit commits."""
    target_commit, target_tree = _commit_and_frontend_tree(repo, target_sha)
    approved_commit, approved_tree = _commit_and_frontend_tree(repo, approved_frontend_sha)
    if target_tree != approved_tree:
        raise FrontendReleaseSourceError(
            "STOP: deploy target frontend Git tree differs from approved frontend source. "
            "Integrate and review a new release commit; CI runner overlay is not deployable."
        )
    return {
        "status": "FRONTEND_TREE_EXACT_MATCH",
        "target_commit": target_commit,
        "approved_frontend_commit": approved_commit,
        "frontend_tree": target_tree,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--approved-frontend-sha", required=True)
    args = parser.parse_args()
    try:
        result = verify_frontend_source_equivalence(
            args.repo, target_sha=args.target_sha,
            approved_frontend_sha=args.approved_frontend_sha,
        )
    except FrontendReleaseSourceError as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
