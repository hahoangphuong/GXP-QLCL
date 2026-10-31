"""Pin fail-closed historical cross-site GMP certificate behaviour (Issue #6).

These disposable regressions intentionally do NOT authorize multi-site acceptance.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Certificate, Company, Site
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


@pytest.mark.parametrize(
    ("case_site_relation", "case_gxp", "expected_valid"),
    [
        ("primary", "GMP", True),
        ("same_company", "GMP", False),
        ("different_company", "GMP", False),
        ("primary", "GLP", False),
        ("same_company", "GLP", False),
    ],
)
def test_linked_certificate_requires_evidenced_site_and_gxp(
    case_site_relation, case_gxp, expected_valid
):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            company = Company(legal_name="Legacy source boundary")
            foreign_company = Company(legal_name="Unrelated owner")
            session.add_all([company, foreign_company])
            session.flush()
            primary = Site(company_id=company.id, site_name="Primary")
            additional = Site(company_id=company.id, site_name="Other same-company Site")
            unrelated = Site(company_id=foreign_company.id, site_name="Foreign Site")
            session.add_all([primary, additional, unrelated])
            session.flush()
            case_site = {
                "primary": primary,
                "same_company": additional,
                "different_company": unrelated,
            }[case_site_relation]
            linked_case = Case(
                site_id=case_site.id, gxp_type=case_gxp, state=CaseState.DRAFT,
            )
            session.add(linked_case)
            session.flush()
            cert = Certificate(
                site_id=primary.id, case_id=linked_case.id, certificate_type="GMP",
                latest_flag=False,
            )
            session.add(cert)
            session.flush()
            if not expected_valid:
                with pytest.raises(HTTPException) as exc:
                    CaseWorkflowService._validate_certificate_linked_case(session, cert)
                assert exc.value.status_code == 409
                assert "invalid linked Case" in str(exc.value.detail)
                # Even historical records cannot evade unscoped search validation.
                with pytest.raises(HTTPException) as search_error:
                    CatalogReadService().search_facilities(session, gxp_type="GMP")
                assert search_error.value.status_code == 409
            else:
                assert CaseWorkflowService._validate_certificate_linked_case(session, cert).id == linked_case.id
    finally:
        engine.dispose()
