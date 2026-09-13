from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "c5e_certificate_detail_taxonomy_bookmark_coverage.json"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W_NAME = f"{{{W_NS}}}name"

GXP_TYPES = ("GMP", "GLP", "GSP")

SOURCE_VARIANTS = {
    "certificate_9": "9. Phamvi{gxp}.docx",
    "appendix_z3": "z3. Phamvi{gxp}.docx",
}


class TaxonomyBookmarkCoverageError(RuntimeError):
    pass


def key2bookmark(node_key: str) -> str:
    value = str(node_key or "").strip()

    if not value:
        raise TaxonomyBookmarkCoverageError(
            "Taxonomy node_key must not be blank."
        )

    # Exact legacy Key2Bookmark semantics:
    # trim -> remove ONE final period -> prefix L -> "." to "_"
    if value.endswith("."):
        value = value[:-1]

    return "L" + value.replace(".", "_")


def _load_taxonomy(path: Path) -> dict[str, list[dict]]:
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    named_ranges = payload.get("named_ranges") or {}

    result: dict[str, list[dict]] = {}

    for gxp in GXP_TYPES:
        matches = [
            item
            for item in named_ranges.values()
            if item.get("gxp_type") == gxp
        ]

        if len(matches) != 1:
            raise TaxonomyBookmarkCoverageError(
                f"Expected exactly one taxonomy range for "
                f"{gxp}; found {len(matches)}."
            )

        rows = list(matches[0].get("rows") or ())

        if not rows:
            raise TaxonomyBookmarkCoverageError(
                f"Taxonomy range for {gxp} is empty."
            )

        result[gxp] = rows

    return result


def _find_source(
    source_root: Path,
    filename: str,
) -> Path:
    direct = source_root / filename

    if direct.is_file():
        return direct

    matches = list(
        source_root.rglob(filename)
    )

    if len(matches) != 1:
        raise TaxonomyBookmarkCoverageError(
            f"Expected exactly one source document "
            f"{filename!r}; found {len(matches)}."
        )

    return matches[0]


def _load_bookmarks(path: Path) -> set[str]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            document_xml = archive.read(
                "word/document.xml"
            )

    except (zipfile.BadZipFile, KeyError) as exc:
        raise TaxonomyBookmarkCoverageError(
            f"{path.name!r} is not a valid DOCX "
            "with word/document.xml."
        ) from exc

    root = ET.fromstring(document_xml)

    return {
        node.attrib[W_NAME]
        for node in root.iter(
            f"{{{W_NS}}}bookmarkStart"
        )
        if W_NAME in node.attrib
    }


