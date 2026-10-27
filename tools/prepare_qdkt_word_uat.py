"""Prepare isolated local Word UAT inputs; never render or mark UAT passed.

Run from repository root. Originals are checksum-verified and copied into a new
directory; no existing directory or file is overwritten. No StorageService,
database, network, Word COM, or production configuration is accessed.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
from xml.etree import ElementTree
from zipfile import ZipFile

from backend.app.document.inspection_qd_kt_dotx_binary_audit import inspect_supplied_qdkt_dotx_set
from backend.app.document.inspection_qd_kt_renderer_contract import (
    SYNTHETIC_INPUT, SYNTHETIC_INPUT_SHA256, UAT_CHECKS, decision_digest,
    load_renderer_decision,
)
from backend.app.document.inspection_qd_kt_template_asset_contract import load_inspection_qd_kt_template_assets


def prepare_package(*, template_directory: Path, output: Path) -> dict:
    """Validate all inputs before exclusively creating any output."""
    decision = load_renderer_decision()
    audits = inspect_supplied_qdkt_dotx_set(template_directory)
    assets = {a.gxp_type: a for a in load_inspection_qd_kt_template_assets()}
    # Pin the copied bytes too, rather than trusting an earlier path read.
    source_bytes = {}
    for audit in audits:
        data = (template_directory / assets[audit.gxp_type].filename).read_bytes()
        if sha256(data).hexdigest() != audit.actual_sha256:
            raise ValueError("QDKT_UAT_SOURCE_CHANGED")
        source_bytes[audit.gxp_type] = data
    output.mkdir(parents=False, exist_ok=False)
    manifest = {
        "schema_version": "qdkt-word-uat-package/v1",
        "decision_sha256": decision_digest(decision),
        "decision": decision.decision,
        "execution": "NOT_EXECUTED",
        "ready_to_render": False,
        "synthetic_input": SYNTHETIC_INPUT,
        "synthetic_input_sha256": SYNTHETIC_INPUT_SHA256,
        "required_acceptance_checks": sorted(UAT_CHECKS),
        "negative_cases": [
            {"id": "MISSING_CODE", "HsDK": None, "expected": "BLOCK_BEFORE_WORD"},
            {"id": "MISSING_DATE", "NgaynopHsDK": None, "expected": "BLOCK_BEFORE_WORD"},
            {"id": "WRONG_CASE_OR_APPLICATION", "expected": "BLOCK_BEFORE_WORD"},
            {"id": "STALE_TEMPLATE_OR_APPROVAL", "expected": "BLOCK_BEFORE_WORD"},
        ],
        "templates": [],
    }
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for audit in audits:
        asset = assets[audit.gxp_type]
        with (output / asset.filename).open("xb") as target:
            target.write(source_bytes[audit.gxp_type])
        locations = []
        with ZipFile(BytesIO(source_bytes[audit.gxp_type])) as archive:
            for part in audit.scanned_word_parts:
                root = ElementTree.fromstring(archive.read(part))
                for index, paragraph in enumerate(root.iter(f"{ns}p"), 1):
                    text = "".join(t.text or "" for t in paragraph.iter(f"{ns}t"))
                    if "hồ sơ" in text.casefold():
                        # No legal/business paragraph text exported to evidence.
                        in_table = any(paragraph in list(table.iter()) for table in root.iter(f"{ns}tbl"))
                        locations.append({"part": part, "paragraph_index": index, "inside_table": in_table})
        manifest["templates"].append({
            "gxp_type": audit.gxp_type,
            "source_filename": asset.filename,
            "source_sha256": audit.actual_sha256,
            "source_version": f"legacy-sha256:{audit.actual_sha256}",
            "copy_sha256": sha256((output / asset.filename).read_bytes()).hexdigest(),
            "candidate_approved": False,
            "candidate_version": None,
            "candidate_sha256": None,
            "source_dossier_prose_locations": locations,
            "source_target_bookmarks": "VERIFIED_ABSENT",
            "candidate_placement": "EVIDENCE_MISSING_OWNER_DECISION",
            "word_page": "EVIDENCE_MISSING_WORD_UAT",
            "uat_result": "NOT_EXECUTED",
        })
    with (output / "uat-package.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    # The procedure is versioned in Git; a package receives the same exact bytes.
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / "docs/QDKT_RENDERER_DECISION_WORD_UAT.md",
        output / "PROCEDURE.md",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare_package(template_directory=args.template_dir, output=args.output)
    print(json.dumps({"templates": len(manifest["templates"]), "execution": "NOT_EXECUTED", "ready_to_render": False}))


if __name__ == "__main__":
    main()
