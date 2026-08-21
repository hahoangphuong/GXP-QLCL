from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from pyxlsb import open_workbook


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
WORKBOOK_PATH = next((ROOT / "legacy").glob("*.xlsb"))
OUTPUT_DIR = ROOT / "artifacts" / "legacy_audit"
JSON_OUT = OUTPUT_DIR / "current_lookup_reconciliation.json"
MD_OUT = OUTPUT_DIR / "current_lookup_reconciliation.md"


def load_snapshot() -> dict[str, list[dict[str, str]]]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_ktra_lookup_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open_workbook(str(WORKBOOK_PATH)) as wb:
        with wb.get_sheet("db.ktra") as sh:
            for row in sh.rows():
                # pyxlsb row indexes are 0-based here; header is row 3, data starts at row 4.
                if row[0].r < 4:
                    continue
                logical_index = row[0].r - 3
                values = [row[i].v if i < len(row) else None for i in [0, 1, 2, 3, 34, 35]]
                rows.append(
                    {
                        "logical_index": str(logical_index),
                        "ID": normalize(values[0]),
                        "LOẠI KT": normalize(values[1]),
                        "ID CƠ SỞ": normalize(values[2]),
                        "MÃ DC": normalize(values[3]),
                        "MỚI NHẤT": normalize(values[4]),
                        "ID MỚI NHẤT": normalize(values[5]),
                    }
                )
    return rows


