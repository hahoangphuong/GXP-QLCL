from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
import zipfile
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]

#
# Direct execution:
#
#     py tools/audit_c5e_certificate_detail_fragment_cell_geometry.py
#
# puts tools/ rather than the repository root on sys.path.
# Add the repository root explicitly so this audit imports
# and reuses the real production extractor.
#
if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )


from backend.app.document.c5e_certificate_detail_fragment_extractor import (
    CertificateDetailFragmentExtractionError,
    extract_bookmark_table_fragment_from_docx_bytes,
)


WORD_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)

NS = {
    "w": WORD_NS,
}


SOURCE_FILENAMES = (
    "9. PhamviGLP.docx",
    "9. PhamviGMP.docx",
    "9. PhamviGSP.docx",
    "z3. PhamviGLP.docx",
    "z3. PhamviGMP.docx",
    "z3. PhamviGSP.docx",
)


EXPECTED_BOOKMARK_COUNTS = {
    "9. PhamviGLP.docx": 237,
    "9. PhamviGMP.docx": 112,
    "9. PhamviGSP.docx": 52,
    "z3. PhamviGLP.docx": 237,
    "z3. PhamviGMP.docx": 112,
    "z3. PhamviGSP.docx": 52,
}


DEFAULT_OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "c5e_certificate_detail_fragment_cell_geometry.json"
)


def _w(
    tag: str,
) -> str:
    return (
        f"{{{WORD_NS}}}{tag}"
    )


def _find_exact_file(
    root: Path,
    filename: str,
) -> Path:
    matches = []

    for path in root.rglob(
        filename
    ):
        if ".git" in path.parts:
            continue

        if not path.is_file():
            continue

        matches.append(
            path.resolve()
        )

    unique = sorted(
        set(matches)
    )

    if len(unique) != 1:
        raise RuntimeError(
            "Expected exactly one "
            f"{filename!r} below "
            f"{root}; found "
            f"{len(unique)}: "
            + ", ".join(
                str(path)
                for path in unique
            )
        )

    return unique[0]


def _document_xml_from_docx(
    path: Path,
) -> bytes:
    try:
        with zipfile.ZipFile(
            path,
            "r",
        ) as archive:
            return archive.read(
                "word/document.xml"
            )

    except (
        zipfile.BadZipFile,
        KeyError,
    ) as exc:
        raise RuntimeError(
            "Invalid DOCX source asset: "
            f"{path}"
        ) from exc


def _bookmark_names(
    document_xml: bytes,
) -> list[str]:
    root = ET.fromstring(
        document_xml
    )

    result = []

    for node in root.findall(
        ".//w:bookmarkStart",
        NS,
    ):
        name = node.attrib.get(
            _w("name")
        )

        if not name:
            continue

        #
        # Skip Word-internal bookmarks.
        #
        if name.startswith("_"):
            continue

        result.append(
            name
        )

    return result


def _cell_text(
    cell: ET.Element,
) -> str:
    parts = []

    for node in cell.findall(
        ".//w:t",
        NS,
    ):
        if node.text:
            parts.append(
                node.text
            )

    return "".join(
        parts
    )


def _grid_span(
    cell: ET.Element,
) -> int:
    node = cell.find(
        "./w:tcPr/w:gridSpan",
        NS,
    )

    if node is None:
        return 1

    raw = node.attrib.get(
        _w("val")
    )

    try:
        value = int(
            raw or "1"
        )

    except ValueError:
        return 1

    return max(
        value,
        1,
    )


def _vmerge(
    cell: ET.Element,
) -> str | None:
    node = cell.find(
        "./w:tcPr/w:vMerge",
        NS,
    )

    if node is None:
        return None

    return (
        node.attrib.get(
            _w("val")
        )
        or "continue"
    )


