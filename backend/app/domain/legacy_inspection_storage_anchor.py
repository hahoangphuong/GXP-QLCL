from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable, Literal, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, LegacyInspectionStorageAnchor


AnchorStatus = Literal["usable", "unavailable", "conflict"]

DB_KTRA_SHEET = "db.ktra"
DB_KTRA_HEADER_ROW_1_BASED = 4
DB_KTRA_GROUP_ROW_1_BASED = 3
REGISTRATION_SUBMISSION_COLUMN_1_BASED = 8  # H: ĐĂNG KÝ / Ngày nộp
INSPECTION_DATE_COLUMN_1_BASED = 13  # M: KIỂM TRA / Ngày K.tra
_YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


class LegacyInspectionStorageAnchorError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceYear:
    raw: str
    year: int | None
    status: AnchorStatus


@dataclass(frozen=True)
class LegacyInspectionStorageAnchorSourceRow:
    legacy_inspection_id: int
    source_sheet: str
    source_row: int
    registration_submission: SourceYear
    inspection_date: SourceYear
    source_hash: str

    def to_projection_payload(self, *, source_version: str) -> dict[str, Any]:
        return {
            "legacy_inspection_id": self.legacy_inspection_id,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
            "registration_submission_raw": self.registration_submission.raw,
            "registration_submission_year": self.registration_submission.year,
            "registration_submission_status": self.registration_submission.status,
            "inspection_date_raw": self.inspection_date.raw,
            "inspection_year": self.inspection_date.year,
            "inspection_year_status": self.inspection_date.status,
            "source_hash": self.source_hash,
            "source_version": source_version,
        }


@dataclass(frozen=True)
class LegacyInspectionStorageAnchorBuildResult:
    created_count: int
    existing_count: int
    source_count: int


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _excel_serial_date(value: Any) -> date | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    except (OverflowError, ValueError):
        return None


def parse_storage_anchor_year(value: Any) -> SourceYear:
    """Derive a source-faithful year without turning a date range into a date."""

    raw = _source_scalar_text(value)
    if not raw or raw in {"-", "???", "Xét hồ sơ"}:
        return SourceYear(raw=raw, year=None, status="unavailable")

    if isinstance(value, datetime):
        return SourceYear(raw=raw, year=value.year, status="usable")
    if isinstance(value, date):
        return SourceYear(raw=raw, year=value.year, status="usable")

    serial_date = _excel_serial_date(value)
    if serial_date is not None:
        return SourceYear(raw=raw, year=serial_date.year, status="usable")

    years = sorted({int(token) for token in _YEAR_PATTERN.findall(raw)})
    if len(years) == 1:
        return SourceYear(raw=raw, year=years[0], status="usable")
    if len(years) > 1:
        return SourceYear(raw=raw, year=None, status="conflict")
    return SourceYear(raw=raw, year=None, status="unavailable")


