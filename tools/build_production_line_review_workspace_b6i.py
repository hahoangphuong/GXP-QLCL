"""Build B6I read-only ProductionLine review artifacts from verified inputs."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.production_line_population import CANONICAL_SNAPSHOT_SHA256, canonical_artifact_bytes, canonical_json_bytes
from backend.app.domain.production_line_review_workspace import (
    build_certificate_site_mismatch_report,
    build_cross_site_text_report,
    build_review_summary,
    build_review_workspace,
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("B6I JSON input must be an object")
    return value


def _semantic_sha(value: dict[str, Any]) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only B6I physical-identity review workspace.")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "artifacts" / "phase3c" / "legacy_snapshot_v2.json")
    parser.add_argument("--canonical-state", type=Path, required=True, help="Verified B6H read-only canonical-state JSON.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "phase3c")
    parser.add_argument("--node", help="Explicit Node executable for the artifact-tool workbook builder.")
    parser.add_argument("--artifact-tool-url", help="Explicit file URL for the approved bundled @oai/artifact-tool runtime.")
    parser.add_argument("--skip-xlsx", action="store_true", help="Write JSON/Markdown review artifacts only.")
    args = parser.parse_args(argv)
    snapshot_raw = args.snapshot.read_bytes()
    snapshot_sha = sha256(snapshot_raw).hexdigest()
    if snapshot_sha != CANONICAL_SNAPSHOT_SHA256:
        raise ValueError("B6I Snapshot V2 SHA256 provenance guard failed")
    canonical_state = _load_json(args.canonical_state)
    canonical_state_sha = _semantic_sha(canonical_state)
    workspace = build_review_workspace(
        json.loads(snapshot_raw),
        snapshot_sha256=snapshot_sha,
        canonical_state=canonical_state,
        canonical_state_sha256=canonical_state_sha,
    )
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    mismatch_report = build_certificate_site_mismatch_report(workspace, canonical_state)
    cross_site_report = build_cross_site_text_report(workspace["roster"])
    artifacts = {
        "production_line_physical_identity_roster_template_v2.json": workspace["roster"],
        "production_line_physical_identity_evidence_v1.json": {
            "schema_version": workspace["roster"]["schema_version"],
            "artifact_kind": "production_line_physical_identity_review_evidence",
            "input": {key: workspace["roster"][key] for key in ("legacy_snapshot_sha256", "canonical_state_sha256", "planner_version", "candidate_set_sha256")},
            "records": workspace["evidence"],
        },
        "production_line_certificate_site_mismatch_review_v1.json": mismatch_report,
        "production_line_cross_site_text_review_v1.json": cross_site_report,
    }
    for filename, payload in artifacts.items():
        (output_dir / filename).write_bytes(canonical_artifact_bytes(payload))
    (output_dir / "production_line_physical_identity_review_summary_v2.md").write_text(
        build_review_summary(
            workspace["roster"],
            certificate_mismatch_report=mismatch_report,
            cross_site_report=cross_site_report,
        ), encoding="utf-8", newline="\n"
    )
    roster_path = output_dir / "production_line_physical_identity_roster_template_v2.json"
    if not args.skip_xlsx:
        node = args.node or "node"
        environment = dict(os.environ)
        if args.artifact_tool_url:
            environment["B6I_ARTIFACT_TOOL_URL"] = args.artifact_tool_url
        subprocess.run([
            node,
            str(ROOT / "tools" / "build_production_line_review_workbook_b6i.mjs"),
            "--roster", str(roster_path),
            "--evidence", str(output_dir / "production_line_physical_identity_evidence_v1.json"),
            "--output", str(output_dir / "production_line_physical_identity_review_v1.xlsx"),
        ], check=True, env=environment)
    print(f"REVIEW_ROSTER_SHA256={sha256(roster_path.read_bytes()).hexdigest()}")
    print(f"CANDIDATE_SET_SHA256={workspace['roster']['candidate_set_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
