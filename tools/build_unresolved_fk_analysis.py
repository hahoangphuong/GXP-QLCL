from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.phase2_import import (
    CONFIRMED_BLANKED_ROWS_PATH,
    load_confirmed_blanked_contract_rows,
)
INPUT_PATH = ROOT / "artifacts" / "phase3_review" / "anomaly_review_report.json"
SOURCE_SNAPSHOT_PATH = ROOT / "artifacts" / "phase3c" / "legacy_snapshot.json"
OUT_DIR = ROOT / "artifacts" / "legacy-production-analysis"
JSON_OUT = OUT_DIR / "unresolved_fk_analysis.json"
MD_OUT = OUT_DIR / "unresolved_fk_analysis.md"


def _match_method(source_row_key: str) -> str:
    if source_row_key.startswith("row:"):
        return "source_sheet+source_row_key:excel_row_fallback"
    if source_row_key.isdigit():
        return "source_sheet+source_row_key:numeric_legacy_id"
    return "source_sheet+source_row_key"


def _cascade_parent(reason: str, raw_fk_value: str, confirmed_keys: set[tuple[str, str]]) -> dict[str, str] | None:
    raw_fk = str(raw_fk_value or "").strip()
    parent_sheet_by_reason = {
        "missing_case_fk": "db.ktra",
        "missing_change_request_fk": "db.Tdoi",
    }
    parent_sheet = parent_sheet_by_reason.get(reason)
    if not parent_sheet or not raw_fk:
        return None
    if (parent_sheet, raw_fk) not in confirmed_keys:
        return None
    return {
        "classification": "cascade_from_confirmed_blanked_parent",
        "parent_source_sheet": parent_sheet,
        "parent_source_row_key": raw_fk,
    }


def build_unresolved_fk_analysis(
    anomaly_rows: list[dict[str, object]],
    confirmed_rows: list[dict[str, object]],
    *,
    snapshot_sha256: str | None = None,
    confirmed_contract_sha256: str | None = None,
    anomaly_report_sha256: str | None = None,
) -> dict[str, object]:
    confirmed_keys = {
        (str(row.get("source_sheet", "")).strip(), str(row.get("source_row_key", "")).strip())
        for row in confirmed_rows
        if str(row.get("source_sheet", "")).strip() and str(row.get("source_row_key", "")).strip()
    }
    blank_fk_rows = [row for row in anomaly_rows if not str(row.get("raw_fk_value") or "").strip()]
    family_summary: dict[tuple[str, str], dict[str, int | str]] = defaultdict(
        lambda: {
            "raw": 0,
            "confirmed_blanked": 0,
            "remaining_root": 0,
            "cascade": 0,
        }
    )
    row_analyses: list[dict[str, object]] = []
    confirmed_match_count = 0
    cascade_count = 0
    remaining_root_count = 0

    for row in anomaly_rows:
        source_sheet = str(row.get("source_sheet", "")).strip()
        source_row_key = str(row.get("source_row_key", "")).strip()
        legacy_row_id = str(row.get("legacy_row_id") or "").strip()
        reason = str(row.get("reason", "")).strip()
        raw_fk = str(row.get("raw_fk_value") or "").strip()
        key = (source_sheet, source_row_key)
        is_confirmed = key in confirmed_keys
        match_method = _match_method(source_row_key) if is_confirmed else None
        cascade = _cascade_parent(reason, raw_fk, confirmed_keys)

        analysis = {
            "source_sheet": source_sheet,
            "source_row_key": source_row_key,
            "legacy_row_id": legacy_row_id or None,
            "reason": reason,
            "raw_fk": raw_fk,
            "is_confirmed_blanked": is_confirmed,
            "confirmed_blank_match_method": match_method,
        }
        if cascade is not None:
            analysis.update(cascade)

        family_key = (source_sheet, reason)
        family_summary[family_key]["raw"] += 1
        if is_confirmed:
            confirmed_match_count += 1
            family_summary[family_key]["confirmed_blanked"] += 1
        if cascade is not None:
            cascade_count += 1
            family_summary[family_key]["cascade"] += 1
        if not is_confirmed:
            remaining_root_count += 1
            family_summary[family_key]["remaining_root"] += 1

        row_analyses.append(analysis)

    family_rows = []
    for (source_sheet, reason), counts in sorted(family_summary.items()):
        family_rows.append(
            {
                "source_sheet": source_sheet,
                "reason": reason,
                "raw": counts["raw"],
                "confirmed_blanked": counts["confirmed_blanked"],
                "remaining_root": counts["remaining_root"],
                "cascade": counts["cascade"],
            }
        )

    blank_confirmed = sum(1 for row in row_analyses if not row["raw_fk"] and row["is_confirmed_blanked"])
    return {
        "confirmed_blank_contract_path": CONFIRMED_BLANKED_ROWS_PATH.relative_to(ROOT).as_posix(),
        "confirmed_blank_contract_sha256": confirmed_contract_sha256,
        "snapshot_path": SOURCE_SNAPSHOT_PATH.relative_to(ROOT).as_posix(),
        "snapshot_sha256": snapshot_sha256,
        "anomaly_report_path": INPUT_PATH.relative_to(ROOT).as_posix(),
        "anomaly_report_sha256": anomaly_report_sha256,
        "raw_anomaly_count": len(anomaly_rows),
        "blank_fk_total": len(blank_fk_rows),
        "nonblank_dangling_fk_total": len(anomaly_rows) - len(blank_fk_rows),
        "confirmed_blanked_match_count": confirmed_match_count,
        "confirmed_blanked_match_failure_count": len(anomaly_rows) - confirmed_match_count,
        "remaining_root_anomaly_count": remaining_root_count,
        "cascade_anomaly_count": cascade_count,
        "blank_fk_breakdown": {
            "already_owner_confirmed_blanked": blank_confirmed,
            "not_in_confirmed_blanked": len(blank_fk_rows) - blank_confirmed,
            "by_sheet": dict(
                sorted(
                    Counter(
                        row["source_sheet"]
                        for row in row_analyses
                        if not row["raw_fk"]
                    ).items()
                )
            ),
        },
        "family_summary": family_rows,
        "row_analyses": row_analyses,
    }


