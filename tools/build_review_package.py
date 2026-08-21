from __future__ import annotations

import argparse
import fnmatch
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


FORBIDDEN_REVIEW_PATTERNS = (
    ".git/*",
    "legacy/*",
    "artifacts/*",
    "dist/*",
    "frontend/node_modules/*",
    "frontend/dist/*",
    "__pycache__/*",
    "*/__pycache__/*",
    ".pytest_cache/*",
    "*/.pytest_cache/*",
    "*.pyc",
    "*.pyo",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    ".env",
    ".env.*",
)

ALLOWED_REVIEW_EXCEPTIONS = (
    ".env.example",
    ".env.*.example",
)

FIXED_ZIP_TIMESTAMP = (2026, 8, 20, 0, 0, 0)


def _git_ls_files(root: Path) -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], cwd=root, text=True)
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


def _is_excluded(relative_text: str) -> bool:
    normalized = relative_text.replace("\\", "/")
    for pattern in ALLOWED_REVIEW_EXCEPTIONS:
        if fnmatch.fnmatch(normalized, pattern):
            return False
    for pattern in FORBIDDEN_REVIEW_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def collect_review_package_members(root: Path) -> list[Path]:
    try:
        candidates = _git_ls_files(root)
    except subprocess.CalledProcessError:
        candidates = [path.relative_to(root) for path in root.rglob("*") if path.is_file()]
    if not candidates:
        candidates = [path.relative_to(root) for path in root.rglob("*") if path.is_file()]

    members: list[Path] = []
    for relative_path in sorted(candidates, key=lambda item: item.as_posix()):
        relative_text = relative_path.as_posix()
        if _is_excluded(relative_text):
            continue
        candidate_path = root / relative_path
        if candidate_path.is_symlink():
            raise RuntimeError(f"Refusing to package symlinked file: {relative_text}")
        absolute_path = candidate_path.resolve()
        if not absolute_path.is_file():
            continue
        try:
            absolute_path.relative_to(root.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Refusing to package file outside repository root: {absolute_path}") from exc
        members.append(relative_path)
    return members


def build_review_package(root: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    members = collect_review_package_members(root)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for relative_path in members:
            absolute_path = root / relative_path
            zip_info = ZipInfo(relative_path.as_posix(), FIXED_ZIP_TIMESTAMP)
            zip_info.compress_type = ZIP_DEFLATED
            zip_info.create_system = 3
            zip_info.external_attr = (0o100644 & 0xFFFF) << 16
            data = absolute_path.read_bytes()
            archive.writestr(zip_info, data)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sanitized repository review package zip.")
    parser.add_argument(
        "--output",
        default="dist/GXP-QLCL-review.zip",
        help="Output zip path relative to repository root.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output_path = (root / args.output).resolve()
    build_review_package(root, output_path)
    size_bytes = output_path.stat().st_size
    print(f"review package created: {output_path} ({size_bytes} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
