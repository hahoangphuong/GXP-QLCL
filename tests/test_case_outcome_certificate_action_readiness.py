"""Operator Case readiness uses existing inspection-outcome and Certificate owners.

Tests cover actual mutation parity, per-certificate UUID/token containment,
permission/terminal gates and typed API serialization. No document issuance.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Certificate, CertificateVersion, Company, InspectionOutcome, Site,
)
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService
from backend.app.services.workflow import CaseWorkflowService

CATALOG = CatalogReadService()
WORKFLOW = CaseWorkflowService()


@pytest.fixture
def case_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'case-outcome-certificate-actions.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Actions test company")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Actions test facility")
        session.add(site)
        session.flush()
        a = Case(site_id=site.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        b = Case(site_id=site.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        session.add_all([a, b])
        session.commit()
        ids = (a.id, b.id, site.id)
    try:
        yield engine, *ids
    finally:
        engine.dispose()


def _user(*permissions):
    return build_authenticated_user("case-actions-operator", "reader", permissions=list(permissions))


def _workspace(session, case_id, user):
    return CaseWorkspaceRead.model_validate(CATALOG.get_case_workspace(session, case_id=case_id, user=user))


def _certificate(session, case_id, site_id, *, number="TEST-GMP", complete=True):
    root = Certificate(
        case_id=case_id, site_id=site_id, certificate_type="GMP",
        issuance_basis="inspection_case", latest_flag=False,
    )
    session.add(root)
    session.flush()
    version = CertificateVersion(
        certificate_id=root.id, version_no=1, is_latest_version=True,
        certificate_number=number,
        issue_date=date(2026, 11, 13) if complete else None,
        expiry_date=date(2029, 11, 13) if complete else None,
    )
    session.add(version)
    session.commit()
    return root.id, version.id, root.row_version


def _actions(workspace, certificate_id):
    details = {c.certificate_id: c for c in workspace.linked_gxp_certificates}
    assert certificate_id in details
    return {action.action_key: action for action in details[certificate_id].action_readiness}


def test_outcome_readiness_reports_initialization_permission_and_canonical_version(case_db):
    engine, case_id, _, _ = case_db
    with Session(engine) as session:
        admin = _user("inspection.edit")
        initial = _workspace(session, case_id, admin).inspection.outcome_edit_readiness
        assert initial is not None
        assert (initial.action_key, initial.available, initial.expected_version) == (
            "edit_inspection_outcome", True, None,
        )
        denied = _workspace(session, case_id, _user("document.read")).inspection.outcome_edit_readiness
        assert denied is not None
        assert denied.available is False
        assert denied.reason_code == "missing_permission"
        assert denied.required_permissions == ["inspection.edit"]

        # The mutation consumes precisely the outcome child token published
        # by this read model. Compatibility period/source ownership remains
        # protected by the existing endpoint.
        saved = WORKFLOW.upsert_inspection_outcome(
            session, case_id=case_id, expected_version=initial.expected_version,
            inspected_on=None, inspected_to_on=None, decision_reference=None,
            bbkt_reference=None, outcome_result="Ghi nhận kết quả", reason="synthetic",
            fields_set={"outcome_result"}, user=admin,
        )
        session.commit()
    with Session(engine) as verify:
        readiness = _workspace(verify, case_id, _user("inspection.edit")).inspection.outcome_edit_readiness
        assert readiness is not None
        assert readiness.expected_version == saved["row_version"]
        assert readiness.available is True
        assert verify.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case_id)).outcome_result == "Ghi nhận kết quả"


@pytest.mark.parametrize("state", [CaseState.CLOSED, CaseState.CANCELLED])
def test_terminal_case_blocks_outcome_edit_projection(case_db, state):
    engine, case_id, _, _ = case_db
    with Session(engine) as session:
        session.get(Case, case_id).state = state
        session.commit()
    with Session(engine) as verify:
        action = _workspace(verify, case_id, _user("inspection.edit")).inspection.outcome_edit_readiness
        assert action is not None
        assert action.available is False
        assert action.reason_code == "terminal_case"
        assert action.expected_version is None
        assert verify.scalar(select(func.count(AuditEvent.id))) == 0


def test_linked_certificate_readiness_is_per_root_and_permission_scoped(case_db):
    engine, case_id, other_case_id, site_id = case_db
    with Session(engine) as session:
        candidate_id, version_id, token = _certificate(session, case_id, site_id, number="GMP-001")
        other_id, _, _ = _certificate(session, other_case_id, site_id, number="GMP-OTHER")
        reader = _workspace(session, case_id, _user("document.read"))
        assert [c.certificate_id for c in reader.linked_gxp_certificates] == [candidate_id]
        reader_actions = _actions(reader, candidate_id)
        assert reader_actions["promote_current"].available is False
        assert reader_actions["promote_current"].reason_code == "missing_permission"
        assert reader_actions["edit_latest_version"].available is False

        promoter = _workspace(session, case_id, _user("certificate.approve"))
        promoted_actions = _actions(promoter, candidate_id)
        assert promoted_actions["promote_current"].available is True
        assert promoted_actions["promote_current"].expected_version == token
        assert promoted_actions["promote_current"].required_permissions == ["certificate.approve"]
        assert promoted_actions["edit_latest_version"].available is False

        editor = _workspace(session, case_id, _user("certificate.edit"))
        editor_actions = _actions(editor, candidate_id)
        assert editor_actions["edit_latest_version"].available is True
        assert editor_actions["promote_current"].available is False
        assert all(a.expected_version == token for a in editor_actions.values())
        assert version_id != candidate_id
        assert other_id not in {c.certificate_id for c in editor.linked_gxp_certificates}
        assert session.scalar(select(func.count(AuditEvent.id))) == 0


def test_incomplete_certificate_never_advertises_promotion(case_db):
    engine, case_id, _, site_id = case_db
    with Session(engine) as session:
        candidate, _, _ = _certificate(session, case_id, site_id, number="GMP-INCOMPLETE", complete=False)
        actions = _actions(_workspace(session, case_id, _user("certificate.approve")), candidate)
        assert actions["promote_current"].available is False
        assert actions["promote_current"].reason_code == "certificate_data_incomplete"
        assert session.scalar(select(func.count(AuditEvent.id))) == 0


def test_certificate_promotion_readiness_tracks_real_mutation_and_terminal_state(case_db):
    engine, case_id, other_case_id, site_id = case_db
    with Session(engine) as session:
        candidate, _, _ = _certificate(session, case_id, site_id, number="GMP-CURRENT")
        admin = _user("certificate.approve")
        readiness = _actions(_workspace(session, case_id, admin), candidate)["promote_current"]
        assert readiness.available
        assert readiness.expected_version is not None
        result = WORKFLOW.promote_certificate_current(
            session, certificate_id=candidate,
            expected_version=readiness.expected_version, reason="synthetic promote",
            user=admin,
        )
        session.commit()
        assert result["latest_flag"] is True
    with Session(engine) as verify:
        promoted = _actions(_workspace(verify, case_id, admin), candidate)["promote_current"]
        assert promoted.available is False
        assert promoted.reason_code == "already_current"
        assert promoted.expected_version == result["row_version"]
        assert verify.get(Certificate, candidate).latest_flag is True

    # A new, unpromoted Case certificate cannot be promoted if its parent
    # Case is closed: the service's case-state gate is not bypassed by the UI.
    with Session(engine) as session:
        other_candidate, _, _ = _certificate(session, other_case_id, site_id, number="GMP-LATER")
        session.get(Case, other_case_id).state = CaseState.CLOSED
        session.commit()
    with Session(engine) as verify:
        blocked = _actions(_workspace(verify, other_case_id, admin), other_candidate)["promote_current"]
        assert blocked.available is False
        assert blocked.reason_code == "case_state_not_eligible"
