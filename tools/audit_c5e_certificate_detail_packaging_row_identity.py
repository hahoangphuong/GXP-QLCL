from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "c5e_certificate_detail_packaging_row_identity.json"
)

PVCN_ROW_PRI_PACK = 93
PVCN_ROW_SEC_PACK = 96


class PackagingRowIdentityError(RuntimeError):
    pass


def _load_gmp_rows(path: Path) -> list[dict]:
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    ranges = [
        item
        for item in (payload.get("named_ranges") or {}).values()
        if item.get("gxp_type") == "GMP"
    ]

    if len(ranges) != 1:
        raise PackagingRowIdentityError(
            "Expected exactly one GMP taxonomy named range; "
            f"found {len(ranges)}."
        )

    rows = list(ranges[0].get("rows") or [])

    if len(rows) < PVCN_ROW_SEC_PACK:
        raise PackagingRowIdentityError(
            "GMP taxonomy is shorter than the legacy "
            "PVCN_rowSecPack index."
        )

    return rows


def _identity(
    rows: list[dict],
    array_index: int,
) -> dict:
    # VBA PVCN_GxP is a 1-based Excel Range.Value array.
    row = rows[array_index - 1]

    return {
        "vba_array_index": array_index,
        "taxonomy_list_index_zero_based": array_index - 1,
        "source_order": row.get("source_order"),
        "source_excel_row": row.get("source_excel_row"),
        "node_key": row.get("key"),
        "description": row.get("description"),
        "main_topic": row.get("main_topic"),
        "short_render": row.get("short_render"),
        "no_expand": row.get("no_expand"),
        "raw_cells": row.get("raw_cells"),
    }


def _neighbor_window(
    rows: list[dict],
    array_index: int,
) -> list[dict]:
    result = []

    for index in range(
        max(1, array_index - 2),
        min(len(rows), array_index + 2) + 1,
    ):
        row = rows[index - 1]

        result.append(
            {
                "vba_array_index": index,
                "source_order": row.get("source_order"),
                "source_excel_row": row.get("source_excel_row"),
                "node_key": row.get("key"),
                "description": row.get("description"),
                "main_topic": row.get("main_topic"),
                "short_render": row.get("short_render"),
            }
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=(
            ROOT
            / "artifacts"
            / "legacy_snapshot"
            / "evaluation_scope_taxonomy.json"
        ),
    )

    args = parser.parse_args()

    rows = _load_gmp_rows(
        args.taxonomy.resolve()
    )

    primary = _identity(
        rows,
        PVCN_ROW_PRI_PACK,
    )

    secondary = _identity(
        rows,
        PVCN_ROW_SEC_PACK,
    )

    blockers = []

    for label, item in (
        ("primary", primary),
        ("secondary", secondary),
    ):
        if (
            item["source_order"]
            != item["vba_array_index"]
        ):
            blockers.append(
                {
                    "code": "VBA_INDEX_SOURCE_ORDER_MISMATCH",
                    "label": label,
                    "vba_array_index": (
                        item["vba_array_index"]
                    ),
                    "source_order": (
                        item["source_order"]
                    ),
                }
            )

        if not str(
            item.get("node_key") or ""
        ).strip():
            blockers.append(
                {
                    "code": "PACKAGING_ROW_KEY_BLANK",
                    "label": label,
                }
            )

    report = {
        "schema_version": (
            "c5e-certificate-detail-"
            "packaging-row-identity/v1"
        ),
        "status": (
            "PACKAGING_ROW_IDENTITY_VERIFIED"
            if not blockers
            else "PACKAGING_ROW_IDENTITY_BLOCKED"
        ),
        "legacy_constants": {
            "PVCN_rowPriPack": PVCN_ROW_PRI_PACK,
            "PVCN_rowSecPack": PVCN_ROW_SEC_PACK,
        },
        "primary_pack": primary,
        "secondary_pack": secondary,
        "primary_neighbor_window": (
            _neighbor_window(
                rows,
                PVCN_ROW_PRI_PACK,
            )
        ),
        "secondary_neighbor_window": (
            _neighbor_window(
                rows,
                PVCN_ROW_SEC_PACK,
            )
        ),
        "blockers": blockers,
        "invariants": {
            "gdp_in_scope": False,
            "prose_matching_used": False,
            "fuzzy_matching_used": False,
            "unkeyed_entries_used": False,
            "production_code_modified": False,
        },
    }

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"STATUS={report['status']}")

    print(
        "PRIMARY="
        f"index={primary['vba_array_index']}|"
        f"source_order={primary['source_order']}|"
        f"excel_row={primary['source_excel_row']}|"
        f"key={primary['node_key']}|"
        f"main_topic={primary['main_topic']!r}|"
        f"description={primary['description']!r}"
    )

    print(
        "SECONDARY="
        f"index={secondary['vba_array_index']}|"
        f"source_order={secondary['source_order']}|"
        f"excel_row={secondary['source_excel_row']}|"
        f"key={secondary['node_key']}|"
        f"main_topic={secondary['main_topic']!r}|"
        f"description={secondary['description']!r}"
    )

    print(f"BLOCKERS={len(blockers)}")
    print(f"OUTPUT={OUTPUT}")

    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())