from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.legacy_snapshot import read_core_sheet_rows
from backend.app.domain.phase2_import import FIELD_ALIASES


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
DATE_TOKEN_RE = re.compile(r"(?<!\d)\d{1,4}[./-]\d{1,2}(?:[./-]\d{1,4})?(?!\d)")
ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    asciiish = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    asciiish = asciiish.translate(str.maketrans({"Đ": "D", "đ": "d"}))
    return re.sub(r"\s+", " ", asciiish.lower()).strip()


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold(value))


def _contains_token_sequence(tokens: list[str], phrase: str) -> bool:
    wanted = _tokens(phrase)
    return any(tokens[index:index + len(wanted)] == wanted for index in range(len(tokens) - len(wanted) + 1))


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


def _date_morphology(value: str) -> str:
    text = value.strip()
    folded = _fold(text)
    if not folded:
        return "EMPTY"
    if folded == "-":
        return "SENTINEL_DASH"
    if folded == "???":
        return "SENTINEL_UNKNOWN"
    if ISO_TIMESTAMP_RE.fullmatch(text):
        return "ISO_TIMESTAMP"
    date_matches = list(DATE_TOKEN_RE.finditer(text))
    if not date_matches:
        return "INVALID_OR_OTHER"
    if "(" in text and ")" in text:
        return "ANNOTATED_DATE"
    if re.search(r"[,;]", text):
        return "MULTI_DATE"
    if re.search(r"\d{1,2}\s*-\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", text):
        return "DATE_RANGE"
    if re.search(r"\d{1,2}[./-]\d{1,2}\s*-\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", text):
        return "DATE_RANGE"
    if len(re.split(r"[./-]", date_matches[0].group())) == 2:
        return "PARTIAL_DATE"
    if len(date_matches) == 1:
        return "SINGLE_DATE"
    return "MULTI_DATE"


def _value_by_alias(row: dict[str, str], canonical: str) -> str:
    aliases = FIELD_ALIASES.get(canonical, set())
    for alias in aliases:
        value = row.get(alias)
        if value:
            return str(value).strip()
    return ""


def _profile_values(values: list[str], *, decision_composite: bool = False, field: str | None = None) -> dict[str, object]:
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
        report["trailing_date_separator_counts"] = Counter(
            re.search(r"\d{1,2}([./-])\d{1,2}([./-])\d{2,4}\s*$", value.strip()).group(1)
            for value in nonempty
            if re.search(r"\d{1,2}([./-])\d{1,2}([./-])\d{2,4}\s*$", value.strip())
        )
        references = Counter(
            _fold(TRAILING_DATE_RE.sub("", value).strip(" \t\r\n,;:-"))
            for value in nonempty
            if _classify_decision_composite(value) == "reference_plus_trailing_date"
        )
        report["duplicate_normalized_reference_count"] = sum(1 for count in references.values() if count > 1)
        report["multi_reference_count"] = sum(1 for value in nonempty if re.search(r"[,;|]\s*", TRAILING_DATE_RE.sub("", value)))
        report["invalid_trailing_date_count"] = sum(
            1 for value in nonempty if re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", value) and _classify_decision_composite(value) == "no_trailing_date"
        )
    if field:
        normalized = [_fold(value) for value in values]
        report["sentinel_counts"] = Counter(value for value in normalized if value in {"-", "???"})
        report["multi_value_count"] = sum(1 for value in nonempty if re.search(r"[,;|]", value))
        if field in {"inspected_at", "submitted_at", "certificate_issue_date", "certificate_expiry_date"}:
            morphology = Counter(_date_morphology(value) for value in values)
            report["morphology_counts"] = morphology
            report["date_like_count"] = sum(
                count
                for category, count in morphology.items()
                if category in {
                    "ISO_TIMESTAMP",
                    "SINGLE_DATE",
                    "DATE_RANGE",
                    "MULTI_DATE",
                    "PARTIAL_DATE",
                    "ANNOTATED_DATE",
                }
            )
            report["invalid_or_non_date_count"] = morphology["INVALID_OR_OTHER"]
        if field in {"applicable_standard", "inspection_type"}:
            report["normalized_domain_counts"] = Counter(value for value in normalized if value not in {"", "-", "???"})
    return report


def _discover_headers(snapshot: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    discovered: dict[str, list[dict[str, str]]] = {key: [] for key in HEADER_DISCOVERY_GROUPS}
    for sheet_name, rows in snapshot.items():
        headers: set[str] = set()
        for row in rows:
            headers.update(key for key in row if key != "__excel_row_number")
        for header in sorted(headers):
            folded = _fold(header)
            tokens = _tokens(header)
            for group, token_sets in HEADER_DISCOVERY_GROUPS.items():
                if any(all(_contains_token_sequence(tokens, token) for token in token_set) for token_set in token_sets):
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
                field=field,
            )
        profiles[sheet_name] = sheet_profiles
    migration_safety = {
        "decision_reference": "COMPOSITE_REQUIRES_SPLIT",
        "bbkt_reference": "OWNER_MISMATCH",
        "inspected_at": "AMBIGUOUS",
        "submitted_at": "INSUFFICIENT_SOURCE",
        "dossier_code": "AMBIGUOUS",
        "applicable_standard": "SAFE_WITH_DETERMINISTIC_NORMALIZATION",
        "inspection_type": "SAFE_WITH_DETERMINISTIC_NORMALIZATION",
        "certificate_number": "AMBIGUOUS",
        "certificate_issue_date": "SAFE_WITH_DETERMINISTIC_NORMALIZATION",
        "certificate_expiry_date": "AMBIGUOUS",
    }
    return {
        "schema_version": "inspection-case-lifecycle-legacy-profile/v1",
        "status": "READ_ONLY_LEGACY_PROFILE",
        "workbook_sha256": sha256(workbook.read_bytes()).hexdigest(),
        "workbook_name": workbook.name,
        "row_counts": {sheet: len(rows) for sheet, rows in snapshot.items()},
        "known_field_profiles": profiles,
        "candidate_headers": _discover_headers(snapshot),
        "field_source_headers": {
            sheet_name: {
                field: sorted({alias for row in rows for alias in FIELD_ALIASES.get(field, set()) if alias in row})
                for field in fields
            }
            for sheet_name, fields in KNOWN_FIELDS.items()
            for rows in [snapshot.get(sheet_name, [])]
        },
        "migration_safety": migration_safety,
        "migration_safety_basis": "human_reviewed_static_audit_conclusion",
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
