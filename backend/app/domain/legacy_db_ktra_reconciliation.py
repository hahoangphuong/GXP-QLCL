"""Fail-closed, read-only parsers for the approved ``db.ktra`` facts.

These helpers produce evidence for a future migration plan.  They must never
be called by the production importer or use current canonical values as input.
"""
from __future__ import annotations

from datetime import date, time
from hashlib import sha256
import re
from typing import Any


_DMY_DATE = re.compile(r"(?<![\d-])(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)")
_LOCAL_TIME = re.compile(r"\s+(\d{1,2}):(\d{2})(?!\d)")
_ISO_OFFSET_DATETIME = re.compile(
    r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})(?!\d)"
)
_SENTINELS = {"", "-", "???"}
# The full committed snapshot has comma-separated team lists and no mixed
# delimiters.  Other separators remain unresolved rather than guessed.
_TEAM_SPLIT = re.compile(r"\s*,\s*")


def safe_evidence(value: object) -> dict[str, object]:
    """Return non-prose evidence safe for committed reconciliation artifacts."""
    raw = "" if value is None else str(value).strip()
    shape = re.sub(r"\d", "9", raw)
    shape = re.sub(r"[A-Za-zÀ-ỹ]", "a", shape)
    shape = re.sub(r"\s+", " ", shape)
    return {
        "source_raw_hash": sha256(raw.encode("utf-8")).hexdigest(),
        "source_length": len(raw),
        "source_shape": shape[:96],
    }


def _temporal_tokens(value: str) -> list[tuple[date | None, time | None, str, str, tuple[int, int]]]:
    """Return proven source date tokens without changing their offset semantics."""
    tokens: list[tuple[date | None, time | None, str, str, tuple[int, int]]] = []
    for match in _ISO_OFFSET_DATETIME.finditer(value):
        try:
            parsed_date = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            parsed_time = time(int(match.group(4)), int(match.group(5)), int(match.group(6)))
        except ValueError:
            parsed_date, parsed_time = None, None
        tokens.append((parsed_date, parsed_time, "DATE_TIME_LOCAL", "ISO_OFFSET_DATETIME", match.span()))
    occupied = [span for *_ignored, span in tokens]
    for match in _DMY_DATE.finditer(value):
        if any(match.start() < end and start < match.end() for start, end in occupied):
            continue
        try:
            parsed_date = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            parsed_date = None
        time_match = _LOCAL_TIME.match(value, match.end())
        parsed_time = None
        precision = "DATE_ONLY"
        source_format = "DMY_DATE"
        end = match.end()
        if time_match is not None:
            try:
                parsed_time = time(int(time_match.group(1)), int(time_match.group(2)))
            except ValueError:
                parsed_date = None
            precision = "DATE_TIME_LOCAL"
            source_format = "DMY_DATE_TIME"
            end = time_match.end()
        tokens.append((parsed_date, parsed_time, precision, source_format, (match.start(), end)))
    return sorted(tokens, key=lambda token: token[4][0])


def _single_temporal(value: str) -> tuple[date | None, time | None, str | None, str | None, int, tuple[int, int] | None]:
    tokens = _temporal_tokens(value)
    if len(tokens) != 1:
        return None, None, None, None, len(tokens), None
    parsed_date, parsed_time, precision, source_format, span = tokens[0]
    return parsed_date, parsed_time, precision, source_format, 1, span


def _without_temporal(value: str, span: tuple[int, int] | None) -> str:
    if span is None:
        return value
    return f"{value[:span[0]]}{value[span[1]:]}"


