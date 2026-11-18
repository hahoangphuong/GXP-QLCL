"""DDK current promotion cannot overwrite dirty linked GxP evidence graph.

Synthetic SQLite with one persisted DDK -> GxP Certificate link.
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

USER = build_authenticated_user("ddk-linked-graph-draft", "manager", permissions={"certificate.approve"})


@pytest.fixture
def seeded(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ddk-linked-graph-draft.sqlite').as_posix()}", future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Committed owner")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Committed Site")
        db.add(site)
        db.flush()
        gxp_case = Case(
            site_id=site.id, gxp_type="GMP", scope_code=None,
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
        )
        db.add(gxp_case)
        db.flush()
        line = ProductionLine(site_id=site.id, code="GMP-LINE", effective_from=date(2020, 1, 1))
        db.add(line)
        db.flush()
        gxp = Certificate(
            site_id=site.id, case_id=gxp_case.id, production_line_id=line.id,
            certificate_type="GMP", issuance_basis="inspection_case", latest_flag=False,
        )
        db.add(gxp)
        db.flush()
        candidate = BusinessEligibilityCertificate(
            site_id=site.id, company_id=company.id, latest_flag=False,
        )
        db.add(candidate)
        db.flush()
        version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=candidate.id, version_no=1,
            certificate_number="DDK-CANDIDATE", issued_on=date(2026, 11, 2),
        )
        db.add(version)
        db.flush()
        link = BusinessEligibilityCertificateLink(
            business_eligibility_version_id=version.id, certificate_id=gxp.id,
            link_role="source_certificate",
        )
        db.add(link)
        db.commit()
        ids = candidate.id, candidate.row_version, gxp.id, gxp_case.id, line.id, link.id
    try:
        yield engine, ids
    finally:
        engine.dispose()


@pytest.mark.parametrize("dirty_owner", ["link", "gxp_certificate", "gxp_case", "production_line"])
def test_ddk_promote_preserves_dirty_linked_graph_draft(seeded, dirty_owner):
    engine, (candidate_id, token, gxp_id, case_id, line_id, link_id) = seeded
    with Session(engine, autoflush=True, expire_on_commit=False) as db:
        link = db.get(BusinessEligibilityCertificateLink, link_id)
        certificate = db.get(Certificate, gxp_id)
        case = db.get(Case, case_id)
        line = db.get(ProductionLine, line_id)
        if dirty_owner == "link":
            link.link_role = "supporting_certificate"
            tracked, attr, draft = link, "link_role", "supporting_certificate"
        elif dirty_owner == "gxp_certificate":
            certificate.latest_flag = True
            tracked, attr, draft = certificate, "latest_flag", True
        elif dirty_owner == "gxp_case":
            case.state = CaseState.CANCELLED
            tracked, attr, draft = case, "state", CaseState.CANCELLED
        else:
            line.code = "UNSAVED-GMP-LINE"
            tracked, attr, draft = line, "code", "UNSAVED-GMP-LINE"
        pending = Company(legal_name="Unrelated pending Company")
        db.add(pending)
        statements, flushes = [], []

        def observe(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        def reject_flush(*_args):
            flushes.append(True)
            raise AssertionError("DDK linked-graph preflight must not autoflush operator drafts")

        event.listen(engine, "before_cursor_execute", observe)
        event.listen(db, "before_flush", reject_flush)
        try:
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().promote_business_eligibility_current(
                    db, business_eligibility_certificate_id=candidate_id,
                    expected_version=token, reason="Synthetic linked graph draft",
                    user=USER,
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            event.remove(db, "before_flush", reject_flush)
        assert exc.value.status_code == 409
        assert "uncommitted changes" in str(exc.value.detail)
        assert set(statements) <= {"SELECT"} and not flushes
        assert tracked in db.dirty and getattr(tracked, attr) == draft
        assert pending in db.new
        db.rollback()

    with Session(engine) as check:
        assert check.get(BusinessEligibilityCertificate, candidate_id).latest_flag is False
        assert check.get(BusinessEligibilityCertificateLink, link_id).link_role == "source_certificate"
        assert check.get(Certificate, gxp_id).latest_flag is False
        assert check.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert check.get(ProductionLine, line_id).code == "GMP-LINE"
        assert check.scalar(select(func.count(AuditEvent.id))) == 0
        assert check.scalar(select(func.count(Company.id))) == 1
