from __future__ import annotations

from pathlib import Path
import csv
import json
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "artifacts" / "phase2" / "staging_readonly.db"
OUT_DIR = ROOT / "artifacts" / "phase3"

TABLES = [
    "company",
    "site",
    "case",
    "certificate",
    "business_eligibility_certificate",
    "change_request",
    "change_request_detail",
    "legacy_id_map",
]


def export_table(con: sqlite3.Connection, table: str) -> dict[str, int | str]:
    cur = con.cursor()
    cur.execute(f'SELECT * FROM "{table}"')
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]

    json_path = OUT_DIR / f"{table}.json"
    csv_path = OUT_DIR / f"{table}.csv"

    json_rows = [dict(zip(columns, row)) for row in rows]
    json_path.write_text(json.dumps(json_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(json_rows)

    return {"table": table, "rows": len(json_rows), "json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    try:
        manifest = [export_table(con, table) for table in TABLES]
    finally:
        con.close()

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote exports to {OUT_DIR}")
    print(f"Wrote manifest to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
