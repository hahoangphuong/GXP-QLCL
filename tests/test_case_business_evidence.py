"""Actual Case business evidence for operator workflow, independent of Case labels.

Historical state-only transitions are intentionally preserved. This read model
reports whether canonical approval/certificate rows exist; it does not infer
issuance, create documents or authorize mutations.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CapaCycle, Certificate, CertificateVersion, Company,
    InspectionApprovalSubmission, InspectionOutcome, Site,
)
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService

CATALOG = CatalogReadService()
READER = build_authenticated_user("evidence-reader", "admin")


@pytest.fixture
def case_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'case-evidence.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Evidence synthetic company")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Evidence synthetic site")
        session.add(site)
        session.flush()
        row = Case(site_id=site.id, gxp_type="GMP", state=CaseState.CERTIFIED)
        session.add(row)
        session.commit()
        ids = row.id, site.id
    try:
        yield engine, *ids
    finally:
        engine.dispose()


def _evidence(session, case_id):
    body = CATALOG.get_case_workspace(session, case_id=case_id, user=READER)
    return CaseWorkspaceRead.model_validate(body).business_evidence.model_dump()


def _certificate(session, case_id, site_id, *, number, current=False, issued_on=None, expires_on=None):
    root = Certificate(
        case_id=case_id, site_id=site_id, certificate_type="GMP",
        issuance_basis="inspection_case", latest_flag=current,
    )
    session.add(root)
    session.flush()
    version = CertificateVersion(
        certificate_id=root.id, version_no=1, is_latest_version=True,
        certificate_number=number, issue_date=issued_on, expiry_date=expires_on,
    )
    session.add(version)
    session.flush()
    return root, version


def test_certified_case_does_not_fabricate_certificate_evidence(case_db):
    engine, case_id, _ = case_db
    with Session(engine) as session:
        evidence = _evidence(session, case_id)
        assert evidence == {
            "final_evaluation_recorded": False,
            "latest_capa_status": None,
            "completed_pct_count": 0,
            "completed_ct_count": 0,
            "completed_ct_with_pct_count": 0,
            "linked_certificate_count": 0,
            "complete_certificate_record_count": 0,
            "current_certificate_record_count": 0,
            "certificate_record_state": "none",
            "certified_case_without_complete_certificate_record": True,
        }
        assert session.scalar(select(func.count(AuditEvent.id))) == 0
        assert not session.new


def test_certificate_record_is_distinct_from_current_and_from_case_state(case_db):
    engine, case_id, site_id = case_db
    with Session(engine) as session:
        root, version = _certificate(session, case_id, site_id, number="GMP-REC-001")
        session.commit()
        incomplete = _evidence(session, case_id)
        assert incomplete["certificate_record_state"] == "incomplete"
        assert incomplete["linked_certificate_count"] == 1
        assert incomplete["complete_certificate_record_count"] == 0
        assert incomplete["certified_case_without_complete_certificate_record"] is True

        version.issue_date = date(2026, 11, 13)
        version.expiry_date = date(2029, 11, 13)
        session.commit()
        candidate = _evidence(session, case_id)
        assert candidate["certificate_record_state"] == "recorded_not_current"
        assert candidate["complete_certificate_record_count"] == 1
        assert candidate["current_certificate_record_count"] == 0
        assert candidate["certified_case_without_complete_certificate_record"] is False

        root.latest_flag = True
        session.commit()
        current = _evidence(session, case_id)
        assert current["certificate_record_state"] == "current"
        assert current["current_certificate_record_count"] == 1

        row = session.get(Case, case_id)
        row.state = CaseState.CLOSED
        session.commit()
        closed = _evidence(session, case_id)
        assert closed["current_certificate_record_count"] == 1
        assert closed["certified_case_without_complete_certificate_record"] is False


def test_approval_milestones_use_actual_completed_ct_to_completed_pct_link(case_db):
    engine, case_id, _ = case_db
    with Session(engine) as session:
        session.add_all([
            InspectionOutcome(case_id=case_id, final_evaluation="Đạt"),
            CapaCycle(case_id=case_id, round_no=1, status="accepted", result="accepted"),
        ])
        pct = InspectionApprovalSubmission(
            case_id=case_id, stage="PCT", round_no=1, completed_on=date(2026, 11, 11),
        )
        session.add(pct)
        session.flush()
        ct = InspectionApprovalSubmission(
            case_id=case_id, stage="CT", round_no=1, pct_submission_id=pct.id,
            completed_on=date(2026, 11, 12),
        )
        session.add(ct)
        session.commit()
        evidence = _evidence(session, case_id)
        assert evidence["final_evaluation_recorded"] is True
        assert evidence["latest_capa_status"] == "accepted"
        assert evidence["completed_pct_count"] == 1
        assert evidence["completed_ct_count"] == 1
        assert evidence["completed_ct_with_pct_count"] == 1

        # Data can be administratively corrected; the read model must not
        # claim a valid completed parent when the parent is no longer complete.
        pct.completed_on = None
        session.commit()
        corrected = _evidence(session, case_id)
        assert corrected["completed_pct_count"] == 0
        assert corrected["completed_ct_count"] == 1
        assert corrected["completed_ct_with_pct_count"] == 0


def test_other_case_certificates_never_count_as_selected_case_evidence(case_db):
    engine, case_id, site_id = case_db
    with Session(engine) as session:
        other = Case(site_id=site_id, gxp_type="GMP", state=CaseState.CERTIFIED)
        session.add(other)
        session.flush()
        _certificate(
            session, other.id, site_id, number="OTHER-GMP",
            issued_on=date(2026, 11, 1), expires_on=date(2029, 11, 1),
            current=True,
        )
        session.commit()
        selected = _evidence(session, case_id)
        assert selected["linked_certificate_count"] == 0
        assert selected["current_certificate_record_count"] == 0
        assert selected["certified_case_without_complete_certificate_record"] is True
        other_evidence = _evidence(session, other.id)
        assert other_evidence["current_certificate_record_count"] == 1

        # State is independent: no certificate gap flag on a draft Case.
        row = session.get(Case, case_id)
        row.state = CaseState.DRAFT
        session.commit()
        assert _evidence(session, case_id)["certified_case_without_complete_certificate_record"] is False
