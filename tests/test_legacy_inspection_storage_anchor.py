from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, LegacyInspectionStorageAnchor
from backend.app.domain.legacy_inspection_storage_anchor import (
    LegacyInspectionStorageAnchorError,
    build_legacy_inspection_storage_anchor_projection,
    extract_legacy_inspection_storage_anchor_rows_from_grid,
    load_projection_artifact,
    parse_storage_anchor_year,
    projection_payloads,
    projection_artifact_payload,
)
from tools.audit_legacy_inspection_storage_anchor import audit
from tools.audit_inspection_period_raw_evidence_coverage import audit_coverage


FIXTURE_PATH = Path("tests/fixtures/legacy_inspection_storage_anchor_grid.json")
SOURCE_VERSION = sha256(b"fixture-workbook").hexdigest()


def fixture_source_rows():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return extract_legacy_inspection_storage_anchor_rows_from_grid(payload["rows"])


@pytest.mark.parametrize(
    ("value", "status", "year"),
    [
        (datetime(2017, 6, 16), "usable", 2017),
        (date(2009, 8, 1), "usable", 2009),
        (42538.0, "usable", 2016),
        ("20-21/10/2017", "usable", 2017),
        ("31/07 - 01/08/2009", "usable", 2009),
        ("21-06-2019 và 14-15/02/2020", "conflict", None),
        ("-", "unavailable", None),
        ("", "unavailable", None),
        ("???", "unavailable", None),
        ("Xét hồ sơ", "unavailable", None),
    ],
)
def test_parse_storage_anchor_year_is_source_faithful(value, status, year):
    parsed = parse_storage_anchor_year(value)

    assert parsed.status == status
    assert parsed.year == year


def test_qualified_source_extraction_uses_registration_h_not_duplicate_remediation_columns():
    source_rows = {row.legacy_inspection_id: row for row in fixture_source_rows()}

    assert source_rows[41].source_row == 5
    assert source_rows[41].registration_submission.raw == "2017-06-16"
    assert source_rows[41].registration_submission.year == 2017
    assert source_rows[41].inspection_date.raw == "20-21/10/2017"
    assert source_rows[41].inspection_date.year == 2017
    assert source_rows[177].registration_submission.status == "unavailable"
    assert source_rows[177].inspection_date.year == 2009
    assert source_rows[554].inspection_date.status == "conflict"
    assert source_rows[455].inspection_date.status == "unavailable"


def test_qualified_source_extraction_rejects_header_layout_drift():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["rows"][2][7] = "KHẮC PHỤC"

    with pytest.raises(LegacyInspectionStorageAnchorError, match="qualified source column mismatch"):
        extract_legacy_inspection_storage_anchor_rows_from_grid(payload["rows"])


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def add_cases(session: Session, source_rows) -> None:
    for row in source_rows:
        session.add(
            Case(
                id=f"aaaaaaaa-0000-0000-0000-{row.legacy_inspection_id:012d}",
                legacy_inspection_id=row.legacy_inspection_id,
                site_id=f"bbbbbbbb-0000-0000-0000-{row.legacy_inspection_id:012d}",
                gxp_type="GMP",
                state=CaseState.APPLICATION_RECEIVED,
            )
        )
        session.flush()


def test_projection_builder_joins_exact_legacy_case_identity_and_is_idempotent():
    source_rows = fixture_source_rows()
    with build_session() as session:
        add_cases(session, source_rows)

        first = build_legacy_inspection_storage_anchor_projection(
            session,
            source_rows=source_rows,
            source_version=SOURCE_VERSION,
        )
        session.flush()
        rows = list(session.scalars(select(LegacyInspectionStorageAnchor)))
        second = build_legacy_inspection_storage_anchor_projection(
            session,
            source_rows=source_rows,
            source_version=SOURCE_VERSION,
        )

    assert first.created_count == 4
    assert first.existing_count == 0
    assert second.created_count == 0
    assert second.existing_count == 4
    assert len(rows) == 4
    assert {row.registration_submission_year for row in rows} == {None, 2017, 2018}
    assert {row.inspection_year_status for row in rows} == {"usable", "conflict", "unavailable"}


def test_projection_builder_rejects_missing_or_changed_immutable_source_evidence():
    source_rows = fixture_source_rows()
    with build_session() as session:
        with pytest.raises(LegacyInspectionStorageAnchorError, match="no exact Case mapping"):
            build_legacy_inspection_storage_anchor_projection(
                session,
                source_rows=source_rows,
                source_version=SOURCE_VERSION,
            )

        add_cases(session, source_rows)
        build_legacy_inspection_storage_anchor_projection(
            session,
            source_rows=source_rows,
            source_version=SOURCE_VERSION,
        )
        session.flush()
        with pytest.raises(LegacyInspectionStorageAnchorError, match="Immutable storage anchor evidence differs"):
            build_legacy_inspection_storage_anchor_projection(
                session,
                source_rows=source_rows,
                source_version=sha256(b"replacement-workbook").hexdigest(),
            )


