"""Case-to-source-row audit cannot prove QĐKT business payload selection."""
import pytest

from backend.app.domain.legacy_snapshot_v2 import AUTHORITATIVE_WORKBOOK_SHA256, SCHEMA_VERSION
from backend.app.document.inspection_qd_kt_snapshot_case_link_audit import (
    QdKtCaseLegacyId, QdKtSnapshotLinkBlocked, audit_qdkt_case_dbktra_links,
)


def _snapshot(*, ids=(101, 102), duplicate=False):
    rows = [
        {"source_row_number": i + 2, "cells": [{"column_ordinal": 3, "raw_value": value}]}
        for i, value in enumerate(ids)
    ]
    if duplicate:
        rows.append({"source_row_number": 10, "cells": [{"column_ordinal": 3, "raw_value": 101}]})
    return {
        "schema_version": SCHEMA_VERSION,
        "workbook": {"sha256": AUTHORITATIVE_WORKBOOK_SHA256},
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": rows}],
    }


def _audit(snapshot=None, *, attested=True, cases=None, column=3):
    return audit_qdkt_case_dbktra_links(
        snapshot=snapshot if snapshot is not None else _snapshot(),
        cases=cases if cases is not None else [
            QdKtCaseLegacyId("case-a", 101),
            QdKtCaseLegacyId("case-b", 900),
            QdKtCaseLegacyId("case-c", None),
        ],
        dbktra_id_column_ordinal=column,
        column_registry_verified=attested,
    )


def test_unique_missing_and_null_rows_stay_unrenderable():
    a, b, c = _audit()
    assert (a.status, a.source_row_number) == ("SOURCE_ROW_UNIQUE", 2)
    assert (b.status, b.source_row_number) == ("SOURCE_ROW_MISSING", None)
    assert (c.status, c.source_row_number) == ("CASE_LEGACY_ID_MISSING", None)
    assert all(not x.planning_row_proven and not x.qdkt_business_atoms_proven for x in (a, b, c))


def test_duplicate_source_id_never_binds_arbitrary_first_row():
    row, = _audit(_snapshot(duplicate=True), cases=[QdKtCaseLegacyId("case-a", 101)])
    assert (row.status, row.source_row_number) == ("SOURCE_ID_DUPLICATE", None)


@pytest.mark.parametrize("kwargs,error", [
    ({"attested": False}, "DBKTRA_ID_COLUMN_REGISTRY_UNPROVEN"),
    ({"column": True}, "DBKTRA_ID_COLUMN_ORDINAL_INVALID"),
    ({"column": 0}, "DBKTRA_ID_COLUMN_ORDINAL_INVALID"),
    ({"cases": [QdKtCaseLegacyId("a", True)]}, "CANONICAL_LEGACY_INSPECTION_ID_INVALID"),
    ({"cases": [QdKtCaseLegacyId("a", 1), QdKtCaseLegacyId("a", 2)]}, "CANONICAL_CASE_IDENTITY_AMBIGUOUS"),
])
def test_unverified_source_or_case_blocks(kwargs, error):
    with pytest.raises(QdKtSnapshotLinkBlocked, match=error):
        _audit(**kwargs)


def test_forged_workbook_digest_rejected():
    invalid = _snapshot()
    invalid["workbook"]["sha256"] = "0" * 64
    with pytest.raises(QdKtSnapshotLinkBlocked, match="SNAPSHOT_WORKBOOK_DIGEST_MISMATCH"):
        _audit(invalid)


def test_missing_column_must_not_fallback_to_other_cell():
    with pytest.raises(QdKtSnapshotLinkBlocked, match="DBKTRA_ID_CELL_MISSING_OR_DUPLICATE"):
        _audit(column=4)


def _with_header(snapshot, *, header="ID", second_id=False):
    sheet = snapshot["sheets"][0]
    cells = [{"column_ordinal": 1, "raw_value": "CƠ SỞ"},
             {"column_ordinal": 3, "raw_value": header}]
    if second_id:
        cells.append({"column_ordinal": 4, "raw_value": "ID"})
    sheet["raw_rows"].insert(0, {"source_row_number": 1, "cells": cells})
    return snapshot


def test_attested_exact_header_derives_column_and_keeps_planning_unproven():
    from backend.app.document.inspection_qd_kt_snapshot_case_link_audit import (
        audit_qdkt_case_dbktra_links_with_header_proof,
    )
    source = _with_header(_snapshot())
    out = audit_qdkt_case_dbktra_links_with_header_proof(
        snapshot=source, cases=[QdKtCaseLegacyId("c", 101)],
        header_row_number=1, source_header_row_attested=True,
    )
    assert (out[0].status, out[0].source_row_number) == ("SOURCE_ROW_UNIQUE", 2)
    assert out[0].planning_row_proven is False
    assert out[0].qdkt_business_atoms_proven is False


@pytest.mark.parametrize("header,duplicate,error", [
    ("ID CƠ SỞ", False, "DBKTRA_ID_HEADER_NOT_UNIQUE"),
    ("ID", True, "DBKTRA_ID_HEADER_NOT_UNIQUE"),
])
def test_header_mismatch_or_duplicate_fails_closed(header, duplicate, error):
    from backend.app.document.inspection_qd_kt_snapshot_case_link_audit import (
        verify_dbktra_id_header_coordinate,
    )
    with pytest.raises(QdKtSnapshotLinkBlocked, match=error):
        verify_dbktra_id_header_coordinate(
            snapshot=_with_header(_snapshot(), header=header, second_id=duplicate),
            header_row_number=1, source_header_row_attested=True,
        )


def test_header_attestation_and_coordinate_are_not_optional():
    from backend.app.document.inspection_qd_kt_snapshot_case_link_audit import (
        verify_dbktra_id_header_coordinate,
    )
    snap = _with_header(_snapshot())
    with pytest.raises(QdKtSnapshotLinkBlocked, match="DBKTRA_HEADER_ROW_PROVENANCE_UNVERIFIED"):
        verify_dbktra_id_header_coordinate(
            snapshot=snap, header_row_number=1, source_header_row_attested=False,
        )
    with pytest.raises(QdKtSnapshotLinkBlocked, match="DBKTRA_HEADER_ROW_NOT_UNIQUE"):
        verify_dbktra_id_header_coordinate(
            snapshot=snap, header_row_number=9, source_header_row_attested=True,
        )