def _row_metadata(
    row: dict,
    bookmark: str,
) -> dict:
    return {
        "source_order": row.get("source_order"),
        "source_excel_row": row.get(
            "source_excel_row"
        ),
        "node_key": row.get("key"),
        "bookmark": bookmark,
        "description": row.get("description"),
        "main_topic": row.get("main_topic"),
        "short_render": row.get("short_render"),
        "no_expand": row.get("no_expand"),
    }


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

    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    taxonomy = _load_taxonomy(
        args.taxonomy.resolve()
    )

    source_root = args.source_root.resolve()

    source_bookmarks = {}
    source_documents = []

    for source_variant, pattern in (
        SOURCE_VARIANTS.items()
    ):
        for gxp_type in GXP_TYPES:
            filename = pattern.format(
                gxp=gxp_type
            )

            source_path = _find_source(
                source_root,
                filename,
            )

            bookmarks = _load_bookmarks(
                source_path
            )

            source_bookmarks[
                (source_variant, gxp_type)
            ] = bookmarks

            source_documents.append(
                {
                    "source_variant": (
                        source_variant
                    ),
                    "gxp_type": gxp_type,
                    "filename": filename,
                    "bookmark_count": len(
                        bookmarks
                    ),
                }
            )

    rows_report = []
    blockers = []

    total_checks = 0
    exact_coverage = 0

    for gxp_type, rows in taxonomy.items():
        seen_keys = set()
        seen_bookmarks = set()

        for row in rows:
            node_key = str(
                row.get("key") or ""
            ).strip()

            if not node_key:
                blockers.append(
                    {
                        "code": (
                            "BLANK_TAXONOMY_NODE_KEY"
                        ),
                        "gxp_type": gxp_type,
                        "source_order": row.get(
                            "source_order"
                        ),
                    }
                )
                continue

            bookmark = key2bookmark(
                node_key
            )

            if node_key in seen_keys:
                blockers.append(
                    {
                        "code": (
                            "DUPLICATE_TAXONOMY_NODE_KEY"
                        ),
                        "gxp_type": gxp_type,
                        "node_key": node_key,
                    }
                )

            seen_keys.add(node_key)

            if bookmark in seen_bookmarks:
                blockers.append(
                    {
                        "code": (
                            "KEY2BOOKMARK_COLLISION"
                        ),
                        "gxp_type": gxp_type,
                        "node_key": node_key,
                        "bookmark": bookmark,
                    }
                )

            seen_bookmarks.add(bookmark)

            coverage = {}

            for source_variant in (
                SOURCE_VARIANTS
            ):
                total_checks += 1

                present = (
                    bookmark
                    in source_bookmarks[
                        (
                            source_variant,
                            gxp_type,
                        )
                    ]
                )

                coverage[
                    source_variant
                ] = present

                if present:
                    exact_coverage += 1
                else:
                    blockers.append(
                        {
                            "code": (
                                "SOURCE_BOOKMARK_MISSING"
                            ),
                            "gxp_type": (
                                gxp_type
                            ),
                            "source_variant": (
                                source_variant
                            ),
                            "node_key": (
                                node_key
                            ),
                            "bookmark": (
                                bookmark
                            ),
                        }
                    )

            item = _row_metadata(
                row,
                bookmark,
            )

            item["coverage"] = coverage

            rows_report.append(
                {
                    "gxp_type": gxp_type,
                    **item,
                }
            )

    # Active VBA treats these GMP packaging rows specially.
    packaging_special = []

    gmp_by_key = {
        str(row.get("key") or "").strip(): row
        for row in taxonomy["GMP"]
    }

    for node_key in ("6.1", "6.2"):
        row = gmp_by_key.get(node_key)

        if row is None:
            blockers.append(
                {
                    "code": (
                        "GMP_PACKAGING_SPECIAL_KEY_MISSING"
                    ),
                    "node_key": node_key,
                }
            )
            continue

        bookmark = key2bookmark(
            node_key
        )

        item = _row_metadata(
            row,
            bookmark,
        )

        item["coverage"] = {
            source_variant: (
                bookmark
                in source_bookmarks[
                    (
                        source_variant,
                        "GMP",
                    )
                ]
            )
            for source_variant
            in SOURCE_VARIANTS
        }

        packaging_special.append(
            item
        )

    report = {
        "schema_version": (
            "c5e-certificate-detail-"
            "taxonomy-bookmark-coverage/v1"
        ),
        "status": (
            "TAXONOMY_BOOKMARK_COVERAGE_VERIFIED"
            if not blockers
            else "TAXONOMY_BOOKMARK_COVERAGE_BLOCKED"
        ),
        "scope": {
            "gxp_types": list(
                GXP_TYPES
            ),
            "source_variants": list(
                SOURCE_VARIANTS
            ),
            "gdp_in_scope": False,
        },
        "key2bookmark_contract": {
            "examples": {
                "1": "L1",
                "1.": "L1",
                "1.1": "L1_1",
                "6.1": "L6_1",
                "6.2": "L6_2",
            }
        },
        "summary": {
            "taxonomy_node_count": len(
                rows_report
            ),
            "source_document_count": len(
                source_documents
            ),
            "coverage_check_count": (
                total_checks
            ),
            "exact_coverage_count": (
                exact_coverage
            ),
            "blocker_count": len(
                blockers
            ),
        },
        "source_documents": (
            source_documents
        ),
        "packaging_special_gmp": (
            packaging_special
        ),
        "rows": rows_report,
        "blockers": blockers,
        "invariants": {
            "exact_key_only": True,
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

    print(
        f"STATUS={report['status']}"
    )
    print(
        "TAXONOMY_NODES="
        f"{len(rows_report)}"
    )
    print(
        "SOURCE_DOCUMENTS="
        f"{len(source_documents)}"
    )
    print(
        f"COVERAGE_CHECKS={total_checks}"
    )
    print(
        f"EXACT_COVERAGE={exact_coverage}"
    )
    print(
        f"BLOCKERS={len(blockers)}"
    )

    for item in packaging_special:
        print(
            "PACKAGING_SPECIAL="
            f"{item['node_key']}|"
            f"{item['bookmark']}|"
            "certificate_9="
            f"{item['coverage']['certificate_9']}|"
            "appendix_z3="
            f"{item['coverage']['appendix_z3']}|"
            "main_topic="
            f"{item.get('main_topic')!r}|"
            "no_expand="
            f"{item.get('no_expand')!r}"
        )

    print(f"OUTPUT={OUTPUT}")

    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())