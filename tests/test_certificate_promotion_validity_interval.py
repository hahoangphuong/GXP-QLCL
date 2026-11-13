"""GxP certificate issuance-date validity gate, with actual read/write parity.

Imported/historical candidate metadata may remain editable; a certificate
with expiry strictly before issue must never become Current.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.models.phase1 import AuditEvent, Certificate, CertificateVersion, Company, Site
from backend.app.services.workflow import CaseWorkflowService

WORKFLOW = CaseWorkflowService()
USER = build_authenticated_user("certificate-validity-actor", "admin")


@pytest.fixture
def certificates(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'validity-gate.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic certificate validity company")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic certificate validity site")
        session.add(site)
        session.flush()
        ids = {}
        for suffix, issued, expiry in (
            ("bad", date(2027, 1, 2), date(2027, 1, 1)),
            ("same-day", date(2027, 1, 2), date(2027, 1, 2)),
        ):
            certificate = Certificate(
                site_id=site.id, certificate_type="GSP",
                issuance_basis="administrative_no_inspection",
                line_code=suffix, latest_flag=False,
            )
            session.add(certificate)
            session.flush()
            session.add(CertificateVersion(
                certificate_id=certificate.id, version_no=1,
                certificate_number=f"GSP-{suffix}",
                issue_date=issued, expiry_date=expiry,
                is_latest_version=True,
            ))
            ids[suffix] = certificate.id
        session.commit()
    try:
        yield engine, ids
    finally:
        engine.dispose()


def _promote_action(session, certificate_id):
    return next(
        action for action in WORKFLOW.get_certificate_action_readiness(
            session, certificate_id=certificate_id, user=USER,
        )
        if action["action_key"] == "promote_current"
    )


def test_expiry_before_issue_is_blocked_in_readiness_and_mutation_without_audit(certificates):
    engine, ids = certificates
    with Session(engine) as session:
        candidate = session.get(Certificate, ids["bad"])
        assert candidate is not None
        version = session.scalar(select(CertificateVersion).where(
            CertificateVersion.certificate_id == candidate.id,
        ))
        assert version is not None
        action = _promote_action(session, candidate.id)
        assert action["available"] is False
        assert action["reason_code"] == "certificate_expiry_precedes_issue"
        assert action["required_permissions"] == ["certificate.approve"]
        assert action["expected_version"] == candidate.row_version
        with pytest.raises(HTTPException) as blocked:
            WORKFLOW.promote_certificate_current(
                session, certificate_id=candidate.id,
                expected_version=action["expected_version"], reason="invalid synthetic interval",
                user=USER,
            )
        assert blocked.value.status_code == 409
        assert "expiry date on or after issue date" in blocked.value.detail
        session.rollback()

    with Session(engine) as verify:
        candidate = verify.get(Certificate, ids["bad"])
        version = verify.scalar(select(CertificateVersion).where(
            CertificateVersion.certificate_id == ids["bad"],
        ))
        assert candidate.latest_flag is False
        assert version.issue_date == date(2027, 1, 2)
        assert version.expiry_date == date(2027, 1, 1)
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_same_day_is_accepted_and_editing_invalid_candidate_remains_possible(certificates):
    engine, ids = certificates
    with Session(engine) as session:
        valid = _promote_action(session, ids["same-day"])
        assert valid["available"] is True
        promoted = WORKFLOW.promote_certificate_current(
            session, certificate_id=ids["same-day"],
            expected_version=valid["expected_version"],
            reason="synthetic valid same day", user=USER,
        )
        session.commit()
        assert promoted["latest_flag"] is True

    with Session(engine) as session:
        bad = session.get(Certificate, ids["bad"])
        assert bad is not None
        editable = WORKFLOW.get_certificate_action_readiness(
            session, certificate_id=bad.id, user=USER,
        )
        assert next(a for a in editable if a["action_key"] == "edit_latest_version")["available"] is True
        corrected = WORKFLOW.upsert_certificate_latest_version(
            session, certificate_id=bad.id, expected_version=bad.row_version,
            certificate_number="GSP-bad", issue_date=date(2027, 1, 2),
            expiry_date=date(2028, 1, 1), scopes=[],
            reason="correct candidate interval", user=USER,
        )
        session.commit()
        action = _promote_action(session, ids["bad"])
        assert action["available"] is True
        assert action["expected_version"] == corrected["row_version"]
        promoted = WORKFLOW.promote_certificate_current(
            session, certificate_id=bad.id, expected_version=action["expected_version"],
            reason="promote corrected candidate", user=USER,
        )
        session.commit()
        assert promoted["latest_flag"] is True

    with Session(engine) as verify:
        assert verify.get(Certificate, ids["bad"]).latest_flag is True
        assert verify.get(Certificate, ids["same-day"]).latest_flag is True
        assert verify.scalar(select(func.count(AuditEvent.id))) == 3


def test_missing_permission_precedes_invalid_date_exposure(certificates):
    engine, ids = certificates
    reader = build_authenticated_user("certificate-read-only", "reader")
    with Session(engine) as session:
        actions = WORKFLOW.get_certificate_action_readiness(
            session, certificate_id=ids["bad"], user=reader,
        )
        promote = next(a for a in actions if a["action_key"] == "promote_current")
        assert promote["available"] is False
        assert promote["reason_code"] == "missing_permission"
        assert promote["required_permissions"] == ["certificate.approve"]
        assert session.scalar(select(func.count(AuditEvent.id))) == 0
