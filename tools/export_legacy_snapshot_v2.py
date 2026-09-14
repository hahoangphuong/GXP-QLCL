from __future__ import annotations
import argparse
from hashlib import sha256
from pathlib import Path
from backend.app.domain.legacy_snapshot_v2 import build_snapshot, snapshot_bytes

ROOT = Path(__file__).resolve().parents[1]
V1_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"


def validate_output_path(output: Path) -> Path:
    resolved = output.resolve()
    if resolved == V1_PATH.resolve():
        raise ValueError("V2 exporter refuses to overwrite the V1 snapshot")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Export full, read-only legacy workbook snapshot V2.")
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "phase3c" / "legacy_snapshot_v2.json")
    args = parser.parse_args()
    output = validate_output_path(args.output)
    content = snapshot_bytes(build_snapshot(args.workbook.resolve()))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    print(f"SHA256={sha256(content).hexdigest()}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
