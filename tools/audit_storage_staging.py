"""Read-only inventory of potential abandoned storage staging files.

Usage (from repository root with an explicitly configured, authorized storage
environment):
    python -m tools.audit_storage_staging --root inspection --max-directories 250

No --delete, --cleanup, --apply, or mutation path exists. Outputs metadata
only, and marks partial inventories explicitly.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from backend.app.storage.factory import create_storage_service_from_env
from backend.app.storage.staging import audit_staging_candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", choices=("inspection", "dkkd", "template"), action="append", required=True)
    parser.add_argument("--max-directories", type=int, default=250)
    parser.add_argument("--max-entries", type=int, default=10000)
    parser.add_argument("--max-depth", type=int, default=8)
    args = parser.parse_args(argv)

    service = create_storage_service_from_env()
    if service.config.storage_class not in {"synology_smb", "local_filesystem_fake"}:
        parser.error("Inventory requires an explicitly configured direct storage adapter.")

    report = audit_staging_candidates(
        service,
        roots=tuple(args.root),
        max_directories=args.max_directories,
        max_entries=args.max_entries,
        max_depth=args.max_depth,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 2 if report.truncated else 0


if __name__ == "__main__":
    raise SystemExit(main())
