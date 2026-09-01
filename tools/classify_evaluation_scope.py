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

from backend.app.domain.evaluation_scope import (
    classify_scope_corpus,
    taxonomy_statistics,
    validate_taxonomy_integrity,
)


def _logical_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def build_report(snapshot_path: Path, taxonomy_path: Path) -> dict[str, Any]:
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot: dict[str, Any] = json.loads(snapshot_bytes.decode("utf-8"))
    sheets = snapshot.get("sheets", snapshot)
    if not isinstance(sheets, dict) or not isinstance(sheets.get("db.ktra"), list):
        raise ValueError("Legacy snapshot does not contain a db.ktra row list.")
    taxonomy_bytes = taxonomy_path.read_bytes()
    taxonomy: dict[str, Any] = json.loads(taxonomy_bytes.decode("utf-8"))
    integrity = validate_taxonomy_integrity(taxonomy)
    report = classify_scope_corpus(sheets["db.ktra"], taxonomy=taxonomy)
    report["source_snapshot"] = _logical_path(snapshot_path)
    report["source_snapshot_sha256"] = sha256(snapshot_bytes).hexdigest()
    report["taxonomy_artifact"] = _logical_path(taxonomy_path)
    report["taxonomy_schema_version"] = taxonomy["schema_version"]
    report["taxonomy_content_sha256"] = taxonomy["taxonomy_content_sha256"]
    report["source_workbook_sha256"] = taxonomy.get("source_workbook_sha256")
    report["taxonomy_integrity"] = integrity
    report["taxonomy_statistics"] = taxonomy_statistics(taxonomy, integrity["validation"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify legacy db.ktra evaluation scopes from JSON artifacts only.")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json")
    parser.add_argument("--taxonomy", type=Path, default=ROOT / "artifacts" / "legacy_snapshot" / "evaluation_scope_taxonomy.json")
    parser.add_argument("--output", "--out", dest="output", type=Path, default=ROOT / "artifacts" / "legacy_audit" / "evaluation_scope_payload_classification.json")
    args = parser.parse_args()
    report = build_report(args.snapshot, args.taxonomy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote evaluation-scope classification report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
