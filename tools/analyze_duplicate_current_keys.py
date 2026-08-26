from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
OUTPUT_DIR = ROOT / "artifacts" / "legacy_audit"
JSON_OUT = OUTPUT_DIR / "duplicate_current_analysis.json"
MD_OUT = OUTPUT_DIR / "duplicate_current_analysis.md"
SNAPSHOT_ONLY_ANALYSIS_STRATEGY = "snapshot_only"


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


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_sheet_mapping(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    validated: dict[str, list[dict[str, Any]]] = {}
    for sheet_name, rows in payload.items():
        if not isinstance(sheet_name, str):
            raise RuntimeError("Legacy snapshot sheet names must be strings.")
        if not isinstance(rows, list):
            continue
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise RuntimeError(
                    f"Legacy snapshot sheet {sheet_name!r} contains a non-object row."
                )
            normalized_rows.append(row)
        validated[sheet_name] = normalized_rows
    return validated


def _snapshot_sheets(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if "sheets" in payload:
        sheets = payload["sheets"]
        if not isinstance(sheets, dict):
            raise RuntimeError("Legacy snapshot wrapper field 'sheets' must be a JSON object.")
        return _validate_sheet_mapping(sheets)
    return _validate_sheet_mapping(payload)


def _snapshot_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _load_snapshot_document(snapshot_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], str]:
    if not snapshot_path.exists():
        raise RuntimeError(
            f"Required legacy snapshot artifact is missing: {_display_path(snapshot_path)}"
        )
    snapshot_bytes = snapshot_path.read_bytes()
    try:
        payload = json.loads(snapshot_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Legacy snapshot artifact is invalid JSON: {_display_path(snapshot_path)}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Legacy snapshot artifact must be a JSON object: {_display_path(snapshot_path)}"
        )
    return payload, _snapshot_sheets(payload), sha256(snapshot_bytes).hexdigest()


def _require_rows(
    sheets: dict[str, list[dict[str, Any]]], sheet_name: str
) -> list[dict[str, Any]]:
    rows = sheets.get(sheet_name)
    if rows is None:
        raise RuntimeError(f"Legacy snapshot is missing required sheet: {sheet_name}")
    if not rows:
        raise RuntimeError(f"Legacy snapshot sheet has no rows: {sheet_name}")
    return rows


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


def read_ktra_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not rows:
        return []
    aliases = alias_map(list(rows[0].keys()))
    normalized_rows: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        normalized_rows.append(
            {
                "logical_index": field_any(row, aliases, ["logical_index"])
                or field_any(row, aliases, ["excel_row_number"])
                or str(index),
                "excel_row_number": field_any(row, aliases, ["excel_row_number"]) or str(index),
                "__legacy_row_id": field(row, aliases, "id"),
                "__inspection_type": field(row, aliases, "loai_kt"),
                "__site_id": field(row, aliases, "id_co_so"),
                "__ma_dc": field(row, aliases, "ma_dc"),
                "__bb": field_any(row, aliases, ["b_ban", "bien_ban"]),
                "__progress": field(row, aliases, "tien_do_xu_ly"),
                "__linked_certificate_id": field_any(row, aliases, ["id_cc_gps", "id_cc"]),
                "__lookup_status": field(row, aliases, "moi_nhat"),
                "__lookup_key": field(row, aliases, "id_moi_nhat"),
            }
        )
    return normalized_rows


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


def build_report(*, snapshot_path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    snapshot_document, sheets, snapshot_sha256 = _load_snapshot_document(snapshot_path)
    metadata = _snapshot_metadata(snapshot_document)
    return {
        "generated_from": {
            "snapshot_path": _display_path(snapshot_path),
            "snapshot_sha256": snapshot_sha256,
            "snapshot_exported_at": metadata.get("exported_at"),
            "source_workbook_identity": metadata.get("source_workbook_identity"),
            "analysis_strategy": SNAPSHOT_ONLY_ANALYSIS_STRATEGY,
        },
        "db_cc": summarize_cc_duplicates(_require_rows(sheets, "db.cc")),
        "db_ktra": summarize_ktra_duplicates(read_ktra_rows(_require_rows(sheets, "db.ktra"))),
    }


def render_markdown(report: dict[str, Any]) -> str:
    provenance = report["generated_from"]
    lines = [
        "# Duplicate Current Analysis",
        "",
        "Generated by `tools/analyze_duplicate_current_keys.py`.",
        "",
        "## Provenance",
        "",
        f"- snapshot_path: `{provenance['snapshot_path']}`",
        f"- snapshot_sha256: `{provenance['snapshot_sha256']}`",
        f"- snapshot_exported_at: `{provenance['snapshot_exported_at']}`",
        f"- source_workbook_identity: `{provenance['source_workbook_identity']}`",
        f"- analysis_strategy: `{provenance['analysis_strategy']}`",
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
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report = build_report()
        JSON_OUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        MD_OUT.write_text(render_markdown(report), encoding="utf-8")
        print(f"Wrote {JSON_OUT}")
        print(f"Wrote {MD_OUT}")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
