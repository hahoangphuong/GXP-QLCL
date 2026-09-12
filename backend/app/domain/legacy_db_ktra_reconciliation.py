"""Fail-closed, read-only parsers for the approved ``db.ktra`` facts.

These helpers produce evidence for a future migration plan.  They must never
be called by the production importer or use current canonical values as input.
"""
from __future__ import annotations

from datetime import date, time
from hashlib import sha256
import re
from typing import Any


_DATE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)")
_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")
_SENTINELS = {"", "-", "???"}
_TEAM_SPLIT = re.compile(r"(?:\r?\n|;|\s*/\s*)+")


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


def _parse_date(token: str) -> date | None:
    match = _DATE.fullmatch(token.strip())
    if match is None:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _single_date(value: str) -> tuple[date | None, int]:
    matches = _DATE.findall(value)
    if len(matches) != 1:
        return None, len(matches)
    return _parse_date("/".join(matches[0])), 1


def parse_legacy_inspection_decision(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    result: dict[str, Any] = {"state": "MISSING", "decision_reference": None, "decision_date": None, "raw": raw}
    if raw in _SENTINELS:
        return result
    parsed_date, count = _single_date(raw)
    if count != 1:
        result["state"] = "UNRESOLVED" if count > 1 else "PARTIAL"
        return result
    reference = _DATE.sub("", raw).strip(" ,;:-()\t")
    reference = re.sub(r"\b(?:ngày|ngay)\b", "", reference, flags=re.IGNORECASE).strip(" ,;:-()\t")
    if parsed_date is None:
        result["state"] = "PARTIAL"
    elif not reference:
        result.update(state="PARTIAL", decision_date=parsed_date)
    elif ";" in reference or "\n" in reference:
        result.update(state="UNRESOLVED", decision_date=parsed_date)
    else:
        result.update(state="KNOWN", decision_reference=reference, decision_date=parsed_date)
    return result


def parse_legacy_minutes_recorded(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    result: dict[str, Any] = {"state": "MISSING", "recorded_on": None, "recorded_time": None, "precision": "RAW_ONLY", "raw": raw}
    if raw in _SENTINELS:
        return result
    parsed_date, date_count = _single_date(raw)
    if date_count != 1:
        result["state"] = "UNRESOLVED" if date_count > 1 else "RAW_ONLY"
        return result
    if parsed_date is None:
        result["state"] = "RAW_ONLY"
        return result
    times = _TIME.findall(raw)
    if len(times) > 1:
        result["state"] = "UNRESOLVED"
        return result
    if times:
        try:
            parsed_time = time(int(times[0][0]), int(times[0][1]))
        except ValueError:
            result["state"] = "UNRESOLVED"
            return result
        return {**result, "state": "KNOWN", "recorded_on": parsed_date, "recorded_time": parsed_time, "precision": "DATE_TIME"}
    return {**result, "state": "KNOWN", "recorded_on": parsed_date, "precision": "DATE_ONLY"}


def parse_legacy_date(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    result: dict[str, Any] = {"state": "MISSING", "value": None, "raw": raw}
    if raw in _SENTINELS:
        return result
    parsed, count = _single_date(raw)
    if count != 1 or parsed is None or _DATE.fullmatch(raw) is None:
        result["state"] = "UNRESOLVED" if count > 1 else "PARTIAL"
        return result
    return {**result, "state": "KNOWN", "value": parsed}


def parse_legacy_team(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    if raw in _SENTINELS:
        return {"state": "MISSING", "members": [], "raw": raw}
    names = [part.strip() for part in _TEAM_SPLIT.split(raw) if part.strip()]
    if not names:
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
    parsed_date, count = _single_date(raw)
    if count > 1:
        return {"state": "UNRESOLVED", "reference": None, "submitted_on": None, "submitted_time": None, "raw": raw}
    reference = _DATE.sub("", raw).strip(" ,;:-()\t")
    if parsed_date is None and not reference:
        return {"state": "PARTIAL", "reference": None, "submitted_on": None, "submitted_time": None, "raw": raw}
    if count == 1 and parsed_date is None:
        return {"state": "PARTIAL", "reference": reference or None, "submitted_on": None, "submitted_time": None, "raw": raw}
    times = _TIME.findall(raw)
    if len(times) > 1:
        return {"state": "UNRESOLVED", "reference": None, "submitted_on": None, "submitted_time": None, "raw": raw}
    parsed_time = None
    if times:
        try:
            parsed_time = time(int(times[0][0]), int(times[0][1]))
        except ValueError:
            return {"state": "UNRESOLVED", "reference": None, "submitted_on": None, "submitted_time": None, "raw": raw}
    return {"state": "KNOWN", "reference": reference or None, "submitted_on": parsed_date, "submitted_time": parsed_time, "raw": raw}


def parse_legacy_certificate_id(value: object) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    if raw in _SENTINELS:
        return {"state": "MISSING", "legacy_certificate_id": None, "raw": raw}
    if not re.fullmatch(r"\d+", raw):
        return {"state": "UNRESOLVED", "legacy_certificate_id": None, "raw": raw}
    return {"state": "KNOWN", "legacy_certificate_id": int(raw), "raw": raw}
