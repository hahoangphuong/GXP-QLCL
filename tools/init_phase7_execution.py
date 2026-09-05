from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from tools.phase7_execution_evidence import (
    TEMPLATE_PATH,
    Phase7ExecutionEvidenceError,
    resolve_execution_evidence_paths,
)


def initialize_execution_evidence(output_dir: Path) -> Path:
    paths = resolve_execution_evidence_paths(output_dir)
    if paths.evidence_dir.exists() and not paths.evidence_dir.is_dir():
        raise Phase7ExecutionEvidenceError(
            f"Phase 7 execution evidence path is not a directory: {paths.evidence_dir}"
        )
    if paths.checklist_path.exists():
        raise Phase7ExecutionEvidenceError(
            f"Refusing to overwrite existing Phase 7 execution checklist: {paths.checklist_path}"
        )
    paths.evidence_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE_PATH, paths.checklist_path)
    return paths.checklist_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize external Phase 7 execution evidence.")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        checklist_path = initialize_execution_evidence(args.output_dir)
    except Phase7ExecutionEvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Created {checklist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