def test_projection_audit_reports_source_coverage_and_field_parity():
    source_rows = fixture_source_rows()
    projection_rows = projection_payloads(source_rows, source_version=SOURCE_VERSION)

    report = audit(source_rows, source_version=SOURCE_VERSION, projection_rows=projection_rows)

    assert report["effective_case_count"] == 4
    assert report["registration_usable_year_count"] == 2
    assert report["inspection_fallback_usable_year_count"] == 1
    assert report["no_anchor_count"] == 1
    assert report["inspection_conflict_count"] == 1
    assert report["parity_passed"] is True

    projection_rows[0]["registration_submission_year"] = 2099
    mismatch = audit(source_rows, source_version=SOURCE_VERSION, projection_rows=projection_rows)
    assert mismatch["parity_passed"] is False
    assert mismatch["field_mismatches"][0]["legacy_inspection_id"] == 41

    duplicate_source = audit(
        [source_rows[0], source_rows[0]],
        source_version=SOURCE_VERSION,
        projection_rows=[projection_rows[0]],
    )
    assert duplicate_source["duplicate_source_case_ids"] == [41]
    assert duplicate_source["parity_passed"] is False


def test_projection_artifact_loader_is_exact_and_fails_closed_for_tampered_evidence(tmp_path: Path):
    source_rows = fixture_source_rows()
    artifact_path = tmp_path / "legacy_inspection_storage_anchor.json"
    artifact_path.write_text(
        json.dumps(
            projection_artifact_payload(source_rows, source_version=SOURCE_VERSION, snapshot_sha256="a" * 64),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded_rows, loaded_version, loaded_snapshot_sha = load_projection_artifact(artifact_path)

    assert loaded_rows == source_rows
    assert loaded_version == SOURCE_VERSION
    assert loaded_snapshot_sha == "a" * 64
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["rows"][0]["registration_submission_year"] = 2099
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(LegacyInspectionStorageAnchorError, match="source_hash does not match"):
        load_projection_artifact(artifact_path)

    artifact = projection_artifact_payload(source_rows, source_version=SOURCE_VERSION, snapshot_sha256="a" * 64)
    artifact["rows"].append(dict(artifact["rows"][0]))
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(LegacyInspectionStorageAnchorError, match="duplicate legacy inspection IDs"):
        load_projection_artifact(artifact_path)

    artifact = projection_artifact_payload(source_rows, source_version=SOURCE_VERSION, snapshot_sha256="a" * 64)
    artifact["source_version"] = "not-a-sha"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(LegacyInspectionStorageAnchorError, match="invalid source_version"):
        load_projection_artifact(artifact_path)

    artifact = projection_artifact_payload(source_rows, source_version=SOURCE_VERSION, snapshot_sha256="a" * 64)
    artifact["snapshot_sha256"] = "not-a-sha"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(LegacyInspectionStorageAnchorError, match="invalid snapshot_sha256"):
        load_projection_artifact(artifact_path)


def test_real_anchor_coverage_reports_unmatched_source_rows_without_losing_matched_raw_evidence():
    snapshot = json.loads(Path("artifacts/phase3c/legacy_snapshot.json").read_text(encoding="utf-8"))
    report = audit_coverage(snapshot, "artifacts/phase3c/legacy_inspection_storage_anchor.json")

    assert report["valid_legacy_row_count"] == 1533
    assert report["anchored_row_count"] == 1496
    assert report["missing_anchor_count"] == 37
    assert report["source_hash_validated_anchor_count"] == 1496
    assert report["state_coverage"] == {
        "KNOWN": {"total": 1424, "anchored": 1424, "missing_anchor": 0},
        "MISSING": {"total": 49, "anchored": 12, "missing_anchor": 37},
        "NON_DATE_EXPRESSION": {"total": 1, "anchored": 1, "missing_anchor": 0},
        "NOT_APPLICABLE": {"total": 4, "anchored": 4, "missing_anchor": 0},
        "PENDING_INPUT": {"total": 54, "anchored": 54, "missing_anchor": 0},
        "UNRESOLVED": {"total": 1, "anchored": 1, "missing_anchor": 0},
    }
    anchors, _, _ = load_projection_artifact("artifacts/phase3c/legacy_inspection_storage_anchor.json")
    raw_values = {anchor.inspection_date.raw for anchor in anchors}
    assert {"???", "-", "", "Xét hồ sơ", "24-01/2018"}.issubset(raw_values)
