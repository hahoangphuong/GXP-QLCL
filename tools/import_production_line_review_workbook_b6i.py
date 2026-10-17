"""Convert a B6I XLSX review surface into validated canonical review JSON only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.production_line_population import canonical_artifact_bytes
from backend.app.domain.production_line_review_workspace import reviewed_roster_from_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a B6I review workbook and emit canonical review roster JSON.")
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node", default="node")
    parser.add_argument("--artifact-tool-url", help="Explicit file URL for the approved bundled @oai/artifact-tool runtime.")
    parser.add_argument("--existing-production-line-id", action="append", default=[])
    args = parser.parse_args(argv)
    # Human-reviewed artifacts and source workbooks are immutable evidence.
    # Refuse aliasing and existing outputs before invoking the XLSX extractor.
    if args.output.resolve() in {args.workbook.resolve(), args.template.resolve()}:
        parser.error("B6I reviewed roster output must differ from workbook and template inputs")
    if args.output.exists() or args.output.is_symlink():
        parser.error("B6I reviewed roster output already exists; select a fresh path")
    environment = dict(os.environ)
    if args.artifact_tool_url:
        environment["B6I_ARTIFACT_TOOL_URL"] = args.artifact_tool_url
    # Extraction must never reuse/delete a predictable path next to the
    # approved output: that path may already contain independent evidence.
    with TemporaryDirectory(prefix="gxp-b6i-review-") as temp_dir:
        extracted = Path(temp_dir) / "extracted.json"
        subprocess.run([
            args.node,
            str(ROOT / "tools" / "extract_production_line_review_workbook_b6i.mjs"),
            "--input", str(args.workbook.resolve()), "--output", str(extracted),
        ], check=True, env=environment)
        template = json.loads(args.template.read_bytes())
        review = json.loads(extracted.read_bytes())
        roster = reviewed_roster_from_rows(
            template,
            workbook_metadata=review["metadata"],
            review_rows=review["rows"],
            existing_line_ids=set(args.existing_production_line_id),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("xb") as handle:
            handle.write(canonical_artifact_bytes(roster))
    except FileExistsError:
        parser.error("B6I reviewed roster output already exists; select a fresh path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
