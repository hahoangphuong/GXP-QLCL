"""Read-only B6C discovery for ``db.ktra.ID CC GPs`` certificate references.

The historical Phase 2 importer owns creation of certificates from ``db.cc``.
This module deliberately owns no writes: it records only deterministic source
evidence and a future-link assessment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import re
from typing import Any, Iterable, Mapping

from backend.app.domain.legacy_db_ktra_source_v2 import (
    snapshot_cell_value,
    snapshot_columns,
    substantive_source_value,
)


SOURCE_SHEET = "db.ktra"
CERTIFICATE_SHEET = "db.cc"
_SENTINELS = {"", "-", "???"}
_MULTI_NUMERIC = re.compile(r"^\s*\d+\s*(?:[,;/&]|\bvà\b)\s*\d+(?:\s*(?:[,;/&]|\bvà\b)\s*\d+)*\s*$", re.IGNORECASE)


def safe_evidence(value: object) -> dict[str, object]:
    """Return shape/hash evidence without serializing source prose."""
    raw = "" if value is None else str(value).strip()
    shape = re.sub(r"\d", "9", raw)
    shape = re.sub(r"[A-Za-zÀ-ỹ]", "a", shape)
    return {
        "source_raw_hash": sha256(raw.encode("utf-8")).hexdigest(),
        "source_length": len(raw),
        "source_shape": re.sub(r"\s+", " ", shape)[:96],
    }


def parse_legacy_certificate_reference(value: object) -> dict[str, object]:
    """Parse one literal legacy certificate ID; never split ambiguous prose."""
    raw = "" if value is None else str(value).strip()
    lexical = "" if value is None else str(value)
    delimiters = tuple(name for name, marker in (
        ("COMMA", ","), ("SEMICOLON", ";"), ("SLASH", "/"), ("AMPERSAND", "&"), ("NEWLINE", "\n"),
    ) if marker in lexical)
    result: dict[str, object] = {
        "state": "SOURCE_UNRESOLVED",
        "legacy_certificate_id": None,
        "value_form": "TEXT_OTHER",
        "value_type": type(value).__name__.upper() if value is not None else "NULL",
        "leading_whitespace": isinstance(value, str) and value != value.lstrip(),
        "trailing_whitespace": isinstance(value, str) and value != value.rstrip(),
        "delimiter_kinds": delimiters,
        "evidence": safe_evidence(value),
    }
    if value is None:
        return {**result, "state": "SOURCE_MISSING", "value_form": "NULL"}
    if isinstance(value, bool):
        return {**result, "value_form": "BOOLEAN"}
    if isinstance(value, int):
        return {**result, "state": "KNOWN", "legacy_certificate_id": value, "value_form": "INTEGER"}
    if isinstance(value, float):
        if value.is_integer():
            return {**result, "state": "KNOWN", "legacy_certificate_id": int(value), "value_form": "FLOAT_INTEGRAL"}
        return {**result, "value_form": "FLOAT_DECIMAL"}
    if raw in _SENTINELS:
        form = "BLANK" if raw == "" else f"SENTINEL_{raw}"
        return {**result, "state": "SOURCE_MISSING", "value_form": form}
    if re.fullmatch(r"\d+", raw):
        return {**result, "state": "KNOWN", "legacy_certificate_id": int(raw), "value_form": "NUMERIC_STRING"}
    if _MULTI_NUMERIC.fullmatch(raw):
        return {**result, "state": "SOURCE_MULTI_ID", "value_form": "MULTI_NUMERIC_TEXT"}
    if re.fullmatch(r"\d+\.0+", raw):
        return {**result, "value_form": "DECIMAL_TEXT_INTEGRAL"}
    return result


def _parse_legacy_int(value: object) -> int | None:
    parsed = parse_legacy_certificate_reference(value)
    return parsed["legacy_certificate_id"] if parsed["state"] == "KNOWN" else None


def _snapshot_rows(snapshot: Mapping[str, Any], sheet: str, required: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows, columns = snapshot_columns(snapshot, sheet, required_headers=required)
    if any(name not in columns for name in required):
        missing = ", ".join(name for name in required if name not in columns)
        raise ValueError(f"{sheet} required source headers are missing: {missing}")
    return rows, columns


def _value(row: Mapping[str, Any], columns: Mapping[str, int], name: str) -> object:
    return snapshot_cell_value(row, columns[name])


def _normalized_text(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text.upper() or None


def _source_rows(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows, columns = _snapshot_rows(snapshot, SOURCE_SHEET, ("ID", "ID CƠ SỞ", "LOẠI KT", "ID CC GPs"))
    records: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        row_number = row.get("source_row_number")
        if not isinstance(row_number, int) or row_number <= 4:
            continue
        legacy_id = _parse_legacy_int(_value(row, columns, "ID"))
        if legacy_id is None:
            continue
        if legacy_id in seen:
            raise ValueError("Snapshot V2 db.ktra has duplicate valid legacy inspection ID")
        seen.add(legacy_id)
        site_id = _parse_legacy_int(_value(row, columns, "ID CƠ SỞ"))
        gxp_type = _normalized_text(_value(row, columns, "LOẠI KT"))
        parsed = parse_legacy_certificate_reference(_value(row, columns, "ID CC GPs"))
        records.append({
            "legacy_inspection_id": legacy_id,
            "source_row_number": row_number,
            "source_site_legacy_id": site_id,
            "source_gxp_type": gxp_type,
            "source_case_context_state": (
                "KNOWN" if site_id is not None and substantive_source_value(_value(row, columns, "LOẠI KT"))
                else "SOURCE_CASE_CONTEXT_UNRESOLVED"
            ),
            **parsed,
        })
    return sorted(records, key=lambda item: item["legacy_inspection_id"])


def _certificate_source_rows(snapshot: Mapping[str, Any]) -> dict[int, list[dict[str, Any]]]:
    rows, columns = _snapshot_rows(snapshot, CERTIFICATE_SHEET, ("ID", "ID ĐỢT KTRA", "ID CƠ SỞ", "LOẠI CC", "Mã số CC"))
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row_number = row.get("source_row_number")
        if not isinstance(row_number, int) or row_number <= 4:
            continue
        legacy_id = _parse_legacy_int(_value(row, columns, "ID"))
        if legacy_id is None:
            continue
        result[legacy_id].append({
            "legacy_certificate_id": legacy_id,
            "source_row_number": row_number,
            "inspection_legacy_id": _parse_legacy_int(_value(row, columns, "ID ĐỢT KTRA")),
            "site_legacy_id": _parse_legacy_int(_value(row, columns, "ID CƠ SỞ")),
            "certificate_type": _normalized_text(_value(row, columns, "LOẠI CC")),
            "certificate_number_evidence": safe_evidence(_value(row, columns, "Mã số CC")),
        })
    return result


def build_certificate_linkage_source_plan(snapshot: Mapping[str, Any], *, snapshot_sha256: str) -> dict[str, Any]:
    """Cross-check `ID CC GPs` with raw `db.cc` without canonical DB input."""
    source_rows = _source_rows(snapshot)
    certificate_rows = _certificate_source_rows(snapshot)
    reference_counts = Counter(item["legacy_certificate_id"] for item in source_rows if item["state"] == "KNOWN")
    classifications = Counter()
    mismatch_dimensions = Counter()
    records: list[dict[str, Any]] = []
    morphology = Counter(item["value_form"] for item in source_rows)
    value_types = Counter(item["value_type"] for item in source_rows)
    delimiters = Counter(delimiter for item in source_rows for delimiter in item["delimiter_kinds"])
    examples: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in source_rows:
        bucket = examples[item["value_form"]]
        if len(bucket) < 3:
            bucket.append({
                "legacy_inspection_id": item["legacy_inspection_id"],
                "source_row_number": item["source_row_number"],
                "evidence": item["evidence"],
            })
    for item in source_rows:
        record = dict(item)
        certificate_id = item["legacy_certificate_id"]
        if item["state"] != "KNOWN":
            classification = item["state"]
            matches: list[dict[str, Any]] = []
            mismatch_fields: list[str] = []
        else:
            matches = certificate_rows.get(certificate_id, [])
            mismatch_fields = []
            if not matches:
                classification = "CERTIFICATE_SOURCE_NOT_FOUND"
            elif len(matches) != 1:
                classification = "CERTIFICATE_SOURCE_DUPLICATE"
            else:
                matched = matches[0]
                if matched["inspection_legacy_id"] != item["legacy_inspection_id"]:
                    mismatch_fields.append("INSPECTION_OWNER")
                if matched["site_legacy_id"] != item["source_site_legacy_id"]:
                    mismatch_fields.append("SITE")
                if matched["certificate_type"] != item["source_gxp_type"]:
                    mismatch_fields.append("GXP_TYPE")
                context_incomplete = any(
                    matched[field] is None
                    for field in ("inspection_legacy_id", "site_legacy_id", "certificate_type")
                )
                classification = (
                    "SOURCE_CERTIFICATE_CONTEXT_INCOMPLETE" if context_incomplete
                    else "SOURCE_TYPE_MISMATCH" if "GXP_TYPE" in mismatch_fields
                    else "SOURCE_OWNER_MISMATCH" if mismatch_fields
                    else "EXACT_SOURCE_MATCH"
                )
                if context_incomplete:
                    mismatch_fields.append("CERTIFICATE_CONTEXT_INCOMPLETE")
        record.update({
            "classification": classification,
            "certificate_source_match_count": len(matches),
            "source_mismatch_fields": mismatch_fields,
            "duplicate_source_certificate_reference": bool(certificate_id is not None and reference_counts[certificate_id] > 1),
            "certificate_source_evidence": matches[0] if len(matches) == 1 else None,
        })
        records.append(record)
        classifications[classification] += 1
        mismatch_dimensions.update(mismatch_fields)
    return {
        "schema_version": "b6c-certificate-linkage-source-plan/v1",
        "provenance": {"snapshot_v2_sha256": snapshot_sha256, "database_mutated": False, "importer_invoked": False},
        "source_morphology": {
            "eligible_row_count": len(source_rows),
            "substantive_value_count": sum(1 for item in source_rows if item["state"] == "KNOWN"),
            "missing_or_sentinel_count": sum(1 for item in source_rows if item["state"] == "SOURCE_MISSING"),
            "exact_distinct_reference_count": len(reference_counts),
            "duplicate_reference_count": sum(1 for count in reference_counts.values() if count > 1),
            "value_form_counts": dict(sorted(morphology.items())),
            "value_type_counts": dict(sorted(value_types.items())),
            "leading_whitespace_count": sum(1 for item in source_rows if item["leading_whitespace"]),
            "trailing_whitespace_count": sum(1 for item in source_rows if item["trailing_whitespace"]),
            "delimiter_occurrence_counts": dict(sorted(delimiters.items())),
            "safe_examples_by_value_form": dict(sorted(examples.items())),
            "observed_cardinality": (
                "0..N_PROVEN"
                if any(item["state"] == "SOURCE_MULTI_ID" for item in source_rows)
                else "0..1_OBSERVED"
            ),
            "multi_id_cell_count": sum(1 for item in source_rows if item["state"] == "SOURCE_MULTI_ID"),
        },
        "cross_source_classification_counts": dict(sorted(classifications.items())),
        "mismatch_dimension_counts": dict(sorted(mismatch_dimensions.items())),
        "records": records,
    }


def build_canonical_certificate_linkage_comparison(
    source_plan: Mapping[str, Any],
    *,
    cases: Iterable[Mapping[str, Any]],
    sites: Iterable[Mapping[str, Any]],
    certificates: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare deterministic source rows to supplied canonical read-only rows."""
    case_by_legacy_id: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    site_by_legacy_id: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    certificate_by_legacy_id: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        legacy_id = case.get("legacy_inspection_id")
        if isinstance(legacy_id, int):
            case_by_legacy_id[legacy_id].append(case)
    for site in sites:
        legacy_id = site.get("legacy_site_id")
        if isinstance(legacy_id, int):
            site_by_legacy_id[legacy_id].append(site)
    for certificate in certificates:
        legacy_id = certificate.get("legacy_certificate_id")
        if isinstance(legacy_id, int):
            certificate_by_legacy_id[legacy_id].append(certificate)
    counts = Counter()
    records: list[dict[str, Any]] = []
    for source in source_plan["records"]:
        source_classification = source["classification"]
        expected_cases = case_by_legacy_id.get(source["legacy_inspection_id"], [])
        expected_sites = site_by_legacy_id.get(source.get("source_site_legacy_id"), [])
        certificates_for_id = certificate_by_legacy_id.get(source.get("legacy_certificate_id"), [])
        expected_case = expected_cases[0] if len(expected_cases) == 1 else None
        expected_site = expected_sites[0] if len(expected_sites) == 1 else None
        certificate = certificates_for_id[0] if len(certificates_for_id) == 1 else None
        if source_classification != "EXACT_SOURCE_MATCH":
            classification = "SOURCE_MISSING" if source_classification == "SOURCE_MISSING" else "SOURCE_UNRESOLVED"
        elif source["duplicate_source_certificate_reference"]:
            classification = "BLOCKED_AMBIGUOUS"
        elif source.get("source_site_legacy_id") is None:
            classification = "SOURCE_SITE_UNRESOLVED"
        elif not expected_sites:
            classification = "SOURCE_SITE_CANONICAL_NOT_FOUND"
        elif len(expected_sites) != 1:
            classification = "SOURCE_SITE_CANONICAL_DUPLICATE"
        elif len(expected_cases) != 1:
            classification = "CASE_OWNER_CONFLICT"
        elif expected_case.get("site_id") != expected_site.get("id"):
            classification = "CASE_SITE_CONFLICT"
        elif not certificates_for_id:
            classification = "MISSING_CANONICAL_CERTIFICATE"
        elif len(certificates_for_id) != 1:
            classification = "CANONICAL_CERTIFICATE_DUPLICATE"
        elif certificate.get("site_id") != expected_site.get("id"):
            classification = "CERTIFICATE_SITE_CONFLICT"
        elif expected_case.get("gxp_type") != source["source_gxp_type"]:
            classification = "CASE_GXP_TYPE_CONFLICT"
        elif certificate.get("certificate_type") != source["source_gxp_type"]:
            classification = "CERTIFICATE_GXP_TYPE_CONFLICT"
        elif certificate.get("case_id") == expected_case.get("id"):
            classification = "EXACT_MATCH"
        elif certificate.get("case_id") is None:
            classification = "MISSING_CASE_LINK"
        else:
            classification = "WRONG_CASE_LINK"
        counts[classification] += 1
        records.append({
            "legacy_inspection_id": source["legacy_inspection_id"],
            "legacy_certificate_id": source.get("legacy_certificate_id"),
            "source_site_legacy_id": source.get("source_site_legacy_id"),
            "expected_canonical_case_id": expected_case.get("id") if expected_case else None,
            "resolved_canonical_site_id": expected_site.get("id") if expected_site else None,
            "canonical_certificate_id": certificate.get("id") if certificate else None,
            "current_certificate_case_id": certificate.get("case_id") if certificate else None,
            "canonical_site_legacy_id": expected_site.get("legacy_site_id") if expected_site else None,
            "source_gxp_type": source.get("source_gxp_type"),
            "canonical_case_gxp_type": expected_case.get("gxp_type") if expected_case else None,
            "canonical_certificate_type": certificate.get("certificate_type") if certificate else None,
            "classification": classification,
            "writability_decision": "SAFE_LINK_CANDIDATE" if classification == "MISSING_CASE_LINK" else "NOT_WRITABLE",
            "writability_reason": classification,
            "source_evidence": source["evidence"],
        })
    safe = sum(1 for item in records if item["classification"] == "MISSING_CASE_LINK")
    return {
        "schema_version": "b6c-certificate-linkage-canonical-comparison/v1",
        "classification_counts": dict(sorted(counts.items())),
        "writability_counts": {
            "SAFE_LINK_CANDIDATE": safe,
            "ALREADY_CORRECT": counts["EXACT_MATCH"],
            "BLOCKED_AMBIGUOUS": counts["BLOCKED_AMBIGUOUS"] + counts["CASE_OWNER_CONFLICT"] + counts["SOURCE_SITE_CANONICAL_DUPLICATE"] + counts["CANONICAL_CERTIFICATE_DUPLICATE"],
            "BLOCKED_CONFLICT": counts["CASE_SITE_CONFLICT"] + counts["CERTIFICATE_SITE_CONFLICT"] + counts["CASE_GXP_TYPE_CONFLICT"] + counts["CERTIFICATE_GXP_TYPE_CONFLICT"] + counts["WRONG_CASE_LINK"],
            "BLOCKED_MISSING_CERTIFICATE": counts["MISSING_CANONICAL_CERTIFICATE"],
            "BLOCKED_SOURCE_EVIDENCE": counts["SOURCE_MISSING"] + counts["SOURCE_UNRESOLVED"] + counts["SOURCE_SITE_UNRESOLVED"] + counts["SOURCE_SITE_CANONICAL_NOT_FOUND"],
        },
        "records": records,
    }
