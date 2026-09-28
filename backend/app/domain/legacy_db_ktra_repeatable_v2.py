"""Snapshot V2 representation adapter for repeatable ``db.ktra`` evidence.

This module owns storage-level normalization only.  It deliberately delegates
all business parsing to ``legacy_db_ktra_reconciliation``.
"""
from __future__ import annotations

from datetime import time
from hashlib import sha256
from math import isfinite
from typing import Any, Mapping

from backend.app.domain.legacy_db_ktra_reconciliation import (
    parse_legacy_inspection_decisions,
    parse_legacy_minutes_records,
)
from backend.app.domain.legacy_db_ktra_source_v2 import (
    excel_serial_date,
    snapshot_cell_value,
    snapshot_columns,
    substantive_source_value,
)
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION, snapshot_bytes
from backend.app.domain.phase2_import import parse_int


DB_KTRA_SHEET = "db.ktra"


def normalize_v2_minutes_representation(value: object) -> tuple[object, str]:
    """Return the parser input for a V2 B. bản cell without inferring meaning.

    V2 numeric cells are Excel serial dates only when they are finite whole
    numbers.  Fractional serials are intentionally left untouched so the
    canonical minutes parser can fail closed rather than discard a time.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value, "UNCHANGED"
    numeric = float(value)
    if not isfinite(numeric) or not numeric.is_integer():
        return value, "NUMERIC_UNRESOLVED"
    converted = excel_serial_date(value)
    if converted is None:
        return value, "NUMERIC_UNRESOLVED"
    # The serial proves a calendar date, not a clock time or timezone.  The
    # canonical parser already recognizes this DMY date-only representation.
    return converted.strftime("%d/%m/%Y"), "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE"


def excel_serial_minutes_representation_equivalent(
    *,
    source_representation: str,
    expected: Mapping[str, Any],
    historical: Mapping[str, Any],
) -> bool:
    """Prove the approved V1 ISO-midnight to V2 Excel-date representation bridge.

    ``legacy_raw`` remains historical V1 source lineage. It is equivalent to a
    V2 numeric cell only when its parser evidence proves the same date at
    historical midnight; this is not a generic date-only relaxation.
    """
    if source_representation != "NUMERIC_CONVERTED_EXCEL_SERIAL_DATE":
        return False
    if (
        expected.get("recorded_time") is not None
        or expected.get("precision") != "DATE_ONLY"
        or expected.get("source_format") != "DMY_DATE"
        or historical.get("recorded_on") != expected.get("recorded_on")
        or historical.get("recorded_time") != time(0, 0)
        or historical.get("precision") != "DATE_TIME_LOCAL"
        or historical.get("source_format") != "ISO_OFFSET_DATETIME"
    ):
        return False
    parsed = parse_legacy_minutes_records(historical.get("legacy_raw"))
    return (
        parsed["state"] == "KNOWN"
        and len(parsed["occurrences"]) == 1
        and parsed["occurrences"][0]["recorded_on"] == historical.get("recorded_on")
        and parsed["occurrences"][0]["recorded_time"] == historical.get("recorded_time")
        and parsed["occurrences"][0]["precision"] == historical.get("precision")
        and parsed["occurrences"][0]["source_format"] == historical.get("source_format")
    )


def eligible_v2_repeatable_rows(snapshot: Mapping[str, Any], *, expected_snapshot_sha256: str) -> list[dict[str, Any]]:
    """Extract exactly the effective db.ktra case population from Snapshot V2."""
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("repeatable V2 adapter requires Snapshot V2")
    if sha256(snapshot_bytes(dict(snapshot))).hexdigest() != expected_snapshot_sha256:
        raise ValueError("repeatable V2 adapter snapshot provenance is invalid")
    required = ("ID", "LOẠI KT", "ID CƠ SỞ", "Q. định", "B. bản")
    rows, columns = snapshot_columns(snapshot, DB_KTRA_SHEET, required_headers=required)
    missing = [name for name in required if name not in columns]
    if missing:
        raise ValueError(f"db.ktra repeatable source columns missing: {', '.join(missing)}")

    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        row_number = row.get("source_row_number")
        legacy_id = parse_int(snapshot_cell_value(row, columns["ID"]))
        if (
            not isinstance(row_number, int)
            or row_number <= 4
            or legacy_id is None
            or not substantive_source_value(snapshot_cell_value(row, columns["LOẠI KT"]))
            or not substantive_source_value(snapshot_cell_value(row, columns["ID CƠ SỞ"]))
        ):
            continue
        if legacy_id in seen:
            raise ValueError("Snapshot V2 contains duplicate effective db.ktra legacy inspection ID")
        seen.add(legacy_id)
        decision_raw = snapshot_cell_value(row, columns["Q. định"])
        minutes_raw = snapshot_cell_value(row, columns["B. bản"])
        minutes_parser_value, minutes_representation = normalize_v2_minutes_representation(minutes_raw)
        result.append(
            {
                "legacy_inspection_id": legacy_id,
                "source_row_number": row_number,
                "decision_raw": decision_raw,
                "minutes_raw": minutes_raw,
                "minutes_parser_value": minutes_parser_value,
                "minutes_representation": minutes_representation,
            }
        )
    return sorted(result, key=lambda item: (item["legacy_inspection_id"], item["source_row_number"]))


def parse_v2_repeatable_rows(snapshot: Mapping[str, Any], *, expected_snapshot_sha256: str) -> list[dict[str, Any]]:
    """Normalize V2 storage values, then delegate to the canonical parsers."""
    result = []
    for row in eligible_v2_repeatable_rows(snapshot, expected_snapshot_sha256=expected_snapshot_sha256):
        result.append(
            {
                **row,
                "decisions": parse_legacy_inspection_decisions(row["decision_raw"]),
                "minutes": parse_legacy_minutes_records(row["minutes_parser_value"]),
            }
        )
    return result
