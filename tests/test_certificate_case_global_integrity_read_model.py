"""Regression: history is not a license to hide an invalid Certificate -> Case."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Certificate, CertificateVersion, Company, Site
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


def test_historical_cross_site_certificate_blocks_global_search_and_own_site_workspace(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'certificate-historical-integrity.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Shared company")
        session.add(company)
        session.flush()

        site_a = Site(company_id=company.id, site_name="Manufacturing Site A")
        site_b = Site(company_id=company.id, site_name="Manufacturing Site B")
        session.add_all([site_a, site_b])
        session.flush()

        origin_case = Case(site_id=site_b.id, gxp_type="GMP", state=CaseState.CERTIFIED)
        session.add(origin_case)
        session.flush()

        historical_invalid = Certificate(
            site_id=site_a.id,
            case_id=origin_case.id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            latest_flag=False,
        )
        unrelated_administrative = Certificate(
            site_id=site_a.id,
            case_id=None,
            certificate_type="GLP",
            issuance_basis="administrative_no_inspection",
            latest_flag=True,
        )
        session.add_all([historical_invalid, unrelated_administrative])
        session.flush()
        session.add_all([
            CertificateVersion(
                certificate_id=historical_invalid.id,
                version_no=1,
                certificate_number="HISTORICAL-INVALID",
                issue_date=date(2022, 4, 20),
                is_latest_version=True,
            ),
            CertificateVersion(
                certificate_id=unrelated_administrative.id,
                version_no=1,
                certificate_number="ADMINISTRATIVE-VALID",
                issue_date=date(2024, 1, 1),
                is_latest_version=True,
            ),
        ])
        session.commit()
        site_a_id, site_b_id = site_a.id, site_b.id
        historical_id, administrative_id = historical_invalid.id, unrelated_administrative.id

    catalog = CatalogReadService()
    with Session(engine) as session:
        # Global validation must precede filtering/pagination/current-only projection.
        for gxp_type in ("GMP", "GLP", None):
            with pytest.raises(HTTPException, match="invalid linked Case") as error:
                catalog.search_facilities(
                    session,
                    q=None,
                    gxp_type=gxp_type,
                    province=None,
                    case_states=None,
                    change_request_states=None,
                    certificate_state=None,
                    certificate_expiring_within_days=None,
                    offset=0,
                    limit=1,
                )
            assert error.value.status_code == 409

        with pytest.raises(HTTPException, match="invalid linked Case") as error:
            catalog.get_facility_workspace(
                session,
                site_id=site_a_id,
                gxp_type="GLP",
                line_code=None,
            )
        assert error.value.status_code == 409

        with pytest.raises(HTTPException, match="invalid linked Case") as error:
            catalog.get_gxp_certificate_detail(session, certificate_id=historical_id)
        assert error.value.status_code == 409

        # Validation ownership is site-scoped for workspace reads, global for
        # search. A bad Site A certificate does not contaminate Site B's read.
        unaffected = catalog.get_facility_workspace(
            session,
            site_id=site_b_id,
            gxp_type="GMP",
            line_code=None,
        )
        assert unaffected["summary"]["site_id"] == site_b_id

        # Administrative-no-Case certificates are legitimate; never
        # reinterpret the invalid historical certificate as administrative.
        administrative = session.get(Certificate, administrative_id)
        assert administrative is not None
        assert CaseWorkflowService._validate_certificate_linked_case(session, administrative) is None

        # SQL predicates used by workflow must also reject the bad link.
        valid_ids = set(session.scalars(
            select(Certificate.id).where(CaseWorkflowService._certificate_valid_linked_case_sql())
        ))
        assert administrative_id in valid_ids
        assert historical_id not in valid_ids
