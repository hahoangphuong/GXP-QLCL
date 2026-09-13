from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.document.c5e_certificate_detail_source_asset_contract import (
    ALLOWED_GXP_TYPES,
    ALLOWED_SOURCE_VARIANTS,
    load_source_asset_registry,
)

OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "c5e_certificate_detail_source_asset_registry_audit.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    assets = load_source_asset_registry()

    records: list[dict[str, object]] = []
    blockers: list[dict[str, object]] = []

    for asset in assets:
        path = source_root / asset.filename

        if not path.is_file():
            blockers.append(
                {
                    "code": "SOURCE_ASSET_MISSING",
                    "source_variant": asset.source_variant,
                    "gxp_type": asset.gxp_type,
                    "filename": asset.filename,
                }
            )
            records.append(
                {
                    "source_variant": asset.source_variant,
                    "gxp_type": asset.gxp_type,
                    "filename": asset.filename,
                    "exists": False,
                    "expected_sha256": asset.sha256,
                    "actual_sha256": None,
                    "checksum_match": False,
                }
            )
            continue

        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        checksum_match = actual_sha256 == asset.sha256

        if not checksum_match:
            blockers.append(
                {
                    "code": "SOURCE_ASSET_CHECKSUM_MISMATCH",
                    "source_variant": asset.source_variant,
                    "gxp_type": asset.gxp_type,
                    "filename": asset.filename,
                    "expected_sha256": asset.sha256,
                    "actual_sha256": actual_sha256,
                }
            )

        records.append(
            {
                "source_variant": asset.source_variant,
                "gxp_type": asset.gxp_type,
                "filename": asset.filename,
                "exists": True,
                "expected_sha256": asset.sha256,
                "actual_sha256": actual_sha256,
                "checksum_match": checksum_match,
            }
        )

    report = {
        "schema_version": (
            "c5e-certificate-detail-source-asset-registry-audit/v1"
        ),
        "status": (
            "SOURCE_ASSET_REGISTRY_VERIFIED"
            if not blockers
            else "SOURCE_ASSET_REGISTRY_BLOCKED"
        ),
        "scope": {
            "gxp_types": list(ALLOWED_GXP_TYPES),
            "source_variants": list(ALLOWED_SOURCE_VARIANTS),
            "gdp_in_scope": False,
        },
        "summary": {
            "asset_count": len(records),
            "verified_count": sum(
                1 for item in records if item["checksum_match"]
            ),
            "blocker_count": len(blockers),
        },
        "assets": records,
        "blockers": blockers,
        "invariants": {
            "gdp_excluded": True,
            "source_documents_modified": False,
            "production_renderer_modified": False,
            "copy_forward_reused": False,
            "unkeyed_entries_used": False,
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"STATUS={report['status']}")
    print(f"ASSETS={len(records)}")
    print(f"VERIFIED={report['summary']['verified_count']}")
    print(f"BLOCKERS={len(blockers)}")
    print(f"OUTPUT={OUTPUT}")

    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())