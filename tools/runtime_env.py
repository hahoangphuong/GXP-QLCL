from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.env_utils import parse_env_file


def export_null(path: Path) -> int:
    values = parse_env_file(path)
    for key, value in values.items():
        if not key:
            raise ValueError("Runtime env keys must not be blank.")
        sys.stdout.buffer.write(f"{key}={value}".encode("utf-8"))
        sys.stdout.buffer.write(b"\0")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "export-null":
        print("Usage: python tools/runtime_env.py export-null /path/to/runtime.env", file=sys.stderr)
        return 2
    return export_null(Path(args[1]))


if __name__ == "__main__":
    raise SystemExit(main())