def build_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Unresolved FK Analysis",
        "",
        f"- confirmed_blank_contract_path: {report['confirmed_blank_contract_path']}",
        f"- confirmed_blank_contract_sha256: {report['confirmed_blank_contract_sha256']}",
        f"- snapshot_path: {report['snapshot_path']}",
        f"- snapshot_sha256: {report['snapshot_sha256']}",
        f"- anomaly_report_path: {report['anomaly_report_path']}",
        f"- anomaly_report_sha256: {report['anomaly_report_sha256']}",
        f"- raw_anomaly_count: {report['raw_anomaly_count']}",
        f"- confirmed_blanked_match_count: {report['confirmed_blanked_match_count']}",
        f"- confirmed_blanked_match_failure_count: {report['confirmed_blanked_match_failure_count']}",
        f"- remaining_root_anomaly_count: {report['remaining_root_anomaly_count']}",
        f"- cascade_anomaly_count: {report['cascade_anomaly_count']}",
        f"- blank_fk_total: {report['blank_fk_total']}",
        f"- nonblank_dangling_fk_total: {report['nonblank_dangling_fk_total']}",
        "",
        "## Blank FK Breakdown",
        "",
        f"- already_owner_confirmed_blanked: {report['blank_fk_breakdown']['already_owner_confirmed_blanked']}",
        f"- not_in_confirmed_blanked: {report['blank_fk_breakdown']['not_in_confirmed_blanked']}",
        "",
        "## Family Summary",
        "",
        "| Family | Raw | Confirmed blanked | Remaining root | Cascade |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in report["family_summary"]:
        lines.append(
            f"| {row['source_sheet']} / {row['reason']} | {row['raw']} | {row['confirmed_blanked']} | {row['remaining_root']} | {row['cascade']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    anomaly_report_bytes = INPUT_PATH.read_bytes()
    anomaly_rows = json.loads(anomaly_report_bytes.decode("utf-8"))
    source_snapshot_bytes = SOURCE_SNAPSHOT_PATH.read_bytes()
    confirmed_rows = load_confirmed_blanked_contract_rows()
    confirmed_bytes = CONFIRMED_BLANKED_ROWS_PATH.read_bytes()
    report = build_unresolved_fk_analysis(
        anomaly_rows,
        confirmed_rows,
        snapshot_sha256=sha256(source_snapshot_bytes).hexdigest(),
        confirmed_contract_sha256=sha256(confirmed_bytes).hexdigest(),
        anomaly_report_sha256=sha256(anomaly_report_bytes).hexdigest(),
    )
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MD_OUT.write_text(build_markdown(report), encoding="utf-8")
    print(f"Wrote {JSON_OUT}")
    print(f"Wrote {MD_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
