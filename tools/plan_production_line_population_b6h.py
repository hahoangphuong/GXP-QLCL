"""Generate deterministic, source-only B6H ProductionLine planning artifacts."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.production_line_population import (
    CANONICAL_SNAPSHOT_SHA256,
    ProductionLinePlanningError,
    build_production_line_population_plan,
    build_physical_identity_roster_template,
    build_review_summary,
    canonical_artifact_bytes,
    canonical_json_bytes,
)


SNAPSHOT = ROOT / "artifacts" / "phase3c" / "legacy_snapshot_v2.json"
OUTPUT_DIR = ROOT / "artifacts" / "phase3c"
ARTIFACT_FILENAMES = {
    "discovery": "production_line_discovery_v2.json",
    "case_linkage": "production_line_case_linkage_plan_v2.json",
    "certificate_linkage": "production_line_certificate_linkage_plan_v2.json",
    "transformation_evidence": "production_line_transformation_evidence_v2.json",
}


def load_verified_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != CANONICAL_SNAPSHOT_SHA256:
        raise ProductionLinePlanningError("B6H Snapshot V2 SHA256 provenance guard failed")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ProductionLinePlanningError("B6H Snapshot V2 payload is invalid")
    return payload, digest


def load_json_with_sha256(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ProductionLinePlanningError("B6H JSON input is invalid")
    # Domain provenance is semantic JSON SHA256, independent of whitespace in a reviewed file.
    return payload, sha256(canonical_json_bytes(payload)).hexdigest()


def write_artifacts(output_dir: Path, artifacts: dict[str, dict[str, Any]]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for kind, artifact in artifacts.items():
        payload = canonical_artifact_bytes(artifact)
        (output_dir / ARTIFACT_FILENAMES[kind]).write_bytes(payload)
        digests[kind] = sha256(payload).hexdigest()
    return digests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only B6H ProductionLine discovery and linkage planning.")
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--canonical-state", type=Path, help="Read-only canonical state JSON; never a database URL.")
    parser.add_argument("--physical-identity-roster", type=Path, help="Reviewed roster JSON; no apply mode exists.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    snapshot, snapshot_sha256 = load_verified_snapshot(args.snapshot.resolve())
    canonical_state, canonical_state_sha256 = load_json_with_sha256(args.canonical_state)
    roster, roster_sha256 = load_json_with_sha256(args.physical_identity_roster)
    artifacts = build_production_line_population_plan(
        snapshot,
        snapshot_sha256=snapshot_sha256,
        canonical_state=canonical_state,
        canonical_state_sha256=canonical_state_sha256,
        roster=roster,
        roster_sha256=roster_sha256,
    )
    output_dir = args.output_dir.resolve()
    for kind, digest in sorted(write_artifacts(output_dir, artifacts).items()):
        print(f"{kind.upper()}_SHA256={digest}")
    template = build_physical_identity_roster_template(
        artifacts["discovery"], snapshot_sha256=snapshot_sha256, canonical_state_sha256=canonical_state_sha256
    )
    roster_path = output_dir / "production_line_physical_identity_roster_template_v1.json"
    roster_path.write_bytes(canonical_artifact_bytes(template))
    (output_dir / "production_line_physical_identity_review_summary_v1.md").write_text(
        build_review_summary(template), encoding="utf-8", newline="\n"
    )
    csv_rows = ["candidate_key,legacy_site_id,canonical_site_id,canonical_line_text,review_status,physical_identity_action,review_reason,production_line_id"]
    for item in template["items"]:
        csv_rows.append(",".join(f'"{str(value or "").replace(chr(34), chr(34) * 2)}"' for value in (
            item["candidate_key"], item["source_site_legacy_id"], item["canonical_site_id"], item["canonical_line_text"], item["review_status"], item["physical_identity_action"], "", "")))
    (output_dir / "production_line_physical_identity_roster_template_v1.csv").write_text("\n".join(csv_rows) + "\n", encoding="utf-8", newline="\n")
    print(f"ROSTER_TEMPLATE_SHA256={sha256(roster_path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
