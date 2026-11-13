"""Case registration/assessment/plan readiness is owned by the backend.

The read-only projection mirrors existing route permissions, nonterminal Case
mutation gates, and child-specific optimistic versions. No frontend or new
mutation endpoint is required.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseApplication, CaseAssessment, Company, InspectionPlan, Site,
)
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService


ACTIONS = {
    "edit_case_application": "case.edit",
    "edit_case_assessment": "case.edit",
    "edit_inspection_plan": "inspection.edit",
}
CATALOG = CatalogReadService()


@pytest.fixture
def case_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'case-stage-readiness.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Synthetic registration company")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic registration facility")
        session.add(site)
        session.flush()
        row = Case(site_id=site.id, gxp_type="GMP", state=CaseState.APPLICATION_RECEIVED)
        session.add(row)
        session.commit()
        case_id = row.id
    try:
        yield engine, case_id
    finally:
        engine.dispose()


def _user(*permissions):
    return build_authenticated_user(
        "stage-readiness-synthetic", "admin", permissions=list(permissions),
    )


def _stage_actions(session, case_id, user):
    workspace = CATALOG.get_case_workspace(session, case_id=case_id, user=user)
    # Verify fields survive the actual API response schema; not just an
    # internal Python dictionary that FastAPI might silently drop.
    serialized = CaseWorkspaceRead(**workspace).model_dump()
    actions = serialized["stage_edit_actions"]
    assert set(item["action_key"] for item in actions) == set(ACTIONS)
    assert len(actions) == 3
    return {item["action_key"]: item for item in actions}


def test_stage_edit_readiness_allows_initialization_and_reports_permission(case_db):
    engine, case_id = case_db
    with Session(engine) as session:
        all_actions = _stage_actions(session, case_id, _user("case.edit", "inspection.edit"))
        for key, action in all_actions.items():
            assert action["available"] is True
            assert action["reason_code"] is None
            assert action["expected_version"] is None
            assert action["required_permissions"] == [ACTIONS[key]]

        case_only = _stage_actions(session, case_id, _user("case.edit"))
        assert case_only["edit_case_application"]["available"] is True
        assert case_only["edit_case_assessment"]["available"] is True
        assert case_only["edit_inspection_plan"]["available"] is False
        assert case_only["edit_inspection_plan"]["reason_code"] == "missing_permission"

        inspection_only = _stage_actions(session, case_id, _user("inspection.edit"))
        assert inspection_only["edit_inspection_plan"]["available"] is True
        for key in ("edit_case_application", "edit_case_assessment"):
            assert inspection_only[key]["reason_code"] == "missing_permission"

        assert _stage_actions(session, case_id, _user()) == {
            key: {
                **action, "available": False, "reason_code": "missing_permission",
            }
            for key, action in all_actions.items()
        }
        assert session.scalar(select(func.count(AuditEvent.id))) == 0


def test_stage_readiness_versions_track_canonical_child_editors(case_db):
    engine, case_id = case_db
    with Session(engine) as session:
        session.add_all([
            CaseApplication(case_id=case_id, dossier_code="REG-TEST"),
            CaseAssessment(case_id=case_id, assessment_result="Reviewed"),
            InspectionPlan(case_id=case_id, planning_sheet_name="KHKT-TEST"),
        ])
        session.commit()
        children = (
            session.scalar(select(CaseApplication).where(CaseApplication.case_id == case_id)),
            session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == case_id)),
            session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_id)),
        )
        ids = {key: child.row_version for key, child in zip(ACTIONS, children)}
        actions = _stage_actions(session, case_id, _user("case.edit", "inspection.edit"))
        assert {key: action["expected_version"] for key, action in actions.items()} == ids
        # The existing application mutation consumes exactly the stage token
        # advertised by this read contract; no cross-stage Case version.
        updated = CaseWorkflowService().upsert_case_application(
            session, case_id=case_id, expected_version=actions["edit_case_application"]["expected_version"],
            submitted_on=datetime(2026, 11, 13, 9, 0), dossier_code="REG-UPDATED",
            dossier_reference=None, applicant_name="Synthetic", reason="Synthetic correction",
            user=_user("case.edit"), fields_set={"submitted_on", "dossier_code", "applicant_name"},
        )
        session.commit()
        assert updated["row_version"] > ids["edit_case_application"]
    with Session(engine) as verify:
        actions = _stage_actions(verify, case_id, _user("case.edit", "inspection.edit"))
        assert actions["edit_case_application"]["expected_version"] == updated["row_version"]
        assert actions["edit_case_assessment"]["expected_version"] == ids["edit_case_assessment"]
        assert actions["edit_inspection_plan"]["expected_version"] == ids["edit_inspection_plan"]


@pytest.mark.parametrize("terminal", [CaseState.CLOSED, CaseState.CANCELLED])
def test_stage_readiness_blocks_terminal_case_without_mutations(case_db, terminal):
    engine, case_id = case_db
    with Session(engine) as writer:
        row = writer.get(Case, case_id)
        row.state = terminal
        writer.commit()
    with Session(engine) as session:
        actions = _stage_actions(session, case_id, _user("case.edit", "inspection.edit"))
        assert all(not action["available"] and action["reason_code"] == "terminal_case" for action in actions.values())
        assert all(action["expected_version"] is None for action in actions.values())
        assert session.scalar(select(func.count(AuditEvent.id))) == 0
