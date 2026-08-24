from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.env_utils import parse_env_file, write_systemd_environment_file


def export_null(path: Path) -> int:
    values = parse_env_file(path)
    for key, value in values.items():
        if not key:
            raise ValueError("Runtime env keys must not be blank.")
        sys.stdout.buffer.write(f"{key}={value}".encode("utf-8"))
        sys.stdout.buffer.write(b"\0")
    return 0


def write_systemd(source_path: Path, output_path: Path) -> int:
    values = parse_env_file(source_path)
    write_systemd_environment_file(output_path, values)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "export-null":
        return export_null(Path(args[1]))
    if len(args) == 3 and args[0] == "write-systemd":
        return write_systemd(Path(args[1]), Path(args[2]))
    print(
        "Usage: python tools/runtime_env.py {export-null /path/to/runtime.env | write-systemd /path/to/runtime.env /path/to/runtime.systemd.env}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
