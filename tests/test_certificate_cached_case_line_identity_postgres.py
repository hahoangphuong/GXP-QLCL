"""Certificate identity validation must not trust cached Case/ProductionLine.

Both tests use one disposable PostgreSQL schema, two committed Sessions,
and DDK Current promotion as an actual caller of the shared GxP identity
owner. A previously valid linked Case or line is reparented after caching.
"""
from __future__ import annotations

from datetime import date
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion, Case, Certificate, Company, ProductionLine, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("changed_owner", ["case_site", "production_line_site"])
def test_ddk_promotion_rechecks_canonical_gxp_case_and_line_owner(changed_owner):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5432
    ):
        pytest.fail("Only loopback disposable gxp_qlcl_test may be mutated.")

    schema = "cert_case_line_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = writer = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Linked Case/Line refresh " + schema)
            setup.add(company)
            setup.flush()
            site_a = Site(company_id=company.id, site_name="Original GxP Site")
            site_b = Site(company_id=company.id, site_name="Reparented Site")
            setup.add_all([site_a, site_b])
            setup.flush()
            line = ProductionLine(
                site_id=site_a.id, code="LINE-A", effective_from=date(2026, 1, 1),
            )
            setup.add(line)
            setup.flush()
            case = Case(
                site_id=site_a.id, production_line_id=line.id, gxp_type="GMP",
                state=CaseState.AWAITING_CERTIFICATE_DECISION,
            )
            setup.add(case)
            setup.flush()
            cert = Certificate(
                site_id=site_a.id, case_id=case.id, production_line_id=line.id,
                certificate_type="GMP", issuance_basis="inspection_case",
                latest_flag=False,
            )
            ddk = BusinessEligibilityCertificate(
                company_id=company.id, site_id=site_a.id, latest_flag=False,
            )
            setup.add_all([cert, ddk])
            setup.flush()
            version = BusinessEligibilityVersion(
                business_eligibility_certificate_id=ddk.id,
                version_no=1, certificate_number="CI-CASE-LINE-DDK",
                issued_on=date(2026, 11, 12),
            )
            setup.add(version)
            setup.flush()
            setup.add(BusinessEligibilityCertificateLink(
                business_eligibility_version_id=version.id,
                certificate_id=cert.id, link_role="source_certificate",
            ))
            setup.commit()
            case_id, line_id, cert_id, ddk_id = case.id, line.id, cert.id, ddk.id
            original_site_id, target_site_id = site_a.id, site_b.id
            root_version = ddk.row_version

        contender = factory()
        cached_case = contender.get(Case, case_id)
        cached_line = contender.get(ProductionLine, line_id)
        cached_gxp = contender.get(Certificate, cert_id)
        assert cached_case.site_id == original_site_id
        assert cached_line.site_id == original_site_id
        assert cached_gxp.site_id == original_site_id

        writer = factory()
        owner_class, owner_id = (
            (Case, case_id) if changed_owner == "case_site"
            else (ProductionLine, line_id)
        )
        canonical_owner = writer.get(owner_class, owner_id)
        canonical_owner.site_id = target_site_id
        writer.commit()

        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().promote_business_eligibility_current(
                contender,
                business_eligibility_certificate_id=ddk_id,
                expected_version=root_version,
                reason="reject stale linked Case or canonical ProductionLine",
                user=build_authenticated_user("ci-gxp-line-canonical", "manager"),
            )
        assert denied.value.status_code == 409
        assert "invalid linked" in str(denied.value.detail).lower()
        contender.rollback()

        with factory() as verify:
            assert verify.get(owner_class, owner_id).site_id == target_site_id
            assert verify.get(Certificate, cert_id).site_id == original_site_id
            persisted = verify.get(BusinessEligibilityCertificate, ddk_id)
            assert persisted.latest_flag is False
            assert persisted.row_version == root_version
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        for session in (contender, writer):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
