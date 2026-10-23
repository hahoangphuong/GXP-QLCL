"""Read-only candidate linkage between canonical Cases and Snapshot V2 db.ktra.

A Case's legacy_inspection_id may be matched to a source db.ktra ID only
when a *separately verified* source-column registry and workbook provenance
are provided. This does not prove which planning-sheet row supplied QĐKT
DaychuyenDD, Tinhthanh or TTVdd, and never authorizes document generation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any

from backend.app.domain.legacy_snapshot_v2 import (
    AUTHORITATIVE_WORKBOOK_SHA256, SCHEMA_VERSION, snapshot_legacy_int,
)


class QdKtSnapshotLinkBlocked(ValueError):
    pass


@dataclass(frozen=True)
class QdKtCaseLegacyId:
    case_id: str
    legacy_inspection_id: int | None


@dataclass(frozen=True)
class QdKtLegacyLinkResult:
    case_id: str
    source_row_number: int | None
    status: str
    planning_row_proven: bool = False
    qdkt_business_atoms_proven: bool = False


def audit_qdkt_case_dbktra_links(
    *, snapshot: Mapping[str, Any], cases: Iterable[QdKtCaseLegacyId],
    dbktra_id_column_ordinal: int,
    column_registry_verified: bool,
) -> tuple[QdKtLegacyLinkResult, ...]:
    """Match unique IDs using authoritative coordinates; never guess a header.

    The source column ordinal must be independently verified against the
    workbook field registry. Snapshot V2 deliberately records raw coordinates
    and does NOT establish semantic headers automatically.
    """
    if column_registry_verified is not True:
        raise QdKtSnapshotLinkBlocked("DBKTRA_ID_COLUMN_REGISTRY_UNPROVEN")
    if type(dbktra_id_column_ordinal) is not int or dbktra_id_column_ordinal < 1:
        raise QdKtSnapshotLinkBlocked("DBKTRA_ID_COLUMN_ORDINAL_INVALID")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise QdKtSnapshotLinkBlocked("SNAPSHOT_SCHEMA_UNPROVEN")
    workbook = snapshot.get("workbook")
    if not isinstance(workbook, Mapping) or workbook.get("sha256") != AUTHORITATIVE_WORKBOOK_SHA256:
        raise QdKtSnapshotLinkBlocked("SNAPSHOT_WORKBOOK_DIGEST_MISMATCH")
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, list):
        raise QdKtSnapshotLinkBlocked("SNAPSHOT_SHEETS_MISSING")
    rows = [sheet for sheet in sheets if isinstance(sheet, Mapping) and sheet.get("sheet_name") == "db.ktra"]
    if len(rows) != 1 or not isinstance(rows[0].get("raw_rows"), list):
        raise QdKtSnapshotLinkBlocked("DBKTRA_SOURCE_SHEET_AMBIGUOUS")
    source: dict[int, list[int]] = {}
    positions: set[int] = set()
    for row in rows[0]["raw_rows"]:
        if not isinstance(row, Mapping) or type(row.get("source_row_number")) is not int:
            raise QdKtSnapshotLinkBlocked("DBKTRA_SOURCE_ROW_INVALID")
        number = row["source_row_number"]
        if number < 1 or number in positions:
            raise QdKtSnapshotLinkBlocked("DBKTRA_ROW_NUMBER_DUPLICATE")
        positions.add(number)
        cells = row.get("cells")
        if not isinstance(cells, list):
            raise QdKtSnapshotLinkBlocked("DBKTRA_CELLS_INVALID")
        selected = [c for c in cells if isinstance(c, Mapping)
                    and c.get("column_ordinal") == dbktra_id_column_ordinal]
        if len(selected) != 1:
            raise QdKtSnapshotLinkBlocked("DBKTRA_ID_CELL_MISSING_OR_DUPLICATE")
        raw = selected[0].get("raw_value")
        parsed = snapshot_legacy_int(raw)
        if parsed is None or parsed <= 0:
            # Header rows and unissued/incomplete source rows are not Case IDs.
            # Do not silently associate them with Case records.
            continue
        source.setdefault(parsed, []).append(number)
    result: list[QdKtLegacyLinkResult] = []
    seen_case: set[str] = set()
    for case in cases:
        if not isinstance(case.case_id, str) or not case.case_id.strip() or case.case_id in seen_case:
            raise QdKtSnapshotLinkBlocked("CANONICAL_CASE_IDENTITY_AMBIGUOUS")
        seen_case.add(case.case_id)
        key = case.legacy_inspection_id
        if key is None:
            result.append(QdKtLegacyLinkResult(case.case_id, None, "CASE_LEGACY_ID_MISSING"))
        elif type(key) is not int or key <= 0:
            raise QdKtSnapshotLinkBlocked("CANONICAL_LEGACY_INSPECTION_ID_INVALID")
        else:
            matches = source.get(key, [])
            status = ("SOURCE_ROW_UNIQUE" if len(matches) == 1 else
                      "SOURCE_ROW_MISSING" if not matches else "SOURCE_ID_DUPLICATE")
            result.append(QdKtLegacyLinkResult(
                case.case_id, matches[0] if len(matches) == 1 else None, status,
            ))
    return tuple(result)


def verify_dbktra_id_header_coordinate(
    *, snapshot: Mapping[str, Any], header_row_number: int,
    source_header_row_attested: bool,
) -> int:
    """Return the exact db.ktra ID column only after proving its header cell.

    The header-row *identity* must come from separately attested workbook
    layout evidence; an arbitrary caller-supplied row number cannot confer
    semantic authority. A duplicate ID header or malformed row fails closed.
    """
    if source_header_row_attested is not True:
        raise QdKtSnapshotLinkBlocked("DBKTRA_HEADER_ROW_PROVENANCE_UNVERIFIED")
    if type(header_row_number) is not int or header_row_number < 1:
        raise QdKtSnapshotLinkBlocked("DBKTRA_HEADER_ROW_NUMBER_INVALID")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise QdKtSnapshotLinkBlocked("SNAPSHOT_SCHEMA_UNPROVEN")
    wb = snapshot.get("workbook")
    if not isinstance(wb, Mapping) or wb.get("sha256") != AUTHORITATIVE_WORKBOOK_SHA256:
        raise QdKtSnapshotLinkBlocked("SNAPSHOT_WORKBOOK_DIGEST_MISMATCH")
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, list):
        raise QdKtSnapshotLinkBlocked("SNAPSHOT_SHEETS_MISSING")
    matched = [s for s in sheets if isinstance(s, Mapping) and s.get("sheet_name") == "db.ktra"]
    if len(matched) != 1 or not isinstance(matched[0].get("raw_rows"), list):
        raise QdKtSnapshotLinkBlocked("DBKTRA_SOURCE_SHEET_AMBIGUOUS")
    rows = [r for r in matched[0]["raw_rows"] if isinstance(r, Mapping)
            and r.get("source_row_number") == header_row_number]
    if len(rows) != 1 or not isinstance(rows[0].get("cells"), list):
        raise QdKtSnapshotLinkBlocked("DBKTRA_HEADER_ROW_NOT_UNIQUE")
    headers = rows[0]["cells"]
    if any(not isinstance(c, Mapping) or type(c.get("column_ordinal")) is not int
           or c["column_ordinal"] < 1 for c in headers):
        raise QdKtSnapshotLinkBlocked("DBKTRA_HEADER_CELLS_INVALID")
    ordinals = [c["column_ordinal"] for c in headers]
    if len(ordinals) != len(set(ordinals)):
        raise QdKtSnapshotLinkBlocked("DBKTRA_HEADER_COLUMN_DUPLICATE")
    ids = [c["column_ordinal"] for c in headers if c.get("raw_value") == "ID"]
    if len(ids) != 1:
        raise QdKtSnapshotLinkBlocked("DBKTRA_ID_HEADER_NOT_UNIQUE")
    return ids[0]


def audit_qdkt_case_dbktra_links_with_header_proof(
    *, snapshot: Mapping[str, Any], cases: Iterable[QdKtCaseLegacyId],
    header_row_number: int, source_header_row_attested: bool,
) -> tuple[QdKtLegacyLinkResult, ...]:
    """Validate the workbook header before permitting the existing ID audit."""
    ordinal = verify_dbktra_id_header_coordinate(
        snapshot=snapshot, header_row_number=header_row_number,
        source_header_row_attested=source_header_row_attested,
    )
    return audit_qdkt_case_dbktra_links(
        snapshot=snapshot, cases=cases, dbktra_id_column_ordinal=ordinal,
        column_registry_verified=True,
    )
