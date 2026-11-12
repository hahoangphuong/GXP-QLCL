"""Reassessment creation must reject a stale cached ProductionLine owner/code.

PostgreSQL only, synthetic fixtures. The writer commits an independent line
change after the creator Session cached it. The actual Case create mutation
must read the canonical row and reject without a new Case or audit.
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
    AppUser, AuditEvent, Case, Company, ProductionLine, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("change", ["reparent_site", "rename_code"])
def test_reassessment_create_rejects_stale_cached_production_line(change):
    url = make_url(DATABASE_URL)
    if (
        url.get_backend_name() != "postgresql"
        or url.database != "gxp_qlcl_test"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5432
    ):
        pytest.fail("Only disposable loopback gxp_qlcl_test may be mutated.")
    schema = "reassessment_line_refresh_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = creator = editor = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Synthetic reassessment line owner " + schema)
            setup.add(company)
            setup.add(AppUser(username="synthetic-line-reassessment", display_name="Line Reassessment", is_active=True))
            setup.flush()
            site_a = Site(company_id=company.id, site_name="Original line site")
            site_b = Site(company_id=company.id, site_name="Reparented line site")
            setup.add_all([site_a, site_b])
            setup.flush()
            line = ProductionLine(site_id=site_a.id, code="LINE-1", effective_from=date(2026, 1, 1))
            setup.add(line)
            setup.flush()
            source = Case(
                site_id=site_a.id, production_line_id=line.id, scope_code="LINE-1",
                gxp_type="GMP", state=CaseState.CERTIFIED,
            )
            setup.add(source)
            setup.commit()
            site_a_id, site_b_id, line_id, source_id = site_a.id, site_b.id, line.id, source.id

        # Strong reference deliberately retains the obsolete identity-map row.
        creator = factory()
        cached_line = creator.get(ProductionLine, line_id)
        assert cached_line.site_id == site_a_id
        assert cached_line.code == "LINE-1"

        editor = factory()
        changed_line = editor.get(ProductionLine, line_id)
        if change == "reparent_site":
            changed_line.site_id = site_b_id
        else:
            changed_line.code = "LINE-2"
        editor.commit()

        # Readiness and actual write must agree on canonical Site/code,
        # even though this Session still holds the old ProductionLine row.
        readiness = CaseWorkflowService().get_create_reassessment_case_action_readiness(
            creator,
            site_id=site_a_id,
            gxp_type="GMP",
            line_code="LINE-1",
            production_line_id=line_id,
            user=build_authenticated_user("synthetic-line-reassessment", "manager", permissions=("case.edit",)),
        )
        assert readiness["readiness_status"] == "unavailable"
        assert "ProductionLine" in readiness["detail"]

        with pytest.raises(HTTPException) as denied:
            CaseWorkflowService().create_inspection_case(
                creator,
                site_id=site_a_id,
                gxp_type="GMP",
                line_code="LINE-1",
                production_line_id=line_id,
                applicable_standard=None,
                reason="stale canonical line regression",
                source_case_id=None,
                user=build_authenticated_user("synthetic-line-reassessment", "manager", permissions=("case.edit",)),
            )
        assert denied.value.status_code == 422
        assert "ProductionLine" in str(denied.value.detail)
        creator.rollback()

        with factory() as verify:
            assert verify.scalar(select(func.count(Case.id))) == 1
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            original = verify.get(Case, source_id)
            assert original.site_id == site_a_id
            assert original.state == CaseState.CERTIFIED
            canonical_line = verify.get(ProductionLine, line_id)
            assert canonical_line.site_id == (site_b_id if change == "reparent_site" else site_a_id)
            assert canonical_line.code == ("LINE-2" if change == "rename_code" else "LINE-1")
    finally:
        for session in (creator, editor):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