def _fragment_profile(
    fragment_xml: str,
) -> dict:
    root = ET.fromstring(
        fragment_xml
    )

    if root.tag != _w("tbl"):
        raise RuntimeError(
            "Extracted fragment root "
            "is not w:tbl."
        )

    rows = root.findall(
        "./w:tr",
        NS,
    )

    row_profiles = []

    total_cells = 0

    for row_index, row in enumerate(
        rows,
        1,
    ):
        cells = row.findall(
            "./w:tc",
            NS,
        )

        total_cells += len(
            cells
        )

        cell_profiles = []

        for cell_index, cell in enumerate(
            cells,
            1,
        ):
            text = _cell_text(
                cell
            )

            cell_profiles.append(
                {
                    "cell_index": (
                        cell_index
                    ),
                    "grid_span": (
                        _grid_span(
                            cell
                        )
                    ),
                    "vmerge": (
                        _vmerge(
                            cell
                        )
                    ),
                    "text": text,
                    "text_length": (
                        len(text)
                    ),
                    "paragraph_count": (
                        len(
                            cell.findall(
                                "./w:p",
                                NS,
                            )
                        )
                    ),
                }
            )

        row_profiles.append(
            {
                "row_index": (
                    row_index
                ),
                "cell_count": (
                    len(cells)
                ),
                "cells": (
                    cell_profiles
                ),
            }
        )

    if not rows:
        raise RuntimeError(
            "Extracted w:tbl "
            "contains no direct w:tr."
        )

    if total_cells == 0:
        raise RuntimeError(
            "Extracted w:tbl "
            "contains no direct w:tc."
        )

    row_cell_counts = tuple(
        row[
            "cell_count"
        ]
        for row in row_profiles
    )

    grid_spans = tuple(
        tuple(
            cell[
                "grid_span"
            ]
            for cell in row[
                "cells"
            ]
        )
        for row in row_profiles
    )

    vmerge_shape = tuple(
        tuple(
            cell[
                "vmerge"
            ]
            or "-"
            for cell in row[
                "cells"
            ]
        )
        for row in row_profiles
    )

    geometry_key = (
        "rows="
        f"{len(rows)}"
        "|cells="
        + ",".join(
            str(value)
            for value
            in row_cell_counts
        )
        + "|grid="
        + ";".join(
            ",".join(
                str(value)
                for value
                in row
            )
            for row
            in grid_spans
        )
        + "|vmerge="
        + ";".join(
            ",".join(
                value
                for value
                in row
            )
            for row
            in vmerge_shape
        )
    )

    return {
        "row_count": (
            len(rows)
        ),
        "total_cell_count": (
            total_cells
        ),
        "row_cell_counts": (
            list(
                row_cell_counts
            )
        ),
        "geometry_key": (
            geometry_key
        ),
        "rows": (
            row_profiles
        ),
    }


