"""PostgreSQL terminal-state guard for mutable Inspection Period and Team.

Read-committed transaction B holds a nonterminal Case in its identity map.
Transaction A closes that Case and commits. B must revalidate against the
current authoritative Case before replacing period segments or team members.
"""
from __future__ import annotations

import os
from datetime import date
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
    AuditEvent, Case, Company, InspectionOutcome,
    InspectionPeriodSegment, InspectionTeam, InspectionTeamMember, Person, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)


@pytest.mark.parametrize("kind", ["period", "team"])
def test_inspection_child_write_rechecks_terminal_case_owner(kind):
    if make_url(DATABASE_URL).database != "gxp_qlcl_test":
        pytest.fail("Disposable gxp_qlcl_test required; no mutations performed.")
    schema = "inspection_child_terminal_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = contender = closing = None
    created_schema = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created_schema = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}, future=True,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
        with factory() as setup:
            company = Company(legal_name="Synthetic terminal guard " + schema)
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic inspected site")
            setup.add(site)
            setup.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            setup.add(case)
            setup.flush()
            person = Person(full_name="Synthetic Inspector")
            setup.add(person)
            outcome = InspectionOutcome(case_id=case.id, inspection_period_state="KNOWN")
            setup.add(outcome)
            setup.commit()
            case_id, person_id = case.id, person.id
            outcome_version = outcome.row_version

        user = build_authenticated_user("synthetic-inspection-editor", "manager")
        service = CaseWorkflowService()
        contender = factory()
        old = contender.get(Case, case_id)
        assert old.state == CaseState.INSPECTION_COMPLETED
        closing = factory()
        terminal = closing.get(Case, case_id)
        terminal.state = CaseState.CLOSED
        closing.commit()

        def mutate():
            if kind == "period":
                return service.upsert_inspection_period_segments(
                    contender, case_id=case_id,
                    expected_version=outcome_version,
                    segments=[{
                        "ordinal": 1, "started_on": date(2026, 10, 1),
                        "ended_on": date(2026, 10, 2),
                    }],
                    reason="synthetic stale state", user=user,
                )
            return service.upsert_inspection_team(
                contender, case_id=case_id, expected_version=None,
                members=[{
                    "person_id": person_id,
                    "inspector_profile_id": None,
                    "identity_kind": None,
                    "role_code": "LEADER",
                    "role_label": "Trưởng đoàn",
                    "sort_order": 1,
                }],
                reason="synthetic stale state", user=user,
            )

        with pytest.raises(HTTPException) as error:
            mutate()
        assert error.value.status_code == 409
        contender.rollback()

        with factory() as verify:
            assert verify.get(Case, case_id).state == CaseState.CLOSED
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
            assert verify.scalar(select(func.count(InspectionPeriodSegment.id))) == 0
            assert verify.scalar(select(func.count(InspectionTeam.id))) == 0
            assert verify.scalar(select(func.count(InspectionTeamMember.id))) == 0
            assert verify.scalar(select(InspectionOutcome.row_version).where(
                InspectionOutcome.case_id == case_id,
            )) == outcome_version
    finally:
        for session in (contender, closing):
            if session is not None:
                session.rollback()
                session.close()
        if engine is not None:
            engine.dispose()
        if created_schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