def parse_legacy_inspection_decision(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    result: dict[str, Any] = {"state": "MISSING", "decision_reference": None, "decision_date": None, "precision": "RAW_ONLY", "source_format": None, "raw": raw}
    if raw in _SENTINELS:
        return result
    parsed_date, _parsed_time, precision, source_format, count, span = _single_temporal(raw)
    if count != 1:
        result["state"] = "UNRESOLVED" if count > 1 else "PARTIAL"
        return result
    reference = _without_temporal(raw, span).strip(" ,;:-()\t")
    reference = re.sub(r"\b(?:ngày|ngay)\b", "", reference, flags=re.IGNORECASE).strip(" ,;:-()\t")
    if parsed_date is None:
        result["state"] = "PARTIAL"
    elif not reference:
        result.update(state="PARTIAL", decision_date=parsed_date, precision=precision, source_format=source_format)
    elif ";" in reference or "\n" in reference:
        result.update(state="UNRESOLVED", decision_date=parsed_date, precision=precision, source_format=source_format)
    else:
        result.update(state="KNOWN", decision_reference=reference, decision_date=parsed_date, precision=precision, source_format=source_format)
    return result


def parse_legacy_minutes_recorded(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    result: dict[str, Any] = {"state": "MISSING", "recorded_on": None, "recorded_time": None, "precision": "RAW_ONLY", "source_format": None, "raw": raw}
    if raw in _SENTINELS:
        return result
    parsed_date, parsed_time, precision, source_format, date_count, _span = _single_temporal(raw)
    if date_count != 1:
        result["state"] = "UNRESOLVED" if date_count > 1 else "RAW_ONLY"
        return result
    if parsed_date is None:
        result["state"] = "RAW_ONLY"
        return result
    return {
        **result,
        "state": "KNOWN",
        "recorded_on": parsed_date,
        "recorded_time": parsed_time,
        "precision": precision,
        "source_format": source_format,
    }


def parse_legacy_date(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    result: dict[str, Any] = {"state": "MISSING", "value": None, "precision": "RAW_ONLY", "source_format": None, "raw": raw}
    if raw in _SENTINELS:
        return result
    parsed, _time, precision, source_format, count, _span = _single_temporal(raw)
    if count != 1 or parsed is None or (_DMY_DATE.fullmatch(raw) is None and _ISO_OFFSET_DATETIME.fullmatch(raw) is None):
        result["state"] = "UNRESOLVED" if count > 1 else "PARTIAL"
        return result
    return {**result, "state": "KNOWN", "value": parsed, "precision": precision, "source_format": source_format}


def parse_legacy_team(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    if raw in _SENTINELS:
        return {"state": "MISSING", "members": [], "raw": raw}
    if any(marker in raw for marker in (";", "/", "\n", "\r")):
        return {"state": "UNRESOLVED", "members": [], "raw": raw}
    names = [part.strip() for part in _TEAM_SPLIT.split(raw)]
    if not names or any(not name for name in names):
        return {"state": "UNRESOLVED", "members": [], "raw": raw}
    members = [
        {"ordinal": index, "display_name": name, "role_code": "LEADER" if index == 1 else "SECRETARY" if index == 2 else "MEMBER"}
        for index, name in enumerate(names, start=1)
    ]
    return {"state": "KNOWN", "members": members, "raw": raw}


def parse_legacy_approval_submission(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    if raw in _SENTINELS:
        return {"state": "MISSING", "reference": None, "submitted_on": None, "submitted_time": None, "raw": raw}
    parsed_date, parsed_time, precision, source_format, count, span = _single_temporal(raw)
    if count > 1:
        return {"state": "UNRESOLVED", "reference": None, "submitted_on": None, "submitted_time": None, "raw": raw}
    reference = _without_temporal(raw, span).strip(" ,;:-()\t")
    # The snapshot proves the same date connector grammar as Q. định.
    reference = re.sub(r"\b(?:ngày|ngay)\b", "", reference, flags=re.IGNORECASE).strip(" ,;:-()\t")
    if parsed_date is None and not reference:
        return {"state": "PARTIAL", "reference": None, "submitted_on": None, "submitted_time": None, "raw": raw}
    if count == 1 and parsed_date is None:
        return {"state": "PARTIAL", "reference": reference or None, "submitted_on": None, "submitted_time": None, "raw": raw}
    return {"state": "KNOWN", "reference": reference or None, "submitted_on": parsed_date, "submitted_time": parsed_time, "precision": precision, "source_format": source_format, "raw": raw}


def parse_legacy_certificate_id(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    if raw in _SENTINELS:
        return {"state": "MISSING", "legacy_certificate_id": None, "raw": raw}
    if not re.fullmatch(r"\d+", raw):
        return {"state": "UNRESOLVED", "legacy_certificate_id": None, "raw": raw}
    return {"state": "KNOWN", "legacy_certificate_id": int(raw), "raw": raw}