def audit(
    *,
    search_root: Path,
) -> dict:
    blockers = []

    documents = []

    geometry_counts: Counter[
        str
    ] = Counter()

    geometry_examples: dict[
        str,
        list[dict],
    ] = defaultdict(
        list
    )

    total_fragments = 0

    for filename in (
        SOURCE_FILENAMES
    ):
        try:
            path = _find_exact_file(
                search_root,
                filename,
            )

        except RuntimeError as exc:
            blockers.append(
                {
                    "code": (
                        "SOURCE_ASSET_RESOLUTION_ERROR"
                    ),
                    "filename": (
                        filename
                    ),
                    "detail": str(
                        exc
                    ),
                }
            )
            continue

        source_bytes = (
            path.read_bytes()
        )

        try:
            document_xml = (
                _document_xml_from_docx(
                    path
                )
            )

        except RuntimeError as exc:
            blockers.append(
                {
                    "code": (
                        "SOURCE_DOCUMENT_XML_ERROR"
                    ),
                    "filename": (
                        filename
                    ),
                    "detail": (
                        str(exc)
                    ),
                }
            )
            continue

        try:
            bookmarks = (
                _bookmark_names(
                    document_xml
                )
            )

        except ET.ParseError as exc:
            blockers.append(
                {
                    "code": (
                        "SOURCE_DOCUMENT_XML_PARSE_ERROR"
                    ),
                    "filename": (
                        filename
                    ),
                    "detail": (
                        str(exc)
                    ),
                }
            )
            continue

        expected = (
            EXPECTED_BOOKMARK_COUNTS[
                filename
            ]
        )

        if (
            len(bookmarks)
            != expected
        ):
            blockers.append(
                {
                    "code": (
                        "BOOKMARK_COUNT_MISMATCH"
                    ),
                    "filename": (
                        filename
                    ),
                    "expected": (
                        expected
                    ),
                    "actual": (
                        len(
                            bookmarks
                        )
                    ),
                }
            )

        document_fragments = []

        for bookmark_name in (
            bookmarks
        ):
            try:
                extracted = (
                    extract_bookmark_table_fragment_from_docx_bytes(
                        source_bytes,
                        bookmark_name=(
                            bookmark_name
                        ),
                    )
                )

                profile = (
                    _fragment_profile(
                        extracted.fragment_xml
                    )
                )

            except (
                CertificateDetailFragmentExtractionError,
                RuntimeError,
                ET.ParseError,
            ) as exc:
                blockers.append(
                    {
                        "code": (
                            "FRAGMENT_PROFILE_ERROR"
                        ),
                        "filename": (
                            filename
                        ),
                        "bookmark": (
                            bookmark_name
                        ),
                        "detail": (
                            str(exc)
                        ),
                    }
                )
                continue

            total_fragments += 1

            geometry_key = (
                profile[
                    "geometry_key"
                ]
            )

            geometry_counts[
                geometry_key
            ] += 1

            if (
                len(
                    geometry_examples[
                        geometry_key
                    ]
                )
                < 5
            ):
                geometry_examples[
                    geometry_key
                ].append(
                    {
                        "filename": (
                            filename
                        ),
                        "bookmark": (
                            bookmark_name
                        ),
                        "visible_text": (
                            extracted.visible_text
                        ),
                        "rows": (
                            profile[
                                "rows"
                            ]
                        ),
                    }
                )

            document_fragments.append(
                {
                    "bookmark": (
                        bookmark_name
                    ),
                    "extractor_geometry_shape": (
                        extracted.geometry_shape
                    ),
                    "visible_text": (
                        extracted.visible_text
                    ),
                    **profile,
                }
            )

        documents.append(
            {
                "filename": (
                    filename
                ),
                "path": str(
                    path
                ),
                "bookmark_count": (
                    len(bookmarks)
                ),
                "fragment_count": (
                    len(
                        document_fragments
                    )
                ),
                "fragments": (
                    document_fragments
                ),
            }
        )

    expected_total = sum(
        EXPECTED_BOOKMARK_COUNTS.values()
    )

    if (
        total_fragments
        != expected_total
    ):
        blockers.append(
            {
                "code": (
                    "TOTAL_FRAGMENT_COUNT_MISMATCH"
                ),
                "expected": (
                    expected_total
                ),
                "actual": (
                    total_fragments
                ),
            }
        )

    return {
        "schema_version": (
            "c5e-certificate-detail-"
            "fragment-cell-geometry/v1"
        ),
        "status": (
            "FRAGMENT_CELL_GEOMETRY_PROFILED"
            if not blockers
            else "FRAGMENT_CELL_GEOMETRY_BLOCKED"
        ),
        "summary": {
            "documents": (
                len(documents)
            ),
            "fragments": (
                total_fragments
            ),
            "geometry_shapes": (
                len(
                    geometry_counts
                )
            ),
            "blockers": (
                len(blockers)
            ),
        },
        "geometry_counts": dict(
            sorted(
                geometry_counts.items()
            )
        ),
        "geometry_examples": {
            key: value
            for key, value
            in sorted(
                geometry_examples.items()
            )
        },
        "documents": (
            documents
        ),
        "blockers": (
            blockers
        ),
        "invariants": {
            "production_extractor_reused": (
                True
            ),
            "fragment_root_required_w_tbl": (
                True
            ),
            "unknown_geometry_not_interpreted": (
                True
            ),
            "english_cell_not_inferred": (
                True
            ),
            "gdp_in_scope": False,
            "unkeyed_entries_used": (
                False
            ),
        },
    }


def main() -> int:
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--search-root",
        type=Path,
        default=ROOT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = (
        parser.parse_args()
    )

    report = audit(
        search_root=(
            args.search_root.resolve()
        )
    )

    output = (
        args.output.resolve()
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary = (
        report["summary"]
    )

    print(
        f"STATUS={report['status']}"
    )

    print(
        "DOCUMENTS="
        f"{summary['documents']}"
    )

    print(
        "FRAGMENTS="
        f"{summary['fragments']}"
    )

    print(
        "GEOMETRY_SHAPES="
        f"{summary['geometry_shapes']}"
    )

    print(
        "BLOCKERS="
        f"{summary['blockers']}"
    )

    for (
        geometry,
        count,
    ) in sorted(
        report[
            "geometry_counts"
        ].items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            "GEOMETRY="
            f"{count}|{geometry}"
        )

    print(
        f"OUTPUT={output}"
    )

    return (
        0
        if not report[
            "blockers"
        ]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )