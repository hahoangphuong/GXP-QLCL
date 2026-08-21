from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"^legacy/"),
    re.compile(r"^artifacts/"),
    re.compile(r"^frontend/node_modules/"),
    re.compile(r"^frontend/dist/"),
    re.compile(r".*\.db$", re.IGNORECASE),
    re.compile(r".*\.sqlite3?$", re.IGNORECASE),
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"^infra/cloudrun/.*\.resolved\.json$"),
]

ALLOWED_PATH_PATTERNS = [
    re.compile(r"(^|/)\.env(\.[^/]+)?\.example$"),
]

ALLOWED_CONTENT_PATH_PATTERNS = [
    re.compile(r"^tools/check_repo_hygiene\.py$"),
    re.compile(r"^tests/test_repo_hygiene\.py$"),
]

FORBIDDEN_CONTENT_PATTERNS = [
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----"),
    re.compile(r"(?i)aws_secret_access_key"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._-]+"),
]


def _git_ls_files(root: Path) -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files"],
        cwd=root,
        text=True,
    )
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        tracked_files = _git_ls_files(root)
    except subprocess.CalledProcessError as exc:
        print(f"git ls-files failed: {exc}", file=sys.stderr)
        return 2
    if not tracked_files:
        print("repo hygiene check failed: git ls-files returned no tracked files", file=sys.stderr)
        return 1

    violations: list[str] = []
    for relative_path in tracked_files:
        relative_text = relative_path.as_posix()
        if any(pattern.search(relative_text) for pattern in ALLOWED_PATH_PATTERNS):
            continue
        if any(pattern.search(relative_text) for pattern in FORBIDDEN_PATH_PATTERNS):
            violations.append(f"forbidden tracked path: {relative_text}")
            continue
        candidate = root / relative_path
        if not candidate.is_file():
            continue
        if any(pattern.search(relative_text) for pattern in ALLOWED_CONTENT_PATH_PATTERNS):
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in FORBIDDEN_CONTENT_PATTERNS:
            if pattern.search(content):
                violations.append(f"forbidden content pattern in {relative_text}: {pattern.pattern}")
    if violations:
        for item in violations:
            print(item, file=sys.stderr)
        return 1
    print("repo hygiene check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
