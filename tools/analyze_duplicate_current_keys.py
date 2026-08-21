from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any
import unicodedata

from pyxlsb import open_workbook


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
WORKBOOK_PATH = next((ROOT / "legacy").glob("*.xlsb"))
OUTPUT_DIR = ROOT / "artifacts" / "legacy_audit"
JSON_OUT = OUTPUT_DIR / "duplicate_current_analysis.json"
MD_OUT = OUTPUT_DIR / "duplicate_current_analysis.md"


def normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    no_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    no_special_d = no_marks.replace("Đ", "D").replace("đ", "d")
    compact = re.sub(r"[^A-Za-z0-9]+", "_", no_special_d)
    return compact.strip("_").lower()


def load_snapshot() -> dict[str, list[dict[str, Any]]]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def alias_map(columns: list[str]) -> dict[str, str]:
    return {normalize_label(column): column for column in columns}


def field(row: dict[str, Any], aliases: dict[str, str], alias: str) -> str:
    actual = aliases.get(alias)
    if actual is None:
        return ""
    return normalize_scalar(row.get(actual))


def field_any(row: dict[str, Any], aliases: dict[str, str], alias_options: list[str]) -> str:
    for alias in alias_options:
        actual = aliases.get(alias)
        if actual is not None:
            return normalize_scalar(row.get(actual))
    return ""


def summarize_cc_duplicates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    aliases = alias_map(list(rows[0].keys()))
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        status = field(row, aliases, "moi_nhat")
        lookup_key = field(row, aliases, "id_moi_nhat")
        if status == "o" and lookup_key:
            groups[lookup_key].append(
                {
                    "legacy_row_id": field(row, aliases, "id"),
                    "certificate_type": field(row, aliases, "loai_cc"),
                    "inspection_id": field(row, aliases, "id_dot_ktra"),
                    "site_id": field(row, aliases, "id_co_so"),
                    "ma_dc": field(row, aliases, "ma_dc"),
                    "certificate_no": field_any(row, aliases, ["ma_so_cc", "so_cc"]),
                    "issue_date": field_any(row, aliases, ["ngay_cap_cc", "ngay_cap"]),
                    "expiry_date": field_any(row, aliases, ["het_han_cc", "ngay_hhl"]),
                }
            )

    duplicate_groups = []
    class_counter: Counter[str] = Counter()
    for key, key_rows in sorted(groups.items()):
        if len(key_rows) <= 1:
            continue
        all_blank_ma_dc = all(not row["ma_dc"] for row in key_rows)
        all_blank_inspection = all(not row["inspection_id"] for row in key_rows)
        unique_site_ids = sorted({row["site_id"] for row in key_rows if row["site_id"]})
        unique_certificate_nos = sorted({row["certificate_no"] for row in key_rows if row["certificate_no"]})

        if all_blank_ma_dc and all_blank_inspection:
            classification = "blank_ma_dc_non_case_backed_multi_current"
        elif all_blank_ma_dc:
            classification = "blank_ma_dc_multi_current"
        else:
            classification = "mixed_current_key_collision"

        class_counter[classification] += 1
        duplicate_groups.append(
            {
                "lookup_key": key,
                "row_count": len(key_rows),
                "classification": classification,
                "all_blank_ma_dc": all_blank_ma_dc,
                "all_blank_inspection_id": all_blank_inspection,
                "unique_site_ids": unique_site_ids,
                "unique_certificate_nos": unique_certificate_nos,
                "rows": key_rows,
            }
        )

    return {
        "duplicate_group_count": len(duplicate_groups),
        "classification_counts": dict(sorted(class_counter.items())),
        "groups": duplicate_groups,
    }


def read_ktra_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open_workbook(str(WORKBOOK_PATH)) as workbook:
        with workbook.get_sheet("db.ktra") as sheet:
            headers: dict[int, str] = {}
            for row in sheet.rows():
                if row[0].r == 3:
                    for idx, cell in enumerate(row):
                        headers[idx] = normalize_scalar(cell.v)
                    continue
                if row[0].r < 4:
                    continue

                record: dict[str, str] = {
                    "logical_index": str(row[0].r - 3),
                    "excel_row_number": str(row[0].r + 1),
                    "__legacy_row_id": normalize_scalar(row[0].v if len(row) > 0 else None),
                    "__inspection_type": normalize_scalar(row[1].v if len(row) > 1 else None),
                    "__site_id": normalize_scalar(row[2].v if len(row) > 2 else None),
                    "__ma_dc": normalize_scalar(row[3].v if len(row) > 3 else None),
                    "__bb": normalize_scalar(row[14].v if len(row) > 14 else None),
                    "__progress": normalize_scalar(row[31].v if len(row) > 31 else None),
                    "__linked_certificate_id": normalize_scalar(row[32].v if len(row) > 32 else None),
                    "__lookup_status": normalize_scalar(row[34].v if len(row) > 34 else None),
                    "__lookup_key": normalize_scalar(row[35].v if len(row) > 35 else None),
                }
                for idx, header in headers.items():
                    if not header:
                        continue
                    record[header] = normalize_scalar(row[idx].v if idx < len(row) else None)
                rows.append(record)
    return rows


