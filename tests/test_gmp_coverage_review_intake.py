"""UNRESOLVED intake must never confer reviewed GMP coverage authority."""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.models import AppUser, Base, Case, Certificate, CertificateVersion, Company, GmpCoverageReviewEvent, Site
from backend.app.db.enums import CaseState
from backend.app.services.gmp_coverage_review_intake import UnresolvedReviewInput, append_unresolved_review_event


def test_unresolved_intake_bound_to_active_actor_and_real_site():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = AppUser(username="synthetic-operator", is_active=True)
            inactive = AppUser(username="synthetic-inactive", is_active=False)
            company = Company(legal_name="Synthetic company")
            session.add_all([user, inactive, company])
            session.flush()
            site = Site(company_id=company.id, site_name="Synthetic Site")
            other_site = Site(company_id=company.id, site_name="Other Site")
            session.add_all([site, other_site])
            session.flush()
            certificate = Certificate(site_id=site.id, certificate_type="GMP")
            session.add(certificate)
            session.flush()
            version = CertificateVersion(certificate_id=certificate.id, version_no=1)
            session.add(version)
            session.flush()
            data = UnresolvedReviewInput(
                certificate_version_id=version.id, site_id=other_site.id,
                case_id=None, source_snapshot_sha256="a"*64,
                source_document_sha256="b"*64, source_page_reference="Synthetic p2",
                rationale="Source needs operator adjudication",
            )
            with pytest.raises(ValueError, match="Active authenticated"):
                append_unresolved_review_event(session, evidence=data, authenticated_user_id=inactive.id)
            with pytest.raises(ValueError, match="SHA256"):
                append_unresolved_review_event(session, evidence=UnresolvedReviewInput(
                    **{**data.__dict__, "source_document_sha256": "x"*64}
                ), authenticated_user_id=user.id)
            row_id = append_unresolved_review_event(session, evidence=data, authenticated_user_id=user.id)
            stored = session.get(GmpCoverageReviewEvent, row_id)
            assert stored.decision_status == "UNRESOLVED"
            assert stored.decision_kind == "SITE_COVERAGE"
            assert stored.recorded_by_user_id == user.id
            assert stored.reviewer_user_id == user.id
            assert stored.site_id == other_site.id
            assert stored.case_id is None
            session.rollback()
        with Session(engine) as session:
            assert session.scalars(select(GmpCoverageReviewEvent)).all() == []
    finally:
        engine.dispose()
