"""Build a sealed B6K manifest from explicit immutable source artifacts."""
from __future__ import annotations
import argparse, json
from hashlib import sha256
from pathlib import Path
from backend.app.domain.cutover_source_manifest_b6k import build_manifest, manifest_bytes

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--workbook",type=Path,required=True);p.add_argument("--snapshot",type=Path,required=True);p.add_argument("--expected-workbook-sha256",required=True);p.add_argument("--expected-snapshot-sha256",required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--declared-frozen",action="store_true");a=p.parse_args()
    wb=a.workbook.read_bytes(); raw=a.snapshot.read_bytes()
    if sha256(wb).hexdigest()!=a.expected_workbook_sha256 or sha256(raw).hexdigest()!=a.expected_snapshot_sha256: raise SystemExit("source SHA256 provenance differs")
    value=build_manifest(workbook_bytes=wb,snapshot_bytes=raw,expected_workbook_sha256=a.expected_workbook_sha256,expected_snapshot_sha256=a.expected_snapshot_sha256,declared_frozen=a.declared_frozen)
    a.output.write_bytes(manifest_bytes(value)); print(f"MANIFEST_SHA256={sha256(manifest_bytes(value)).hexdigest()}"); return 0
if __name__ == "__main__": raise SystemExit(main())
