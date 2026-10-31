"""Pin fail-closed historical cross-site GMP certificate behaviour (Issue #6).

These disposable regressions intentionally do NOT authorize multi-site acceptance.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models.phase1 import Case, Certificate, Company, Site
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


@pytest.mark.parametrize("cross_site", [False, True])
def test_linked_certificate_requires_primary_site_until_coverage_is_reviewed(cross_site):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            company = Company(legal_name="Legacy source boundary")
            session.add(company)
            session.flush()
            primary = Site(company_id=company.id, site_name="Primary")
            other = Site(company_id=company.id, site_name="Other same-company Site")
            session.add_all([primary, other])
            session.flush()
            linked_case = Case(
                site_id=other.id if cross_site else primary.id,
                gxp_type="GMP",
            )
            session.add(linked_case)
            session.flush()
            cert = Certificate(
                site_id=primary.id, case_id=linked_case.id, certificate_type="GMP",
                latest_flag=False,
            )
            session.add(cert)
            session.flush()
            if cross_site:
                with pytest.raises(HTTPException) as exc:
                    CaseWorkflowService._validate_certificate_linked_case(session, cert)
                assert exc.value.status_code == 409
                assert "invalid linked Case" in str(exc.value.detail)
                # Historical latest_flag=False must not bypass the global read guard.
                with pytest.raises(HTTPException) as search_error:
                    CatalogReadService().search_facilities(session, gxp_type="GMP")
                assert search_error.value.status_code == 409
            else:
                assert CaseWorkflowService._validate_certificate_linked_case(session, cert).id == linked_case.id
    finally:
        engine.dispose()
