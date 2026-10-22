"""Read-only, fail-closed attestation of the *active* VM release baseline.

Checks release metadata, managed symlinks and retained artifacts only. Does not
read runtime env, invoke Git/network/database, deploy, migrate or restore.
This is not evidence that database restore or application rollback will succeed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

_SHA = re.compile(r"^[0-9a-f]{40}$")
_KEYS = {
    "backend_release_dir": ("current-backend", "backend-releases", None),
    "backend_venv_dir": ("current-venv", "backend-venvs", "bin/python"),
    "frontend_release_dir": ("frontend-dist", "frontend-releases", "index.html"),
}


class BaselineBlocked(ValueError):
    """Active runtime cannot be shown to match its release metadata."""


def audit_active_release(root: Path, *, expected_sha: str) -> dict[str, object]:
    if not _SHA.fullmatch(expected_sha):
        raise BaselineBlocked("INVALID_EXPECTED_SHA")
    root = root.resolve(strict=True)
    metadata = root / "current-release.json"
    if not metadata.is_file() or metadata.is_symlink():
        raise BaselineBlocked("METADATA_UNAVAILABLE")
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BaselineBlocked("METADATA_UNREADABLE") from exc
    if not isinstance(payload, dict) or payload.get("current_sha") != expected_sha:
        raise BaselineBlocked("METADATA_SHA_MISMATCH")
    if payload.get("current_short_sha") != expected_sha[:7]:
        raise BaselineBlocked("METADATA_SHORT_SHA_MISMATCH")

    for key, (link_name, folder, required_file) in _KEYS.items():
        expected = root / folder / expected_sha
        link = root / link_name
        if not expected.is_dir() or expected.is_symlink():
            raise BaselineBlocked(f"{key}:RELEASE_UNAVAILABLE")
        if payload.get(key) != str(expected):
            raise BaselineBlocked(f"{key}:METADATA_PATH_MISMATCH")
        if not link.is_symlink():
            raise BaselineBlocked(f"{key}:LINK_UNAVAILABLE")
        try:
            actual = link.resolve(strict=True)
            canonical_expected = expected.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise BaselineBlocked(f"{key}:BROKEN_LINK") from exc
        if actual != canonical_expected:
            raise BaselineBlocked(f"{key}:ACTIVE_TARGET_MISMATCH")
        if required_file is not None and not (expected / required_file).is_file():
            raise BaselineBlocked(f"{key}:REQUIRED_ARTIFACT_MISSING")

    return {
        "status": "ACTIVE_RELEASE_BASELINE_MATCH",
        "current_sha": expected_sha,
        "components_checked": sorted(_KEYS),
        "rollback_restore_verified": False,
        "database_mutation_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/opt/gxp"))
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        report = audit_active_release(args.root, expected_sha=args.expected_sha)
    except (BaselineBlocked, OSError) as exc:
        parser.exit(2, f"STOP: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
