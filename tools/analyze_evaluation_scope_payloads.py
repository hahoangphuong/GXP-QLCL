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

from backend.app.domain.evaluation_scope import classify_scope_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify legacy db.ktra evaluation-scope payloads without inference.")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json")
    parser.add_argument("--taxonomy", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "legacy_audit" / "evaluation_scope_payload_classification.json")
    args = parser.parse_args()
    snapshot_bytes = args.snapshot.read_bytes()
    document: dict[str, Any] = json.loads(snapshot_bytes.decode("utf-8"))
    rows = document.get("sheets", document).get("db.ktra", [])
    taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8")) if args.taxonomy else None
    report = classify_scope_corpus(rows, taxonomy=taxonomy)
    report["source_snapshot"] = args.snapshot.relative_to(ROOT).as_posix()
    report["source_snapshot_sha256"] = sha256(snapshot_bytes).hexdigest()
    report["taxonomy_artifact"] = None if args.taxonomy is None else args.taxonomy.relative_to(ROOT).as_posix()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote evaluation-scope classification report to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
