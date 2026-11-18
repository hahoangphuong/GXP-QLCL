"""ĐĐK latest-version edit preserves link and submitted GxP graph drafts.

Synthetic SQLite; verifies pre-mutation SELECT-only admission.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, BusinessEligibilityCertificate, BusinessEligibilityVersion,
    BusinessEligibilityCertificateLink, Case, Certificate, Company, Site,
    ProductionLine,
)
from backend.app.services.workflow import CaseWorkflowService


USER = build_authenticated_user(
    "ddk-edit-links", "manager", permissions={"certificate.edit"},
)


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-edit-link-draft.sqlite').as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed Company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        line = ProductionLine(
            site_id=site.id, code="COMMITTED-LINE", effective_from=date(2020, 1, 1)
        )
        db.add(line)
        db.flush()
        case = Case(
            site_id=site.id, gxp_type="GMP", production_line_id=line.id,
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
        )
        db.add(case)
        db.flush()
        gxp = Certificate(
            site_id=site.id, case_id=case.id, production_line_id=line.id,
            certificate_type="GMP", issuance_basis="inspection_case",
            latest_flag=False,
        )
        db.add(gxp)
        db.flush()
        ddk = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, latest_flag=False,
        )
        db.add(ddk)
        db.flush()
        version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=ddk.id, version_no=1,
            certificate_number="COMMITTED-DDK", issued_on=date(2026, 11, 1),
        )
        db.add(version)
        db.flush()
        link = BusinessEligibilityCertificateLink(
            business_eligibility_version_id=version.id,
            certificate_id=gxp.id, link_role="source_certificate",
        )
        db.add(link)
        db.commit()
        ids = ddk.id, version.id, link.id, gxp.id, case.id, line.id, ddk.row_version
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "dirty_owner",
    ["existing_link", "pending_link", "linked_certificate", "linked_case", "linked_line"],
)
def test_ddk_edit_rejects_uncommitted_link_graph_without_autoflush(seeded, dirty_owner):
    engine, (ddk_id, version_id, link_id, gxp_id, case_id, line_id, token) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        link = db.get(BusinessEligibilityCertificateLink, link_id)
        gxp = db.get(Certificate, gxp_id)
        case = db.get(Case, case_id)
        line = db.get(ProductionLine, line_id)
        if dirty_owner == "existing_link":
            link.link_role = "supporting_certificate"
            tracked, attribute, draft = link, "link_role", "supporting_certificate"
        elif dirty_owner == "pending_link":
            pending_link = BusinessEligibilityCertificateLink(
                business_eligibility_version_id=version_id,
                certificate_id=gxp_id, link_role="source_certificate",
            )
            db.add(pending_link)
        elif dirty_owner == "linked_certificate":
            gxp.latest_flag = True
            tracked, attribute, draft = gxp, "latest_flag", True
        elif dirty_owner == "linked_case":
            case.state = CaseState.CANCELLED
            tracked, attribute, draft = case, "state", CaseState.CANCELLED
        else:
            line.code = "UNSAVED-LINE"
            tracked, attribute, draft = line, "code", "UNSAVED-LINE"
        unrelated = Company(legal_name="Pending operator Company")
        db.add(unrelated)
        sql, flushes = [], []

        def record_sql(_conn, _cursor, statement, _params, _context, _many):
            sql.append(statement.lstrip().split(None, 1)[0].upper())

        def forbid_flush(*_args):
            flushes.append(True)
            raise AssertionError("DDK link edit autoflushed operator drafts")

        event.listen(engine, "before_cursor_execute", record_sql)
        event.listen(db, "before_flush", forbid_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().upsert_business_eligibility_latest_version(
                    db, business_eligibility_certificate_id=ddk_id,
                    expected_version=token, certificate_number="DDK-MUTATION",
                    issued_on=date(2026, 11, 2), expires_on=None,
                    professional_responsible_person_name=None,
                    notes="Submitted replacement",
                    linked_certificates=[{"certificate_id":gxp_id, "link_role":"source_certificate"}],
                    reason="Synthetic draft admission", user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", record_sql)
            event.remove(db, "before_flush", forbid_flush)
        assert exc.value.status_code == 409
        assert "uncommitted changes" in str(exc.value.detail)
        assert set(sql) <= {"SELECT"} and not flushes
        assert unrelated in db.new
        if dirty_owner == "pending_link":
            assert pending_link in db.new
        else:
            assert tracked in db.dirty and getattr(tracked, attribute) == draft
        db.rollback()

    with Session(engine) as check:
        assert check.get(BusinessEligibilityVersion, version_id).certificate_number == "COMMITTED-DDK"
        assert check.get(BusinessEligibilityCertificateLink, link_id).link_role == "source_certificate"
        assert check.get(Certificate, gxp_id).latest_flag is False
        assert check.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert check.get(ProductionLine, line_id).code == "COMMITTED-LINE"
        assert check.scalar(select(func.count(BusinessEligibilityCertificateLink.id))) == 1
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
