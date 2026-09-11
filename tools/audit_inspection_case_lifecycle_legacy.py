from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

from backend.app.domain.legacy_snapshot import read_core_sheet_rows
from backend.app.domain.phase2_import import FIELD_ALIASES


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "inspection_case_lifecycle_legacy_profile.json"


KNOWN_FIELDS = {
    "db.ktra": [
        "dossier_code",
        "submitted_at",
        "assessed_at",
        "assessor_name",
        "assessment_result",
        "inspected_at",
        "decision_reference",
        "bbkt_reference",
        "applicable_standard",
        "inspection_type",
    ],
    "db.cc": [
        "certificate_number",
        "certificate_issue_date",
        "certificate_expiry_date",
    ],
}

# Discovery is intentionally diagnostic only. A matching header is NOT a semantic owner.
HEADER_DISCOVERY_GROUPS = {
    "report_written_on": [
        ("ngay", "bao cao"),
        ("ngay", "bc"),
        ("bao cao",),
    ],
    "capa_incoming_reference": [
        ("cv", "khac phuc"),
        ("cong van", "khac phuc"),
        ("bckp",),
        ("khac phuc",),
    ],
    "final_evaluation": [
        ("danh gia", "cuoi"),
        ("ket qua", "cuoi"),
        ("ket luan",),
    ],
    "compliance_due_on": [
        ("han", "tuan thu"),
        ("han", "kiem tra"),
        ("tuan thu",),
    ],
    "approval_vice_chair": [
        ("phieu trinh", "pct"),
        ("pct",),
        ("pho chu tich",),
    ],
    "approval_chair": [
        ("phieu trinh", "ct"),
        ("chu tich",),
    ],
}

TRAILING_DATE_RE = re.compile(r"(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*$")


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    asciiish = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", asciiish.lower()).strip()


def _shape(value: str) -> str:
    result: list[str] = []
    for ch in value.strip():
        if ch.isdigit():
            token = "9"
        elif ch.isalpha():
            token = "A"
        elif ch.isspace():
            token = " "
        else:
            token = ch
        if result and token in {"9", "A", " "} and result[-1] == token:
            continue
        result.append(token)
    return "".join(result)[:160]


def _classify_decision_composite(value: str) -> str:
    text = value.strip()
    if not text:
        return "empty"
    match = TRAILING_DATE_RE.search(text)
    if not match:
        return "no_trailing_date"
    prefix = text[: match.start()].strip(" \t\r\n,;:-")
    return "reference_plus_trailing_date" if prefix else "date_only"


def _value_by_alias(row: dict[str, str], canonical: str) -> str:
    aliases = FIELD_ALIASES.get(canonical, set())
    for alias in aliases:
        value = row.get(alias)
        if value:
            return str(value).strip()
    return ""


def _profile_values(values: list[str], *, decision_composite: bool = False) -> dict[str, object]:
    nonempty = [value.strip() for value in values if value and value.strip()]
    shapes = Counter(_shape(value) for value in nonempty)
    report: dict[str, object] = {
        "total_rows": len(values),
        "nonempty": len(nonempty),
        "empty": len(values) - len(nonempty),
        "null_rate": round((len(values) - len(nonempty)) / len(values), 6) if values else None,
        "max_length": max((len(value) for value in nonempty), default=0),
        "top_shapes": shapes.most_common(20),
        "raw_values_persisted": False,
    }
    if decision_composite:
        report["composite_classification"] = Counter(_classify_decision_composite(value) for value in values)
    return report


def _discover_headers(snapshot: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    discovered: dict[str, list[dict[str, str]]] = {key: [] for key in HEADER_DISCOVERY_GROUPS}
    for sheet_name, rows in snapshot.items():
        headers: set[str] = set()
        for row in rows:
            headers.update(key for key in row if key != "__excel_row_number")
        for header in sorted(headers):
            folded = _fold(header)
            for group, token_sets in HEADER_DISCOVERY_GROUPS.items():
                if any(all(token in folded for token in token_set) for token_set in token_sets):
                    discovered[group].append({"sheet": sheet_name, "header": header})
    return discovered


def build_profile(workbook: Path) -> dict[str, object]:
    snapshot = read_core_sheet_rows(workbook)
    profiles: dict[str, object] = {}
    for sheet_name, fields in KNOWN_FIELDS.items():
        rows = snapshot.get(sheet_name, [])
        sheet_profiles: dict[str, object] = {}
        for field in fields:
            values = [_value_by_alias(row, field) for row in rows]
            sheet_profiles[field] = _profile_values(
                values,
                decision_composite=(sheet_name == "db.ktra" and field == "decision_reference"),
            )
        profiles[sheet_name] = sheet_profiles
    return {
        "schema_version": "inspection-case-lifecycle-legacy-profile/v1",
        "status": "READ_ONLY_LEGACY_PROFILE",
        "workbook_sha256": sha256(workbook.read_bytes()).hexdigest(),
        "workbook_name": workbook.name,
        "row_counts": {sheet: len(rows) for sheet, rows in snapshot.items()},
        "known_field_profiles": profiles,
        "candidate_headers": _discover_headers(snapshot),
        "guardrails": {
            "database_written": False,
            "legacy_workbook_written": False,
            "raw_values_persisted": False,
            "candidate_header_proves_owner": False,
            "backfill_performed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only legacy morphology/null-rate audit for inspection lifecycle fields.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    workbook = args.workbook.resolve()
    if not workbook.is_file():
        print("STATUS=INSPECTION_LIFECYCLE_LEGACY_PROFILE_FAILED")
        print(f"ERROR=workbook not found: {workbook}")
        return 2
    try:
        report = build_profile(workbook)
    except Exception as exc:  # preserve the underlying Excel/reader failure for the audit operator
        print("STATUS=INSPECTION_LIFECYCLE_LEGACY_PROFILE_FAILED")
        print(f"ERROR={exc}")
        return 2

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=dict) + "\n", encoding="utf-8")
    print("STATUS=READ_ONLY_LEGACY_PROFILE")
    print(f"WORKBOOK_SHA256={report['workbook_sha256']}")
    print(f"OUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