def is_pending_progress(value: str) -> bool:
    normalized = normalize_label(value)
    if not normalized:
        return False
    return normalized.startswith("cho_")


def summarize_ktra_duplicates(rows: list[dict[str, str]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)

    for row in rows:
        status = row["__lookup_status"]
        lookup_key = row["__lookup_key"]
        if status == "o" and lookup_key:
            groups[lookup_key].append(
                {
                    "logical_index": row["logical_index"],
                    "excel_row_number": row["excel_row_number"],
                    "legacy_row_id": row["__legacy_row_id"],
                    "inspection_type": row["__inspection_type"],
                    "site_id": row["__site_id"],
                    "ma_dc": row["__ma_dc"],
                    "progress": row["__progress"],
                    "bb": row["__bb"],
                    "linked_certificate_id": row["__linked_certificate_id"],
                }
            )

    duplicate_groups = []
    class_counter: Counter[str] = Counter()
    for key, key_rows in sorted(groups.items()):
        if len(key_rows) <= 1:
            continue

        completion_flags = [bool(row["bb"] or row["linked_certificate_id"]) for row in key_rows]
        pending_flags = [is_pending_progress(row["progress"]) for row in key_rows]

        if any(completion_flags) and any(pending_flags):
            classification = "completed_plus_pending_both_current"
        elif all(completion_flags):
            classification = "multiple_completed_both_current"
        else:
            classification = "mixed_current_state"

        class_counter[classification] += 1
        duplicate_groups.append(
            {
                "lookup_key": key,
                "row_count": len(key_rows),
                "classification": classification,
                "rows": key_rows,
            }
        )

    return {
        "duplicate_group_count": len(duplicate_groups),
        "classification_counts": dict(sorted(class_counter.items())),
        "groups": duplicate_groups,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Duplicate Current Analysis",
        "",
        "Generated by `tools/analyze_duplicate_current_keys.py`.",
        "",
        "## Summary",
        "",
        f"- `db.cc` duplicate current groups: `{report['db_cc']['duplicate_group_count']}`",
        f"- `db.ktra` duplicate current groups: `{report['db_ktra']['duplicate_group_count']}`",
        "",
        "## Classification counts",
        "",
        "### `db.cc`",
    ]

    if report["db_cc"]["classification_counts"]:
        for key, count in report["db_cc"]["classification_counts"].items():
            lines.append(f"- `{key}`: `{count}`")
    else:
        lines.append("- none")

    lines.extend(["", "### `db.ktra`"])
    if report["db_ktra"]["classification_counts"]:
        for key, count in report["db_ktra"]["classification_counts"].items():
            lines.append(f"- `{key}`: `{count}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Group details", ""])

    lines.append("### `db.cc`")
    if not report["db_cc"]["groups"]:
        lines.append("- none")
    else:
        for group in report["db_cc"]["groups"]:
            lines.append(
                f"- `{group['lookup_key']}` -> `{group['classification']}` with `{group['row_count']}` rows"
            )
            row_ids = ", ".join(row["legacy_row_id"] or "blank" for row in group["rows"])
            cert_nos = ", ".join(row["certificate_no"] or "blank" for row in group["rows"])
            lines.append(f"- row ids: `{row_ids}`")
            lines.append(f"- certificate nos: `{cert_nos}`")

    lines.extend(["", "### `db.ktra`"])
    if not report["db_ktra"]["groups"]:
        lines.append("- none")
    else:
        for group in report["db_ktra"]["groups"]:
            lines.append(
                f"- `{group['lookup_key']}` -> `{group['classification']}` with `{group['row_count']}` rows"
            )
            row_ids = ", ".join(row["legacy_row_id"] or "blank" for row in group["rows"])
            progress = ", ".join(row["progress"] or "blank" for row in group["rows"])
            lines.append(f"- row ids: `{row_ids}`")
            lines.append(f"- progress: `{progress}`")

    return "\n".join(lines) + "\n"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    snapshot = load_snapshot()
    cc_report = summarize_cc_duplicates(snapshot["db.cc"])
    ktra_report = summarize_ktra_duplicates(read_ktra_rows())

    report = {
        "generated_from": {
            "snapshot": str(SNAPSHOT_PATH.relative_to(ROOT)),
            "workbook": str(WORKBOOK_PATH.relative_to(ROOT)),
        },
        "db_cc": cc_report,
        "db_ktra": ktra_report,
    }

    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUT.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
