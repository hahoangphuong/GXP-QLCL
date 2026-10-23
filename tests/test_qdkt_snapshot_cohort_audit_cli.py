"""End-to-end source and cohort guards without a real DB or file writes."""
import pytest

from backend.app.domain.legacy_snapshot_v2 import AUTHORITATIVE_WORKBOOK_SHA256, SCHEMA_VERSION
from tools.audit_qdkt_snapshot_cohort import (
    QdKtCohortAuditBlocked, _checked_cohort, build_qdkt_cohort_report,
)


def _snapshot():
    return {
        "schema_version": SCHEMA_VERSION,
        "workbook": {"sha256": AUTHORITATIVE_WORKBOOK_SHA256},
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": [
            {"source_row_number": 1, "cells": [
                {"column_ordinal": 1, "raw_value": "ID"},
                {"column_ordinal": 3, "raw_value": "ID CƠ SỞ"},
            ]},
            {"source_row_number": 2, "cells": [
                {"column_ordinal": 1, "raw_value": 101},
                {"column_ordinal": 3, "raw_value": 50},
            ]},
            {"source_row_number": 3, "cells": [
                {"column_ordinal": 3, "raw_value": "no inspection ID"},
            ]},
            {"source_row_number": 4, "cells": [
                {"column_ordinal": 1, "raw_value": 101},
            ]},
            {"source_row_number": 5, "cells": [
                {"column_ordinal": 1, "raw_value": 102},
            ]},
        ]}],
    }


def _cohort():
    return [
        {"case_id": "a", "legacy_inspection_id": 101},
        {"case_id": "b", "legacy_inspection_id": 102},
        {"case_id": "c", "legacy_inspection_id": 999},
        {"case_id": "d", "legacy_inspection_id": None},
    ]


def test_aggregate_report_never_contains_raw_business_or_case_ids():
    result = build_qdkt_cohort_report(
        snapshot=_snapshot(), cohort=_cohort(), header_row_number=1,
        source_header_row_attested=True,
        snapshot_sha256="a" * 64, cohort_sha256="b" * 64,
    )
    assert result["case_count"] == 4
    assert result["status_counts"] == {
        "CASE_LEGACY_ID_MISSING": 1,
        "SOURCE_ID_DUPLICATE": 1,
        "SOURCE_ROW_MISSING": 1,
        "SOURCE_ROW_UNIQUE": 1,
    }
    assert result["planning_row_proven"] is False
    assert result["qdkt_business_atoms_proven"] is False
    assert result["ready_to_render"] is False
    import json
    serialized = json.dumps(result)
    assert "no inspection ID" not in serialized
    assert '"case_id"' not in serialized


@pytest.mark.parametrize("bad,error", [
    ([], "CASE_COHORT_EMPTY"),
    ({}, "CASE_COHORT_ARRAY_REQUIRED"),
    ([{"case_id": "a", "legacy_inspection_id": True}], "CASE_COHORT_LEGACY_ID_INVALID"),
    ([{"case_id": "a", "legacy_inspection_id": 1, "name": "private"}], "CASE_COHORT_EXACT_KEYS_REQUIRED"),
    ([{"case_id": "a", "legacy_inspection_id": 1},
      {"case_id": "a", "legacy_inspection_id": 2}], "CASE_COHORT_DUPLICATE_CASE_ID"),
])
def test_invalid_or_leaky_cohort_rejected(bad, error):
    with pytest.raises(QdKtCohortAuditBlocked, match=error):
        _checked_cohort(bad)


def test_missing_header_attestation_fails():
    from backend.app.document.inspection_qd_kt_snapshot_case_link_audit import QdKtSnapshotLinkBlocked
    with pytest.raises(QdKtSnapshotLinkBlocked, match="DBKTRA_HEADER_ROW_PROVENANCE_UNVERIFIED"):
        build_qdkt_cohort_report(
            snapshot=_snapshot(), cohort=_cohort(), header_row_number=1,
            source_header_row_attested=False,
            snapshot_sha256="a" * 64, cohort_sha256="b" * 64,
        )


def test_wrong_source_header_rejected():
    from backend.app.document.inspection_qd_kt_snapshot_case_link_audit import QdKtSnapshotLinkBlocked
    with pytest.raises(QdKtSnapshotLinkBlocked):
        build_qdkt_cohort_report(
            snapshot=_snapshot(), cohort=_cohort(), header_row_number=2,
            source_header_row_attested=True,
            snapshot_sha256="a" * 64, cohort_sha256="b" * 64,
        )
