from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.phase2_import import normalize_row

RECONCILIATION_PATH = ROOT / "artifacts" / "phase2" / "reconciliation.json"
SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
OUT_DIR = ROOT / "artifacts" / "phase3_review"
CSV_PATH = OUT_DIR / "anomaly_review_report.csv"
JSON_PATH = OUT_DIR / "anomaly_review_report.json"
MD_PATH = OUT_DIR / "anomaly_review_report.md"


CSV_COLUMNS = [
    "source_sheet",
    "source_row_key",
    "source_row_number",
    "legacy_row_id",
    "status",
    "reason",
    "required_field",
    "raw_fk_value",
    "display_label",
    "primary_name",
    "secondary_name",
    "site_ref",
    "company_ref",
    "case_ref",
    "certificate_ref",
    "submitted_at",
    "decision_or_result",
    "review_summary",
    "legacy_context_json",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _row_key(row: dict[str, str]) -> str | None:
    legacy_id = str(row.get("ID", "")).strip()
    if legacy_id:
        return legacy_id
    excel_row = str(row.get("__excel_row_number", "")).strip()
    if excel_row:
        return f"row:{excel_row}"
    return None


def build_snapshot_lookup(snapshot: dict[str, list[dict[str, str]]]) -> dict[tuple[str, str], dict[str, str]]:
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    for sheet, rows in snapshot.items():
        for raw_row in rows:
            row = normalize_row(raw_row)
            row_key = _row_key(row)
            if row_key:
                lookup[(sheet, row_key)] = row
    return lookup


def _shorten(text: str | None, limit: int = 140) -> str:
    value = str(text or "").strip().replace("\r", " ").replace("\n", " ")
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _context_for_sheet(sheet: str, row: dict[str, str]) -> dict[str, str]:
    if sheet == "db.cso":
        return {
            "display_label": "Cơ sở thiếu liên kết công ty",
            "primary_name": row.get("site_name", ""),
            "secondary_name": row.get("site_address", ""),
            "site_ref": row.get("ID", ""),
            "company_ref": row.get("company_legacy_id_ref", ""),
            "case_ref": "",
            "certificate_ref": "",
            "submitted_at": "",
            "decision_or_result": row.get("province_name", ""),
            "review_summary": _shorten(
                f"Cơ sở '{row.get('site_name', '')}' tại '{row.get('site_address', '')}' không có company FK hợp lệ."
            ),
        }
    if sheet == "db.ktra":
        return {
            "display_label": "Đợt kiểm tra thiếu liên kết cơ sở",
            "primary_name": row.get("dossier_code", "") or row.get("inspection_gxp_type", ""),
            "secondary_name": row.get("inspection_type", ""),
            "site_ref": row.get("site_legacy_id_ref", ""),
            "company_ref": "",
            "case_ref": row.get("ID", ""),
            "certificate_ref": row.get("linked_certificate_ids", ""),
            "submitted_at": row.get("submitted_at", ""),
            "decision_or_result": row.get("assessment_result", "") or row.get("decision_reference", ""),
            "review_summary": _shorten(
                f"Đợt kiểm tra '{row.get('inspection_gxp_type', '')}' hồ sơ '{row.get('dossier_code', '')}' thiếu site FK."
            ),
        }
    if sheet == "db.cc":
        return {
            "display_label": "Chứng chỉ thiếu liên kết",
            "primary_name": row.get("site_name", "") or row.get("certificate_type", ""),
            "secondary_name": row.get("certificate_type", ""),
            "site_ref": row.get("site_legacy_id_ref", ""),
            "company_ref": row.get("company_legacy_id_ref", ""),
            "case_ref": row.get("inspection_case_legacy_id_ref", ""),
            "certificate_ref": row.get("ID", ""),
            "submitted_at": row.get("Ngày cấp CC", ""),
            "decision_or_result": row.get("certificate_number", "") or row.get("scope_code", ""),
            "review_summary": _shorten(
                f"Chứng chỉ '{row.get('certificate_type', '')}' của cơ sở '{row.get('site_name', '')}' thiếu FK cần thiết."
            ),
        }
    if sheet == "db.dkkd":
        return {
            "display_label": "ĐĐKD thiếu liên kết",
            "primary_name": row.get("site_name", "") or row.get("professional_responsible_person_name", ""),
            "secondary_name": row.get("site_address", ""),
            "site_ref": row.get("site_legacy_id_ref", ""),
            "company_ref": row.get("company_legacy_id_ref", ""),
            "case_ref": "",
            "certificate_ref": row.get("linked_certificate_ids", ""),
            "submitted_at": row.get("issued_on", ""),
            "decision_or_result": row.get("professional_responsible_person_name", ""),
            "review_summary": _shorten(
                f"ĐĐKD của cơ sở '{row.get('site_name', '')}' thiếu site hoặc company FK hợp lệ."
            ),
        }
    if sheet == "db.Tdoi":
        return {
            "display_label": "Thay đổi thiếu liên kết cơ sở",
            "primary_name": row.get("change_description", ""),
            "secondary_name": row.get("change_scope_label", ""),
            "site_ref": row.get("site_legacy_id_ref", ""),
            "company_ref": "",
            "case_ref": "",
            "certificate_ref": "",
            "submitted_at": row.get("submitted_at", ""),
            "decision_or_result": row.get("approval_reference", "") or row.get("assessment_result", ""),
            "review_summary": _shorten(
                f"Yêu cầu thay đổi '{row.get('change_description', '')}' thiếu site FK hợp lệ."
            ),
        }
    if sheet == "db.Tdoi2":
        return {
            "display_label": "Chi tiết thay đổi thiếu liên kết yêu cầu gốc",
            "primary_name": row.get("classification_label", ""),
            "secondary_name": row.get("new_value", ""),
            "site_ref": "",
            "company_ref": "",
            "case_ref": "",
            "certificate_ref": "",
            "submitted_at": "",
            "decision_or_result": row.get("approval_status", ""),
            "review_summary": _shorten(
                f"Chi tiết thay đổi '{row.get('classification_label', '')}' thiếu change request FK hợp lệ."
            ),
        }
    return {
        "display_label": "Legacy anomaly",
        "primary_name": "",
        "secondary_name": "",
        "site_ref": "",
        "company_ref": "",
        "case_ref": "",
        "certificate_ref": "",
        "submitted_at": "",
        "decision_or_result": "",
        "review_summary": "",
    }


def build_review_rows(
    reconciliation: dict[str, Any],
    snapshot: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    lookup = build_snapshot_lookup(snapshot)
    review_rows: list[dict[str, Any]] = []

    for anomaly in reconciliation.get("anomaly_rows", []):
        row_key = anomaly.get("source_row_key")
        sheet = anomaly["source_sheet"]
        snapshot_row = normalize_row(lookup.get((sheet, row_key), {}))
        context = _context_for_sheet(sheet, snapshot_row)
        legacy_context = {
            key: value
            for key, value in snapshot_row.items()
            if key
            in {
                "ID",
                "__excel_row_number",
                "company_legacy_id_ref",
                "site_legacy_id_ref",
                "inspection_case_legacy_id_ref",
                "change_request_legacy_id_ref",
                "site_name",
                "site_address",
                "certificate_type",
                "dossier_code",
                "inspection_gxp_type",
                "change_description",
                "classification_label",
                "linked_certificate_ids",
                "professional_responsible_person_name",
            }
            and str(value or "").strip()
        }
        review_rows.append(
            {
                "source_sheet": sheet,
                "source_row_key": row_key,
                "source_row_number": anomaly.get("source_row_number"),
                "legacy_row_id": anomaly.get("legacy_row_id"),
                "status": anomaly.get("status"),
                "reason": anomaly.get("reason"),
                "required_field": anomaly.get("required_field"),
                "raw_fk_value": anomaly.get("raw_fk_value"),
                **context,
                "legacy_context_json": json.dumps(legacy_context, ensure_ascii=False, sort_keys=True),
            }
        )

    review_rows.sort(
        key=lambda row: (
            row["source_sheet"],
            row["reason"],
            row["source_row_number"] if row["source_row_number"] is not None else 10**9,
            str(row["source_row_key"]),
        )
    )
    return review_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_markdown(rows: list[dict[str, Any]]) -> str:
    by_sheet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_sheet[row["source_sheet"]].append(row)

    reason_counts = Counter(row["reason"] for row in rows)
    lines = [
        "# Phase 3 Review Report",
        "",
        "## Tổng quan",
        "",
        f"- Tổng anomaly mở: `{len(rows)}`",
        f"- Theo reason: `{dict(reason_counts)}`",
        "",
        "## Danh sách chi tiết",
        "",
    ]
    for sheet in sorted(by_sheet):
        sheet_rows = by_sheet[sheet]
        lines.extend(
            [
                f"### `{sheet}`",
                "",
                f"- Số dòng: `{len(sheet_rows)}`",
                "",
                "| Row Key | Legacy ID | Reason | Raw FK | Tên/Context | Tóm tắt |",
                "|---|---:|---|---|---|---|",
            ]
        )
        for row in sheet_rows:
            primary = _shorten(row["primary_name"] or row["secondary_name"], 60).replace("|", "/")
            summary = _shorten(row["review_summary"], 90).replace("|", "/")
            raw_fk = _shorten(row["raw_fk_value"], 30).replace("|", "/")
            lines.append(
                f"| `{row['source_row_key']}` | `{row['legacy_row_id'] or ''}` | `{row['reason']}` | `{raw_fk}` | {primary} | {summary} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    reconciliation = load_json(RECONCILIATION_PATH)
    snapshot = load_json(SNAPSHOT_PATH)
    review_rows = build_review_rows(reconciliation, snapshot)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(review_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(CSV_PATH, review_rows)
    MD_PATH.write_text(build_markdown(review_rows), encoding="utf-8")

    print(f"Wrote {JSON_PATH}")
    print(f"Wrote {CSV_PATH}")
    print(f"Wrote {MD_PATH}")
    print(f"Rows: {len(review_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
