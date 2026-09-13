from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.document.c5e_certificate_detail_fragment_extractor import (
    extract_bookmark_table_fragment_from_docx_bytes,
)

OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "c5e_certificate_detail_runtime_extractor_parity.json"
)


def _normalized_sha(xml: str) -> str:
    root = ET.fromstring(xml)

    payload = ET.tostring(
        root,
        encoding="utf-8",
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


def _walk(
    value,
    *,
    document: str,
    output: list[dict],
):
    if isinstance(value, dict):
        fragment_xml = value.get(
            "fragment_xml"
        )

        if isinstance(
            fragment_xml,
            str,
        ):
            output.append(
                {
                    "document": document,
                    "bookmark": (
                        value.get("bookmark")
                        or value.get(
                            "bookmark_name"
                        )
                        or value.get("name")
                        or value.get(
                            "source_bookmark"
                        )
                    ),
                    "fragment_xml": (
                        fragment_xml
                    ),
                }
            )

        for child in value.values():
            _walk(
                child,
                document=document,
                output=output,
            )

    elif isinstance(value, list):
        for child in value:
            _walk(
                child,
                document=document,
                output=output,
            )


def _fixture_records(
    fixture_path: Path,
):
    payload = json.loads(
        fixture_path.read_text(
            encoding="utf-8"
        )
    )

    document = (
        payload.get("filename")
        or payload.get("document")
        or payload.get(
            "source_document"
        )
        or fixture_path.name.replace(
            ".cross-container.json",
            "",
        )
    )

    result = []

    _walk(
        payload,
        document=str(document),
        output=result,
    )

    return result


def _source_path(
    source_root: Path,
    filename: str,
) -> Path:
    direct = (
        source_root
        / filename
    )

    if direct.is_file():
        return direct

    matches = list(
        source_root.rglob(
            filename
        )
    )

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one source "
            f"{filename!r}; "
            f"found {len(matches)}."
        )

    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--fixture-dir",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    fixture_paths = sorted(
        args.fixture_dir.resolve().glob(
            "*.cross-container.json"
        )
    )

    records = []

    for fixture_path in fixture_paths:
        records.extend(
            _fixture_records(
                fixture_path
            )
        )

    source_cache = {}

    mismatches = []

    for record in records:
        document = record["document"]

        if document not in source_cache:
            source_cache[
                document
            ] = (
                _source_path(
                    args.source_root.resolve(),
                    document,
                ).read_bytes()
            )

        bookmark = record[
            "bookmark"
        ]

        extracted = (
            extract_bookmark_table_fragment_from_docx_bytes(
                source_cache[
                    document
                ],
                bookmark_name=bookmark,
            )
        )

        expected_sha = (
            _normalized_sha(
                record[
                    "fragment_xml"
                ]
            )
        )

        actual_sha = (
            _normalized_sha(
                extracted.fragment_xml
            )
        )

        if (
            expected_sha
            != actual_sha
        ):
            mismatches.append(
                {
                    "document": document,
                    "bookmark": bookmark,
                    "expected_sha256": (
                        expected_sha
                    ),
                    "actual_sha256": (
                        actual_sha
                    ),
                }
            )

    report = {
        "schema_version": (
            "c5e-runtime-extractor-"
            "parity/v1"
        ),
        "status": (
            "RUNTIME_EXTRACTOR_PARITY_VERIFIED"
            if not mismatches
            else "RUNTIME_EXTRACTOR_PARITY_BLOCKED"
        ),
        "summary": {
            "document_count": len(
                source_cache
            ),
            "fragment_count": len(
                records
            ),
            "matched_count": (
                len(records)
                - len(mismatches)
            ),
            "mismatch_count": len(
                mismatches
            ),
        },
        "mismatches": mismatches,
        "invariants": {
            "gdp_in_scope": False,
            "production_service_modified": False,
            "copy_forward_used": False,
            "unkeyed_entries_used": False,
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
        f"DOCUMENTS="
        f"{len(source_cache)}"
    )
    print(
        f"FRAGMENTS="
        f"{len(records)}"
    )
    print(
        "MATCHED="
        f"{len(records)-len(mismatches)}"
    )
    print(
        f"MISMATCHES="
        f"{len(mismatches)}"
    )
    print(
        f"OUTPUT={OUTPUT}"
    )

    return (
        0
        if not mismatches
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())