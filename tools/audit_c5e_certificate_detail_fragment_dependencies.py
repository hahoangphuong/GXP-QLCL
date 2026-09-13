from __future__ import annotations

import argparse
import collections
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "artifacts"
    / "legacy_audit"
    / "c5e_certificate_detail_fragment_dependencies.json"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W_NS}

UNSUPPORTED_STRUCTURAL_TAGS = {
    "drawing",
    "object",
    "altChunk",
    "sectPr",
}


class DependencyAuditError(RuntimeError):
    pass


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def local(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _walk_fragment_records(
    value,
    *,
    document_name: str,
    out: list[dict],
) -> None:
    if isinstance(value, dict):
        fragment_xml = value.get("fragment_xml")

        if isinstance(fragment_xml, str):
            out.append(
                {
                    "document": document_name,
                    "bookmark": (
                        value.get("bookmark")
                        or value.get("bookmark_name")
                        or value.get("name")
                        or value.get("source_bookmark")
                    ),
                    "fragment_xml": fragment_xml,
                }
            )

        for child in value.values():
            _walk_fragment_records(
                child,
                document_name=document_name,
                out=out,
            )

    elif isinstance(value, list):
        for child in value:
            _walk_fragment_records(
                child,
                document_name=document_name,
                out=out,
            )


def load_fragment_fixture(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    document_name = (
        payload.get("filename")
        or payload.get("document")
        or payload.get("source_document")
        or path.name.replace(".cross-container.json", "")
    )

    records: list[dict] = []

    _walk_fragment_records(
        payload,
        document_name=str(document_name),
        out=records,
    )

    return records


def load_docx_metadata(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        names = set(archive.namelist())

        styles = set()

        if "word/styles.xml" in names:
            root = ET.fromstring(
                archive.read("word/styles.xml")
            )

            for style in root.findall(".//w:style", NS):
                style_id = style.attrib.get(w("styleId"))

                if style_id:
                    styles.add(style_id)

        num_ids = set()

        if "word/numbering.xml" in names:
            root = ET.fromstring(
                archive.read("word/numbering.xml")
            )

            for node in root.findall(".//w:num", NS):
                num_id = node.attrib.get(w("numId"))

                if num_id:
                    num_ids.add(num_id)

        relationships = {}

        rel_path = "word/_rels/document.xml.rels"

        if rel_path in names:
            root = ET.fromstring(
                archive.read(rel_path)
            )

            for rel in list(root):
                rel_id = rel.attrib.get("Id")

                if rel_id:
                    relationships[rel_id] = {
                        "type": rel.attrib.get("Type"),
                        "target": rel.attrib.get("Target"),
                        "target_mode": rel.attrib.get("TargetMode"),
                    }

    return {
        "styles": styles,
        "num_ids": num_ids,
        "relationships": relationships,
    }


def scan_fragment(record: dict) -> dict:
    try:
        root = ET.fromstring(
            record["fragment_xml"]
        )
    except ET.ParseError as exc:
        raise DependencyAuditError(
            "Invalid fragment XML for "
            f"{record['document']}::{record.get('bookmark')}"
        ) from exc

    style_refs = {
        "pStyle": set(),
        "rStyle": set(),
        "tblStyle": set(),
    }

    for kind in style_refs:
        for node in root.findall(
            f".//w:{kind}",
            NS,
        ):
            value = node.attrib.get(w("val"))

            if value:
                style_refs[kind].add(value)

    num_ids = set()

    for node in root.findall(
        ".//w:numId",
        NS,
    ):
        value = node.attrib.get(w("val"))

        if value and value != "0":
            num_ids.add(value)

    relationship_ids = set()

    for node in root.iter():
        for attr_name, attr_value in node.attrib.items():
            if attr_name.startswith(
                f"{{{R_NS}}}"
            ):
                relationship_ids.add(attr_value)

    structural_tags = {
        local(node.tag)
        for node in root.iter()
        if local(node.tag)
        in UNSUPPORTED_STRUCTURAL_TAGS
    }

    return {
        "document": record["document"],
        "bookmark": record.get("bookmark"),
        "style_refs": {
            key: sorted(value)
            for key, value
            in style_refs.items()
        },
        "num_ids": sorted(num_ids),
        "relationship_ids": sorted(
            relationship_ids
        ),
        "unsupported_structural_tags": sorted(
            structural_tags
        ),
    }


def find_source_doc(
    source_root: Path,
    document_name: str,
) -> Path:
    direct = source_root / document_name

    if direct.is_file():
        return direct

    matches = list(
        source_root.rglob(document_name)
    )

    if len(matches) != 1:
        raise DependencyAuditError(
            "Expected exactly one source DOCX "
            f"for {document_name!r}; "
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

    if not fixture_paths:
        raise DependencyAuditError(
            "No cross-container fixture files found."
        )

    all_records = []

    for path in fixture_paths:
        all_records.extend(
            load_fragment_fixture(path)
        )

    if not all_records:
        raise DependencyAuditError(
            "No fragment_xml records found."
        )

    by_document = collections.defaultdict(list)

    for record in all_records:
        by_document[
            record["document"]
        ].append(record)

    fragment_reports = []
    blockers = []
    global_counts = collections.Counter()
    document_reports = []

    for document_name, records in sorted(
        by_document.items()
    ):
        source_path = find_source_doc(
            args.source_root.resolve(),
            document_name,
        )

        metadata = load_docx_metadata(
            source_path
        )

        document_counts = (
            collections.Counter()
        )

        document_fragment_reports = []

        for record in records:
            report = scan_fragment(record)

            missing_styles = []

            for kind, refs in (
                report["style_refs"].items()
            ):
                for style_id in refs:
                    if (
                        style_id
                        not in metadata["styles"]
                    ):
                        missing_styles.append(
                            {
                                "kind": kind,
                                "style_id": style_id,
                            }
                        )

            missing_num_ids = [
                num_id
                for num_id in report["num_ids"]
                if num_id
                not in metadata["num_ids"]
            ]

            unresolved_relationships = [
                rel_id
                for rel_id
                in report["relationship_ids"]
                if rel_id
                not in metadata[
                    "relationships"
                ]
            ]

            relationship_details = {
                rel_id: metadata[
                    "relationships"
                ][rel_id]
                for rel_id
                in report["relationship_ids"]
                if rel_id
                in metadata["relationships"]
            }

            report[
                "missing_styles_in_source"
            ] = missing_styles

            report[
                "missing_num_ids_in_source"
            ] = missing_num_ids

            report[
                "unresolved_relationship_ids"
            ] = unresolved_relationships

            report[
                "relationship_details"
            ] = relationship_details

            if any(
                report["style_refs"].values()
            ):
                document_counts[
                    "fragments_with_styles"
                ] += 1

                global_counts[
                    "fragments_with_styles"
                ] += 1

            if report["num_ids"]:
                document_counts[
                    "fragments_with_numbering"
                ] += 1

                global_counts[
                    "fragments_with_numbering"
                ] += 1

            if report["relationship_ids"]:
                document_counts[
                    "fragments_with_relationships"
                ] += 1

                global_counts[
                    "fragments_with_relationships"
                ] += 1

            if report[
                "unsupported_structural_tags"
            ]:
                document_counts[
                    "fragments_with_unsupported_structural_tags"
                ] += 1

                global_counts[
                    "fragments_with_unsupported_structural_tags"
                ] += 1

            fragment_blockers = []

            if missing_styles:
                fragment_blockers.append(
                    "MISSING_STYLE_DEFINITION"
                )

            if missing_num_ids:
                fragment_blockers.append(
                    "MISSING_NUMBERING_DEFINITION"
                )

            if unresolved_relationships:
                fragment_blockers.append(
                    "UNRESOLVED_RELATIONSHIP"
                )

            if report[
                "unsupported_structural_tags"
            ]:
                fragment_blockers.append(
                    "UNSUPPORTED_STRUCTURAL_DEPENDENCY"
                )

            report[
                "blockers"
            ] = fragment_blockers

            if fragment_blockers:
                blockers.append(
                    {
                        "document": document_name,
                        "bookmark": (
                            report.get(
                                "bookmark"
                            )
                        ),
                        "codes": (
                            fragment_blockers
                        ),
                    }
                )

            fragment_reports.append(
                report
            )

            document_fragment_reports.append(
                report
            )

        unique_styles = sorted(
            {
                style_id
                for report
                in document_fragment_reports
                for refs
                in report[
                    "style_refs"
                ].values()
                for style_id in refs
            }
        )

        unique_num_ids = sorted(
            {
                num_id
                for report
                in document_fragment_reports
                for num_id
                in report["num_ids"]
            }
        )

        unique_rel_ids = sorted(
            {
                rel_id
                for report
                in document_fragment_reports
                for rel_id
                in report[
                    "relationship_ids"
                ]
            }
        )

        document_reports.append(
            {
                "document": document_name,
                "fragment_count": len(
                    records
                ),
                "style_ids": unique_styles,
                "num_ids": unique_num_ids,
                "relationship_ids": (
                    unique_rel_ids
                ),
                "counts": dict(
                    document_counts
                ),
            }
        )

    summary = {
        "document_count": len(
            document_reports
        ),
        "fragment_count": len(
            fragment_reports
        ),
        "blocker_count": len(blockers),
        "fragments_with_styles": (
            global_counts[
                "fragments_with_styles"
            ]
        ),
        "fragments_with_numbering": (
            global_counts[
                "fragments_with_numbering"
            ]
        ),
        "fragments_with_relationships": (
            global_counts[
                "fragments_with_relationships"
            ]
        ),
        "fragments_with_unsupported_structural_tags": (
            global_counts[
                "fragments_with_unsupported_structural_tags"
            ]
        ),
    }

    report = {
        "schema_version": (
            "c5e-certificate-detail-"
            "fragment-dependencies/v1"
        ),
        "status": (
            "FRAGMENT_DEPENDENCIES_PROFILED"
            if not blockers
            else "FRAGMENT_DEPENDENCIES_BLOCKED"
        ),
        "summary": summary,
        "documents": document_reports,
        "blockers": blockers,
        "invariants": {
            "gdp_in_scope": False,
            "source_documents_modified": False,
            "destination_templates_modified": False,
            "production_renderer_modified": False,
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
        f"{summary['document_count']}"
    )
    print(
        f"FRAGMENTS="
        f"{summary['fragment_count']}"
    )
    print(
        "WITH_STYLES="
        f"{summary['fragments_with_styles']}"
    )
    print(
        "WITH_NUMBERING="
        f"{summary['fragments_with_numbering']}"
    )
    print(
        "WITH_RELATIONSHIPS="
        f"{summary['fragments_with_relationships']}"
    )
    print(
        "WITH_UNSUPPORTED_STRUCTURAL_TAGS="
        f"{summary['fragments_with_unsupported_structural_tags']}"
    )
    print(
        f"BLOCKERS="
        f"{summary['blocker_count']}"
    )
    print(f"OUTPUT={OUTPUT}")

    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())