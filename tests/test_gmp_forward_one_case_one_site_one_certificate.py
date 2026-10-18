"""Prospective GMP one-Case/one-Site/at-most-one-issuance contract.

Historical imported exceptions are not rewritten or grandfathered into
permission to create new duplicates through the issuance API.
"""
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def _init_context(session, *, gxp_type="GMP"):
    company = Company(legal_name="Test issuer")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="One inspected site")
    session.add(site)
    session.flush()
    case = Case(
        site_id=site.id, gxp_type=gxp_type,
        state=CaseState.AWAITING_CERTIFICATE_DECISION,
    )
    session.add(case)
    session.flush()
    return site, case


def _issue(session, site_id, case_id, *, gxp_type="GMP", number="GMP-CERT-01"):
    return CaseWorkflowService().issue_certificate(
        session,
        site_id=site_id,
        case_id=case_id,
        certificate_type=gxp_type,
        issuance_basis="inspection_case",
        certificate_number=number,
        issue_date=date(2026, 10, 18),
        expiry_date=date(2029, 10, 18),
        scopes=[],
        reason="Prospective case-backed issue",
        user=build_authenticated_user("authorized-issuer", "admin"),
    )


def test_case_with_no_issued_gmp_is_eligible_until_first_issue():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        site, case = _init_context(session)
        readiness = CaseWorkflowService().get_case_certificate_issue_readiness(
            session, case_id=case.id, user=build_authenticated_user("issuer", "admin")
        )
        assert readiness["available"] is True
        first = _issue(session, site.id, case.id)
        assert first["site_id"] == site.id
        assert first["case_id"] == case.id
        assert first["certificate_type"] == "GMP"
        session.commit()
    engine.dispose()


def test_second_gmp_issue_from_same_case_is_refused_before_writes_and_readiness_agrees():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        site, case = _init_context(session)
        first = _issue(session, site.id, case.id)
        session.commit()
        before = (
            session.query(Certificate).count(),
            session.query(CertificateVersion).count(),
            session.query(AuditEvent).count(),
        )
        readiness = CaseWorkflowService().get_case_certificate_issue_readiness(
            session, case_id=case.id, user=build_authenticated_user("issuer", "admin")
        )
        assert readiness["available"] is False
        assert readiness["reason_code"] == "gmp_case_already_issued"
        with pytest.raises(HTTPException) as error:
            _issue(session, site.id, case.id, number="GMP-CERT-SECOND")
        assert error.value.status_code == 409
        assert "already" in str(error.value.detail).lower()
        after = (
            session.query(Certificate).count(),
            session.query(CertificateVersion).count(),
            session.query(AuditEvent).count(),
        )
        assert after == before
        assert session.get(Certificate, first["certificate_id"]).case_id == case.id
    engine.dispose()


def test_replacement_requires_another_case_even_for_same_site():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        site, original = _init_context(session)
        newer = Case(
            site_id=site.id, gxp_type="GMP",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
        )
        session.add(newer)
        session.flush()
        first = _issue(session, site.id, original.id, number="CERT-OLD")
        second = _issue(session, site.id, newer.id, number="CERT-NEW")
        assert first["certificate_id"] != second["certificate_id"]
        assert first["case_id"] != second["case_id"]
        assert first["site_id"] == second["site_id"]
        assert session.query(Certificate).count() == 2
    engine.dispose()


def test_gmp_case_cannot_issue_certificate_for_a_different_site():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        site, case = _init_context(session)
        other = Site(company_id=site.company_id, site_name="Different physical site")
        session.add(other)
        session.flush()
        with pytest.raises(HTTPException) as error:
            _issue(session, other.id, case.id)
        assert error.value.status_code == 422
        assert session.query(Certificate).count() == 0
    engine.dispose()


def test_gmp_duplicate_guard_does_not_mutate_historical_rows():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        site, case = _init_context(session)
        legacy_first = Certificate(
            legacy_certificate_id=100, site_id=site.id, case_id=case.id,
            certificate_type="GMP", issuance_basis="inspection_case",
        )
        legacy_second = Certificate(
            legacy_certificate_id=101, site_id=site.id, case_id=case.id,
            certificate_type="GMP", issuance_basis="inspection_case",
        )
        session.add_all([legacy_first, legacy_second])
        session.commit()
        with pytest.raises(HTTPException) as error:
            _issue(session, site.id, case.id)
        assert error.value.status_code == 409
        rows = session.scalars(
            select(Certificate).where(Certificate.case_id == case.id)
        ).all()
        assert {row.legacy_certificate_id for row in rows} == {100, 101}
        assert len(rows) == 2
    engine.dispose()
