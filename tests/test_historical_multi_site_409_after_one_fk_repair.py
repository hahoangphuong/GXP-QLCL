"""A correct historical Case FK does not legalize other cross-Site GMP grants.

All changes in this test are to a disposable SQLite fixture, never to a VM,
PostgreSQL rehearsal database or a source snapshot. The historical IDs are
regression-fixture identifiers, NOT general-domain hardcoded exceptions.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case, Certificate, CertificateVersion, Company, Site,
)
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


def _expect_global_409(session: Session) -> None:
    service = CatalogReadService()
    for filter_gxp in ("GMP", "GLP", None):
        with pytest.raises(HTTPException, match="invalid linked Case") as error:
            service.search_facilities(
                session,
                q=None,
                gxp_type=filter_gxp,
                province=None,
                case_states=None,
                change_request_states=None,
                certificate_state=None,
                certificate_expiring_within_days=None,
                offset=0,
                limit=100,
            )
        assert error.value.status_code == 409


def test_repairing_legacy_gmp_376_does_not_hide_multisite_1037_1180(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'isolated-gmp-legacy.sqlite'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        unrelated_company = Company(legal_name="Unrelated manufacturing company")
        source_company = Company(legal_name="Single-site historical GMP company")
        domesco_company = Company(legal_name="Historical two-site company")
        session.add_all([unrelated_company, source_company, domesco_company])
        session.flush()

        bad_case_site = Site(
            legacy_site_id=72, company_id=unrelated_company.id, site_name="Wrong imported inspection",
        )
        certified_site = Site(
            legacy_site_id=73, company_id=source_company.id, site_name="Certificate 376 site",
        )
        domesco_primary = Site(
            legacy_site_id=46, company_id=domesco_company.id, site_name="Historical site 1",
        )
        domesco_case_anchor = Site(
            legacy_site_id=298, company_id=domesco_company.id, site_name="Historical site 2",
        )
        session.add_all([bad_case_site, certified_site, domesco_primary, domesco_case_anchor])
        session.flush()

        case378 = Case(
            legacy_inspection_id=378, site_id=bad_case_site.id,
            gxp_type="GMP", state=CaseState.CERTIFIED,
        )
        case380 = Case(
            legacy_inspection_id=380, site_id=certified_site.id,
            gxp_type="GMP", state=CaseState.CERTIFIED,
        )
        case1023 = Case(
            legacy_inspection_id=1023, site_id=domesco_case_anchor.id,
            gxp_type="GMP", state=CaseState.CERTIFIED,
        )
        session.add_all([case378, case380, case1023])
        session.flush()

        cert376 = Certificate(
            legacy_certificate_id=376, site_id=certified_site.id,
            case_id=case378.id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        cert1037 = Certificate(
            legacy_certificate_id=1037, site_id=domesco_primary.id,
            case_id=case1023.id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        cert1180 = Certificate(
            legacy_certificate_id=1180, site_id=domesco_primary.id,
            case_id=case1023.id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=True,
        )
        session.add_all([cert376, cert1037, cert1180])
        session.flush()
        for cert, number, issued_on in (
            (cert376, "119/GCN-QLD", date(2018, 3, 12)),
            (cert1037, "200/GCN-QLD", date(2022, 4, 20)),
            (cert1180, "314/GCN-QLD", date(2023, 5, 15)),
        ):
            session.add(CertificateVersion(
                certificate_id=cert.id, version_no=1,
                certificate_number=number, issue_date=issued_on,
                is_latest_version=True,
            ))
        session.commit()
        cert376_id = cert376.id
        cert1037_id = cert1037.id
        cert1180_id = cert1180.id
        case380_id = case380.id
        original_imported_fk = case378.id

    with Session(engine) as session:
        _expect_global_409(session)

        # Simulate the separately planned ONE FK correction on disposable
        # SQLite only. Never reassign Case 1023 or merge Domesco Sites.
        cert376 = session.get(Certificate, cert376_id)
        assert cert376.case_id == original_imported_fk
        cert376.case_id = case380_id
        session.flush()

        # SQL and Python validators must now agree on 376, and still reject
        # each independently unadjudicated Domesco historical cross-Site link.
        valid_sql_ids = set(session.scalars(
            select(Certificate.id).where(
                CaseWorkflowService._certificate_valid_linked_case_sql()
            )
        ))
        assert cert376_id in valid_sql_ids
        assert cert1037_id not in valid_sql_ids
        assert cert1180_id not in valid_sql_ids

        assert CaseWorkflowService._validate_certificate_linked_case(
            session, cert376
        ).id == case380_id

        for invalid_id in (cert1037_id, cert1180_id):
            invalid = session.get(Certificate, invalid_id)
            with pytest.raises(HTTPException, match="invalid linked Case") as error:
                CaseWorkflowService._validate_certificate_linked_case(session, invalid)
            assert error.value.status_code == 409

        # Even when 376 is corrected, both GMP and unrelated GLP filtered
        # searches must fail closed rather than suppress legacy anomalies.
        _expect_global_409(session)

        # No source FK, site anchor, document or historical scope is
        # changed by this regression: the hypothetical rebind rolls back.
        session.rollback()

    engine.dispose()