def _as_legacy_id(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number.is_integer():
        return None
    return int(number)


def _cell_value(row: Sequence[Any], ordinal_1_based: int) -> Any:
    index = ordinal_1_based - 1
    return row[index] if index < len(row) else None


def _qualified_header_error(*, actual_group: Any, actual_header: Any, expected_group: str, expected_header: str) -> LegacyInspectionStorageAnchorError:
    return LegacyInspectionStorageAnchorError(
        "db.ktra qualified source column mismatch: "
        f"expected group/header {expected_group!r}/{expected_header!r}, "
        f"got {_source_scalar_text(actual_group)!r}/{_source_scalar_text(actual_header)!r}."
    )


def extract_legacy_inspection_storage_anchor_rows_from_grid(rows: Sequence[Sequence[Any]]) -> list[LegacyInspectionStorageAnchorSourceRow]:
    """Extract H/M by qualified physical workbook identity, never by duplicate header text."""

    header_index = DB_KTRA_HEADER_ROW_1_BASED - 1
    group_index = DB_KTRA_GROUP_ROW_1_BASED - 1
    if len(rows) <= header_index:
        raise LegacyInspectionStorageAnchorError("db.ktra does not contain the required header row 4.")

    header_row = rows[header_index]
    group_row = rows[group_index] if len(rows) > group_index else ()
    checks = (
        (REGISTRATION_SUBMISSION_COLUMN_1_BASED, "ĐĂNG KÝ", "Ngày nộp"),
        (INSPECTION_DATE_COLUMN_1_BASED, "KIỂM TRA", "Ngày K.tra"),
    )
    for ordinal, group, header in checks:
        actual_group = _cell_value(group_row, ordinal)
        actual_header = _cell_value(header_row, ordinal)
        if _source_scalar_text(actual_group) != group or _source_scalar_text(actual_header) != header:
            raise _qualified_header_error(
                actual_group=actual_group,
                actual_header=actual_header,
                expected_group=group,
                expected_header=header,
            )

    source_rows: list[LegacyInspectionStorageAnchorSourceRow] = []
    seen_ids: set[int] = set()
    for source_row, row in enumerate(rows[header_index + 1 :], start=DB_KTRA_HEADER_ROW_1_BASED + 1):
        legacy_inspection_id = _as_legacy_id(_cell_value(row, 1))
        inspection_type = _source_scalar_text(_cell_value(row, 2))
        site_legacy_id = _as_legacy_id(_cell_value(row, 3))
        # db.ktra contains legacy placeholder rows with an ID but no case identity.
        # They are not effective cases and therefore cannot own a storage anchor.
        if legacy_inspection_id is None or not inspection_type or site_legacy_id is None:
            continue
        if legacy_inspection_id in seen_ids:
            raise LegacyInspectionStorageAnchorError(
                f"db.ktra contains duplicate effective inspection ID {legacy_inspection_id}."
            )
        seen_ids.add(legacy_inspection_id)

        registration_submission = parse_storage_anchor_year(
            _cell_value(row, REGISTRATION_SUBMISSION_COLUMN_1_BASED)
        )
        inspection_date = parse_storage_anchor_year(_cell_value(row, INSPECTION_DATE_COLUMN_1_BASED))
        source_hash = sha256(
            _canonical_json(
                {
                    "legacy_inspection_id": legacy_inspection_id,
                    "source_sheet": DB_KTRA_SHEET,
                    "source_row": source_row,
                    "registration_submission": asdict(registration_submission),
                    "inspection_date": asdict(inspection_date),
                }
            ).encode("utf-8")
        ).hexdigest()
        source_rows.append(
            LegacyInspectionStorageAnchorSourceRow(
                legacy_inspection_id=legacy_inspection_id,
                source_sheet=DB_KTRA_SHEET,
                source_row=source_row,
                registration_submission=registration_submission,
                inspection_date=inspection_date,
                source_hash=source_hash,
            )
        )
    return source_rows


def read_legacy_inspection_storage_anchor_rows(
    workbook_path: str | Path,
) -> tuple[list[LegacyInspectionStorageAnchorSourceRow], str]:
    """Read db.ktra directly through Excel, preserving the physical H/M contract."""

    try:
        import pywintypes
    except ModuleNotFoundError as exc:
        raise RuntimeError("storage-anchor extraction requires pywin32 on a Windows source tooling host.") from exc

    from backend.app.domain.legacy_snapshot import _excel_app

    source_path = Path(workbook_path)
    if not source_path.is_file():
        raise LegacyInspectionStorageAnchorError(f"Legacy workbook not found: {source_path}")
    app = _excel_app()
    workbook = None
    try:
        workbook = app.Workbooks.Open(str(source_path.resolve()), ReadOnly=True)
        worksheet = workbook.Worksheets(DB_KTRA_SHEET)
        used_range = worksheet.UsedRange
        rows = [list(row) for row in used_range.Value]
        return extract_legacy_inspection_storage_anchor_rows_from_grid(rows), sha256(source_path.read_bytes()).hexdigest()
    except pywintypes.com_error as exc:
        raise LegacyInspectionStorageAnchorError("Unable to read authoritative db.ktra source rows.") from exc
    finally:
        if workbook is not None:
            workbook.Close(False)
        app.Quit()


def projection_payloads(
    source_rows: Iterable[LegacyInspectionStorageAnchorSourceRow],
    *,
    source_version: str,
) -> list[dict[str, Any]]:
    if not re.fullmatch(r"[0-9a-f]{64}", source_version):
        raise LegacyInspectionStorageAnchorError("source_version must be a lowercase SHA-256 digest.")
    return [row.to_projection_payload(source_version=source_version) for row in source_rows]


def build_legacy_inspection_storage_anchor_projection(
    session: Session,
    *,
    source_rows: Iterable[LegacyInspectionStorageAnchorSourceRow],
    source_version: str,
) -> LegacyInspectionStorageAnchorBuildResult:
    """Insert source-faithful anchors; changed evidence is rejected rather than overwritten."""

    payloads = projection_payloads(source_rows, source_version=source_version)
    legacy_ids = [payload["legacy_inspection_id"] for payload in payloads]
    if len(legacy_ids) != len(set(legacy_ids)):
        raise LegacyInspectionStorageAnchorError("Projection input contains duplicate legacy inspection IDs.")

    cases = list(session.scalars(select(Case).where(Case.legacy_inspection_id.in_(legacy_ids)))) if legacy_ids else []
    case_by_legacy_id = {case.legacy_inspection_id: case for case in cases}
    missing_ids = sorted(set(legacy_ids) - set(case_by_legacy_id))
    if missing_ids:
        raise LegacyInspectionStorageAnchorError(
            f"Projection input has no exact Case mapping for legacy inspection IDs: {missing_ids}."
        )

    case_ids = [case.id for case in cases]
    existing_by_case_id = {
        row.case_id: row
        for row in session.scalars(
            select(LegacyInspectionStorageAnchor).where(LegacyInspectionStorageAnchor.case_id.in_(case_ids))
        )
    }
    created_count = 0
    existing_count = 0
    for payload in payloads:
        case = case_by_legacy_id[payload["legacy_inspection_id"]]
        existing = existing_by_case_id.get(case.id)
        if existing is not None:
            existing_count += 1
            if existing.source_hash != payload["source_hash"] or existing.source_version != source_version:
                raise LegacyInspectionStorageAnchorError(
                    f"Immutable storage anchor evidence differs for legacy inspection ID {payload['legacy_inspection_id']}."
                )
            continue
        session.add(
            LegacyInspectionStorageAnchor(
                case_id=case.id,
                source_sheet=payload["source_sheet"],
                source_row=payload["source_row"],
                registration_submission_raw=payload["registration_submission_raw"],
                registration_submission_year=payload["registration_submission_year"],
                registration_submission_status=payload["registration_submission_status"],
                inspection_date_raw=payload["inspection_date_raw"],
                inspection_year=payload["inspection_year"],
                inspection_year_status=payload["inspection_year_status"],
                source_hash=payload["source_hash"],
                source_version=payload["source_version"],
            )
        )
        created_count += 1
    return LegacyInspectionStorageAnchorBuildResult(
        created_count=created_count,
        existing_count=existing_count,
        source_count=len(payloads),
    )
