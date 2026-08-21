from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.schema import write_schema_sql


def main() -> int:
    out = Path("artifacts") / "phase1" / "schema.sql"
    path = write_schema_sql(out)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
