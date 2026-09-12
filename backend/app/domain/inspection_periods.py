"""Source-faithful parsing for legacy ``db.ktra.Ngay K.tra`` values.

The legacy field can describe several disconnected inspection visits.  This
module deliberately returns ordered segments instead of collapsing them into a
single envelope.  Callers must decide how (or whether) a compatibility reader
can project those segments into the old two-column representation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
import re


class InspectionPeriodSourceState(StrEnum):
    KNOWN = "KNOWN"
    PENDING_INPUT = "PENDING_INPUT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MISSING = "MISSING"
    NON_DATE_EXPRESSION = "NON_DATE_EXPRESSION"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class InspectionPeriodSegmentValue:
    ordinal: int
    started_on: date
    ended_on: date


@dataclass(frozen=True)
class InspectionPeriodParseResult:
    state: InspectionPeriodSourceState
    raw_value: str
    segments: tuple[InspectionPeriodSegmentValue, ...] = ()
    diagnostic: str | None = None


_SINGLE_DATE = re.compile(
    r"^(?:(?P<iso_year>\d{4})-(?P<iso_month>\d{1,2})-(?P<iso_day>\d{1,2})(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?|(?P<day>\d{1,2})(?P<sep>[/-])(?P<month>\d{1,2})(?P=sep)(?P<year>\d{4}))$"
)
_SAME_MONTH_RANGE = re.compile(r"^(?P<start>\d{1,2})\s*-\s*(?P<end>\d{1,2})\s*/\s*(?P<month>\d{1,2})\s*/\s*(?P<year>\d{4})$")
_CROSS_MONTH_RANGE = re.compile(r"^(?P<start_day>\d{1,2})\s*/\s*(?P<start_month>\d{1,2})\s*-\s*(?P<end_day>\d{1,2})\s*/\s*(?P<end_month>\d{1,2})\s*/\s*(?P<year>\d{4})$")
_COMPACT_SHARED_MONTH = re.compile(r"^(?P<days>\d{1,2}(?:\s*,\s*\d{1,2})+)\s*/\s*(?P<month>\d{1,2})\s*/\s*(?P<year>\d{4})$")
_TOP_LEVEL_SEPARATOR = re.compile(r"\s*(?:;|\n|&|\bvà\b)\s*", re.IGNORECASE)
_DATEISH = re.compile(r"\d")
_FULL_DATE_RANGE = re.compile(r"^(?P<start>\d{1,2}[/-]\d{1,2}[/-]\d{4})\s*(?:-|đến)\s*(?P<end>\d{1,2}[/-]\d{1,2}[/-]\d{4})$", re.IGNORECASE)
_VIETNAMESE_RANGE = re.compile(r"^từ\s+ngày\s+(?P<start>\d{1,2}[/-]\d{1,2}[/-]\d{4})\s+đến\s+ngày\s+(?P<end>\d{1,2}[/-]\d{1,2}[/-]\d{4})$", re.IGNORECASE)


def _date_or_none(*, year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _single_date(value: str) -> date | None:
    match = _SINGLE_DATE.fullmatch(value)
    if match is None:
        return None
    if match["iso_year"] is not None:
        return _date_or_none(year=int(match["iso_year"]), month=int(match["iso_month"]), day=int(match["iso_day"]))
    return _date_or_none(year=int(match["year"]), month=int(match["month"]), day=int(match["day"]))


def _parse_clause(value: str) -> tuple[tuple[date, date], ...] | None:
    """Parse one grammar clause; ``None`` means it is not safely understood."""
    direct = _single_date(value)
    if direct is not None:
        return ((direct, direct),)

    for expression in (_VIETNAMESE_RANGE, _FULL_DATE_RANGE):
        match = expression.fullmatch(value)
        if match is not None:
            start, end = _single_date(match["start"]), _single_date(match["end"])
            return None if start is None or end is None or start > end else ((start, end),)

    match = _CROSS_MONTH_RANGE.fullmatch(value)
    if match is not None:
        start = _date_or_none(year=int(match["year"]), month=int(match["start_month"]), day=int(match["start_day"]))
        end = _date_or_none(year=int(match["year"]), month=int(match["end_month"]), day=int(match["end_day"]))
        return None if start is None or end is None or start > end else ((start, end),)

    match = _SAME_MONTH_RANGE.fullmatch(value)
    if match is not None:
        start = _date_or_none(year=int(match["year"]), month=int(match["month"]), day=int(match["start"]))
        end = _date_or_none(year=int(match["year"]), month=int(match["month"]), day=int(match["end"]))
        # A descending day pair (e.g. 24-01/2018) is ambiguous, not reordered.
        return None if start is None or end is None or start > end else ((start, end),)

    match = _COMPACT_SHARED_MONTH.fullmatch(value)
    if match is not None:
        values: list[tuple[date, date]] = []
        for raw_day in match["days"].split(","):
            item = _date_or_none(year=int(match["year"]), month=int(match["month"]), day=int(raw_day.strip()))
            if item is None:
                return None
            values.append((item, item))
        return tuple(values)

    # Commas may separate full expressions, but only after compact shared-month
    # syntax has been ruled out above.
    if "," in value:
        parts = [part.strip() for part in value.split(",")]
        if any(not part for part in parts):
            return None
        parsed = [_parse_clause(part) for part in parts]
        if any(part is None for part in parsed):
            return None
        return tuple(segment for part in parsed if part is not None for segment in part)
    return None


def parse_legacy_inspection_periods(value: str | None) -> InspectionPeriodParseResult:
    raw = str(value or "")
    text = raw.strip()
    if not text:
        return InspectionPeriodParseResult(InspectionPeriodSourceState.MISSING, raw)
    if text == "???":
        return InspectionPeriodParseResult(InspectionPeriodSourceState.PENDING_INPUT, raw)
    if text == "-":
        return InspectionPeriodParseResult(InspectionPeriodSourceState.NOT_APPLICABLE, raw)

    # A comma at a physical line break is still a list separator, not a blank
    # source clause.  Preserve every other newline as an explicit separator.
    normalized = re.sub(r",\s*\r?\n\s*", ", ", text)
    clauses = [clause.strip() for clause in _TOP_LEVEL_SEPARATOR.split(normalized)]
    if not clauses or any(not clause for clause in clauses):
        return InspectionPeriodParseResult(InspectionPeriodSourceState.UNRESOLVED, raw, diagnostic="empty_clause")
    parsed = [_parse_clause(clause) for clause in clauses]
    if all(clause is None for clause in parsed) and not _DATEISH.search(text):
        return InspectionPeriodParseResult(InspectionPeriodSourceState.NON_DATE_EXPRESSION, raw)
    if any(clause is None for clause in parsed):
        return InspectionPeriodParseResult(InspectionPeriodSourceState.UNRESOLVED, raw, diagnostic="unsupported_date_grammar")
    pairs = tuple(pair for clause in parsed if clause is not None for pair in clause)
    segments = tuple(
        InspectionPeriodSegmentValue(ordinal=index, started_on=start, ended_on=end)
        for index, (start, end) in enumerate(pairs, start=1)
    )
    return InspectionPeriodParseResult(InspectionPeriodSourceState.KNOWN, raw, segments)