def read_lookup_grid(sheet_name: str, key_col: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open_workbook(str(WORKBOOK_PATH)) as wb:
        with wb.get_sheet(sheet_name) as sh:
            for row in sh.rows():
                if row[0].r < 8:
                    continue
                key = normalize(row[key_col].v if key_col < len(row) else None)
                idx_ktra = normalize(row[key_col + 1].v if key_col + 1 < len(row) else None)
                idx_cc = normalize(row[key_col + 2].v if key_col + 2 < len(row) else None)
                if not key and not idx_ktra and not idx_cc:
                    continue
                rows.append(
                    {
                        "sheet": sheet_name,
                        "key": key,
                        "ktra_index": idx_ktra,
                        "cc_index": idx_cc,
                    }
                )
    return rows


def summarize_mirror_table(
    rows: list[dict[str, str]],
    key_builder,
    entity_label: str,
) -> dict[str, Any]:
    status_key = "MỚI NHẤT"
    lookup_key = "ID MỚI NHẤT"
    counts = Counter((row.get(status_key, ""), bool(row.get(lookup_key, ""))) for row in rows)
    current_rows = [row for row in rows if row.get(status_key) == "o"]
    noncurrent_rows = [row for row in rows if row.get(status_key) != "o"]

    current_key_mismatches = []
    for row in current_rows:
        expected = key_builder(row)
        observed = row.get(lookup_key, "")
        if expected != observed:
            current_key_mismatches.append(
                {
                    "id": row.get("ID", ""),
                    "expected_key": expected,
                    "observed_key": observed,
                }
            )

    stray_lookup_values = []
    for row in noncurrent_rows:
        observed = row.get(lookup_key, "")
        if observed:
            stray_lookup_values.append(
                {
                    "id": row.get("ID", ""),
                    "status": row.get(status_key, ""),
                    "observed_key": observed,
                }
            )

    current_key_counter = Counter(row.get(lookup_key, "") for row in current_rows if row.get(lookup_key, ""))
    duplicate_current_keys = [
        {"key": key, "count": count}
        for key, count in sorted(current_key_counter.items())
        if count > 1
    ]

    return {
        "entity": entity_label,
        "row_count": len(rows),
        "status_counts": {
            f"status={status!r},lookup_present={has_lookup}": count
            for (status, has_lookup), count in sorted(counts.items())
        },
        "current_row_count": len(current_rows),
        "current_key_mismatches": current_key_mismatches,
        "stray_lookup_values_on_noncurrent_rows": stray_lookup_values,
        "duplicate_current_keys": duplicate_current_keys,
    }


def compare_grid_to_base(
    grid_rows: list[dict[str, str]],
    ktra_rows: list[dict[str, str]],
    cc_rows: list[dict[str, str]],
) -> dict[str, Any]:
    ktra_by_index = {row["logical_index"]: row for row in ktra_rows}
    cc_by_index = {str(i): row for i, row in enumerate(cc_rows, start=1)}

    grid_findings = []
    missing_ktra_indexes = []
    missing_cc_indexes = []
    mismatched_ktra_keys = []
    mismatched_cc_keys = []

    for row in grid_rows:
        key = row["key"]
        normalized_key = f"{row['sheet']}-{key}" if key else key
        ktra_idx = row["ktra_index"]
        cc_idx = row["cc_index"]
        finding = {"sheet": row["sheet"], "key": key, "normalized_key": normalized_key}

        if ktra_idx and ktra_idx != "\\":
            ktra_row = ktra_by_index.get(ktra_idx)
            if ktra_row is None:
                missing_ktra_indexes.append({"sheet": row["sheet"], "key": key, "ktra_index": ktra_idx})
            else:
                if ktra_row.get("ID MỚI NHẤT", "") != normalized_key:
                    mismatched_ktra_keys.append(
                        {
                            "sheet": row["sheet"],
                            "key": key,
                            "normalized_key": normalized_key,
                            "ktra_index": ktra_idx,
                            "ktra_key": ktra_row.get("ID MỚI NHẤT", ""),
                            "ktra_id": ktra_row.get("ID", ""),
                        }
                    )
                finding["ktra_id"] = ktra_row.get("ID", "")

        if cc_idx and cc_idx != "\\":
            cc_row = cc_by_index.get(cc_idx)
            if cc_row is None:
                missing_cc_indexes.append({"sheet": row["sheet"], "key": key, "cc_index": cc_idx})
            else:
                if cc_row.get("ID MỚI NHẤT", "") != normalized_key:
                    mismatched_cc_keys.append(
                        {
                            "sheet": row["sheet"],
                            "key": key,
                            "normalized_key": normalized_key,
                            "cc_index": cc_idx,
                            "cc_key": cc_row.get("ID MỚI NHẤT", ""),
                            "cc_id": cc_row.get("ID", ""),
                        }
                    )
                finding["cc_id"] = cc_row.get("ID", "")

        grid_findings.append(finding)

    return {
        "grid_row_count": len(grid_rows),
        "missing_ktra_indexes": missing_ktra_indexes,
        "missing_cc_indexes": missing_cc_indexes,
        "mismatched_ktra_keys": mismatched_ktra_keys,
        "mismatched_cc_keys": mismatched_cc_keys,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Current Lookup Reconciliation",
        "",
        "Generated by `tools/audit_current_lookup_consistency.py`.",
        "",
        "## Summary",
        "",
        f"- `db.cc`: `{report['cc']['current_row_count']}` current rows, `{len(report['cc']['duplicate_current_keys'])}` duplicate current keys.",
        f"- `db.dkkd`: `{report['ddkd']['current_row_count']}` current rows, `{len(report['ddkd']['duplicate_current_keys'])}` duplicate current keys.",
        f"- `db.ktra`: `{report['ktra']['current_row_count']}` current rows, `{len(report['ktra']['duplicate_current_keys'])}` duplicate current keys.",
        f"- Grid rows checked: `{report['grid']['grid_row_count']}`.",
        "",
        "## Findings",
        "",
        f"- `db.cc` current-key mismatches: `{len(report['cc']['current_key_mismatches'])}`",
        f"- `db.cc` stray lookup values on non-current rows: `{len(report['cc']['stray_lookup_values_on_noncurrent_rows'])}`",
        f"- `db.dkkd` current-key mismatches: `{len(report['ddkd']['current_key_mismatches'])}`",
        f"- `db.dkkd` stray lookup values on non-current rows: `{len(report['ddkd']['stray_lookup_values_on_noncurrent_rows'])}`",
        f"- `db.ktra` current-key mismatches: `{len(report['ktra']['current_key_mismatches'])}`",
        f"- `db.ktra` stray lookup values on non-current rows: `{len(report['ktra']['stray_lookup_values_on_noncurrent_rows'])}`",
        f"- Grid -> ktra missing indexes: `{len(report['grid']['missing_ktra_indexes'])}`",
        f"- Grid -> cc missing indexes: `{len(report['grid']['missing_cc_indexes'])}`",
        f"- Grid -> ktra key mismatches: `{len(report['grid']['mismatched_ktra_keys'])}`",
        f"- Grid -> cc key mismatches: `{len(report['grid']['mismatched_cc_keys'])}`",
        "",
        "## Duplicate current keys",
        "",
    ]

    for section_name in ("cc", "ddkd", "ktra"):
        duplicates = report[section_name]["duplicate_current_keys"]
        lines.append(f"### `{section_name}`")
        if not duplicates:
            lines.append("- none")
        else:
            for item in duplicates[:20]:
                lines.append(f"- `{item['key']}` -> `{item['count']}` rows")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = load_snapshot()
    cc_rows = snapshot["db.cc"]
    ddkd_rows = snapshot["db.dkkd"]
    ktra_rows = read_ktra_lookup_rows()

    cc_report = summarize_mirror_table(
        cc_rows,
        lambda row: f"{row.get('LOẠI CC', '')}-{row.get('ID CƠ SỞ', '')}{row.get('MÃ DC', '')}",
        "db.cc",
    )
    ddkd_report = summarize_mirror_table(
        ddkd_rows,
        lambda row: row.get("ID CƠ SỞ", ""),
        "db.dkkd",
    )
    ktra_report = summarize_mirror_table(
        ktra_rows,
        lambda row: f"{row.get('LOẠI KT', '')}-{row.get('ID CƠ SỞ', '')}{row.get('MÃ DC', '')}",
        "db.ktra",
    )

    grid_rows = []
    grid_rows.extend(read_lookup_grid("GMP", 41))
    grid_rows.extend(read_lookup_grid("GLP", 40))
    grid_rows.extend(read_lookup_grid("GMPbb", 40))
    grid_report = compare_grid_to_base(grid_rows, ktra_rows, cc_rows)

    report = {
        "cc": cc_report,
        "ddkd": ddkd_report,
        "ktra": ktra_report,
        "grid": grid_report,
    }

    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
