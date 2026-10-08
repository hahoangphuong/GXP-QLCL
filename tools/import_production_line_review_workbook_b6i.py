"""Convert a B6I XLSX review surface into validated canonical review JSON only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
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
    extracted = args.output.with_suffix(".extracted.json")
    try:
        environment = dict(os.environ)
        if args.artifact_tool_url:
            environment["B6I_ARTIFACT_TOOL_URL"] = args.artifact_tool_url
        subprocess.run([
            args.node,
            str(ROOT / "tools" / "extract_production_line_review_workbook_b6i.mjs"),
            "--input", str(args.workbook.resolve()), "--output", str(extracted.resolve()),
        ], check=True, env=environment)
        template = json.loads(args.template.read_bytes())
        review = json.loads(extracted.read_bytes())
        roster = reviewed_roster_from_rows(
            template,
            workbook_metadata=review["metadata"],
            review_rows=review["rows"],
            existing_line_ids=set(args.existing_production_line_id),
        )
        args.output.write_bytes(canonical_artifact_bytes(roster))
    finally:
        extracted.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
