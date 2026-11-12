"""Opt-in targeted backend regression feedback; NEVER a merge/release gate.

Usage:
  python -m tools.targeted_backend_feedback --suite reassessment --list
  DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/gxp_qlcl_test \\
    python -m tools.targeted_backend_feedback --suite reassessment --execute

Presets only select committed test files. No user-supplied pytest options,
shell interpolation, database provisioning, migration, or production access.
All six required exact-head GitHub checks still apply before merge.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRESETS: dict[str, tuple[str, ...]] = {
    "ci": (
        "test_ci_pytest_shards.py",
        "test_rehearsal_ci_required_results.py",
    ),
    "reassessment": (
        "test_reassessment_*.py",
    ),
    "case-owner": (
        "test_case_*_postgre*.py",
        "test_case_transition_capa_owner_race_postgres.py",
    ),
    "certificate-owner": (
        "test_certificate_*_postgre*.py",
        "test_gmp_forward_one_case_one_site_one_certificate.py",
    ),
    "capa-owner": (
        "test_capa_*_postgre*.py",
        "test_case_transition_capa_owner_race_postgres.py",
    ),
    "change-request": (
        "test_change_request_*.py",
        "test_a5_change_request_mutation.py",
    ),
}


def select_tests(suite: str, *, root: Path = REPOSITORY_ROOT) -> tuple[str, ...]:
    """Fail closed when a preset or its expected tests are missing."""
    if suite not in PRESETS:
        raise ValueError(f"Unknown targeted suite: {suite}")
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        raise ValueError("Expected repository tests/ directory.")
    paths: set[str] = set()
    for pattern in PRESETS[suite]:
        matching = sorted(
            test for test in tests_dir.glob(pattern)
            if test.is_file() and not test.is_symlink()
            and test.parent == tests_dir
            and test.name.startswith("test_")
            and test.suffix == ".py"
        )
        if not matching:
            raise ValueError(f"Required targeted test pattern is missing: {pattern}")
        paths.update(test.relative_to(root).as_posix() for test in matching)
    return tuple(sorted(paths))


def require_disposable_postgres(database_url: str | None) -> None:
    """Prevent accidental targeted test execution against real databases."""
    parsed = urlparse(database_url or "")
    if (
        parsed.scheme != "postgresql+psycopg"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port != 5432
        or parsed.path != "/gxp_qlcl_test"
    ):
        raise ValueError("STOP: non-CI targeted tests require loopback gxp_qlcl_test PostgreSQL.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(PRESETS), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="Print selected tests, without executing")
    mode.add_argument("--execute", action="store_true", help="Run targeted pytest; never a full CI receipt")
    args = parser.parse_args(argv)
    try:
        paths = select_tests(args.suite)
        if args.execute and args.suite != "ci":
            require_disposable_postgres(os.environ.get("DATABASE_URL"))
    except ValueError as exc:
        parser.exit(2, f"{exc}\\n")
    print(f"TARGETED_NON_AUTHORITATIVE suite={args.suite} modules={len(paths)}", flush=True)
    for path in paths:
        print(path, flush=True)
    if args.list:
        return 0
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *paths],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
