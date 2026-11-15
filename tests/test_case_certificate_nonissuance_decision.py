"""Synthetic Case decision regression: explicit no-issuance fact is not inferred."""
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session

from backend.app.api.routers.workflow import register_workflow_routes
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseCertificateNonissuanceDecision, Certificate,
    Company, InspectionOutcome, Site, CapaCycle,
)
from backend.app.services.workflow import CaseWorkflowService


@pytest.fixture
def scenario():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Synthetic decision company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Synthetic decision site")
        db.add(site)
        db.flush()
        first = Case(site_id=site.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        other = Case(site_id=site.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION)
        db.add_all([first, other])
        db.flush()
        db.add_all([
            InspectionOutcome(case_id=first.id, final_evaluation="Recorded final assessment"),
            InspectionOutcome(case_id=other.id, final_evaluation="Recorded other assessment"),
        ])
        ids = (first.id, other.id, site.id)
        db.commit()
    try:
        yield engine, ids
    finally:
        engine.dispose()


def _actor():
    return build_authenticated_user("decision-operator", permissions={"certificate.approve", "certificate.issue"})


def _record(db, case_id, expected=1, ref="DEC-001"):
    return CaseWorkflowService().record_case_nonissuance_decision(
        db, case_id=case_id, expected_case_version=expected,
        decided_on=date(2026, 11, 13), decision_reference=ref,
        explanation="A documented, explicit non-issuance reason",
        reason="Synthetic test", user=_actor(),
    )



@pytest.mark.parametrize("operation,required_permission,kwargs", [
    (
        "upsert_certificate_latest_version", "certificate.edit",
        dict(certificate_id="00000000-0000-4000-8000-000000000001",
             expected_version=1, certificate_number="DENIED", issue_date=date(2026, 11, 15),
             expiry_date=None, scopes=[], reason=None),
    ),
    (
        "promote_certificate_current", "certificate.approve",
        dict(certificate_id="00000000-0000-4000-8000-000000000001",
             expected_version=1, reason=None),
    ),
    (
        "issue_business_eligibility", "certificate.issue",
        dict(site_id="00000000-0000-4000-8000-000000000002",
             certificate_number="DENIED", issued_on=date(2026, 11, 15),
             expires_on=None, professional_responsible_person_name=None,
             notes=None, linked_certificates=[], reason=None),
    ),
    (
        "upsert_business_eligibility_latest_version", "certificate.edit",
        dict(business_eligibility_certificate_id="00000000-0000-4000-8000-000000000003",
             expected_version=1, certificate_number="DENIED",
             issued_on=date(2026, 11, 15), expires_on=None,
             professional_responsible_person_name=None, notes=None,
             linked_certificates=[], reason=None),
    ),
    (
        "promote_business_eligibility_current", "certificate.approve",
        dict(business_eligibility_certificate_id="00000000-0000-4000-8000-000000000003",
             expected_version=1, reason=None),
    ),
])
@pytest.mark.parametrize("other_permission", [None, "certificate.issue", "certificate.edit", "certificate.approve"])
def test_certificate_lifecycle_service_guard_denies_before_any_database_read(
    scenario, operation, required_permission, kwargs, other_permission,
):
    """Service callers cannot bypass router RBAC or probe resource existence.

    All five lifecycle mutations must reject missing capability before even
    querying Site/Certificate/Version, locking, flushing, or auditing.
    """
    if other_permission == required_permission:
        pytest.skip("This test exercises missing permission, not authorized behavior")
    engine, _ = scenario
    service = CaseWorkflowService()
    user = build_authenticated_user(
        f"no-{required_permission}", "viewer",
        permissions=set() if other_permission is None else {other_permission},
    )
    with Session(engine) as db:
        reads = []

        def capture_sql(conn, cursor, statement, parameters, context, executemany):
            reads.append(statement)

        event.listen(engine, "before_cursor_execute", capture_sql)
        try:
            with pytest.raises(HTTPException) as forbidden:
                getattr(service, operation)(db, **kwargs, user=user)
        finally:
            event.remove(engine, "before_cursor_execute", capture_sql)
        assert forbidden.value.status_code == 403
        assert required_permission in str(forbidden.value.detail)
        assert reads == []
        assert not db.new and not db.dirty
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_certificate_lifecycle_permission_checks_do_not_flush_pending_orm_drafts(scenario):
    """Denied service calls cannot auto-flush unrelated pending Case edits."""
    engine, (case_id, _, _) = scenario
    with Session(engine) as db:
        draft = db.get(Case, case_id)
        draft.state = CaseState.PLANNED
        flushed = []

        def prevent_flush(session, context, instances):
            flushed.append(True)
            raise AssertionError("Unauthorized lifecycle call flushed a draft")

        event.listen(db, "before_flush", prevent_flush)
        try:
            with pytest.raises(HTTPException) as denied:
                CaseWorkflowService().issue_business_eligibility(
                    db, site_id=draft.site_id, certificate_number="NOT-ISSUED",
                    issued_on=date(2026, 11, 15), expires_on=None,
                    professional_responsible_person_name=None, notes=None,
                    linked_certificates=[], reason=None,
                    user=build_authenticated_user(
                        "no-issue", "viewer", permissions={"certificate.edit"},
                    ),
                )
        finally:
            event.remove(db, "before_flush", prevent_flush)
        assert denied.value.status_code == 403
        assert flushed == []
        assert draft.state == CaseState.PLANNED
        assert draft in db.dirty
        db.rollback()


@pytest.mark.parametrize("operation,kwargs,required", [
    ("finalize_inspection_outcome", {
        "case_id": "00000000-0000-4000-8000-000000000001",
        "expected_version": 1, "final_evaluation": "DENIED", "reason": None,
    }, {"inspection.edit"}),
    ("create_approval_submission", {
        "case_id": "00000000-0000-4000-8000-000000000001",
        "stage": "PCT", "reference": None, "submitted_on": None,
        "submitted_time": None, "pct_submission_id": None, "reason": None,
    }, {"inspection.edit"}),
    ("complete_approval_submission", {
        "approval_submission_id": "00000000-0000-4000-8000-000000000002",
        "expected_version": 1, "completed_on": date(2026, 11, 15),
        "completed_time": None, "reason": None,
    }, {"inspection.edit"}),
    ("bind_approval_document", {
        "approval_submission_id": "00000000-0000-4000-8000-000000000002",
        "document_id": "00000000-0000-4000-8000-000000000003",
        "expected_version": 1, "reason": None,
    }, {"inspection.edit", "document.read"}),
])
@pytest.mark.parametrize("permissions", [set(), {"case.edit"}, {"inspection.edit"}, {"document.read"}])
def test_approval_mutations_enforce_service_permissions_before_any_read(
    scenario, operation, kwargs, required, permissions,
):
    """Direct service callers may not bypass the owning HTTP route permissions."""
    if required.issubset(permissions):
        pytest.skip("Authorized caller: existing business-gate tests cover this case")
    engine, _ = scenario
    user = build_authenticated_user("approval-denied", "viewer", permissions=permissions)
    with Session(engine) as db:
        reads = []

        def capture_sql(conn, cursor, statement, parameters, context, executemany):
            reads.append(statement)

        event.listen(engine, "before_cursor_execute", capture_sql)
        try:
            with pytest.raises(HTTPException) as denied:
                getattr(CaseWorkflowService(), operation)(db, **kwargs, user=user)
        finally:
            event.remove(engine, "before_cursor_execute", capture_sql)
        assert denied.value.status_code == 403
        assert reads == []
        assert not db.new and not db.dirty
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_denied_approval_document_bind_does_not_flush_pending_case_draft(scenario):
    engine, (case_id, _, _) = scenario
    with Session(engine) as db:
        case = db.get(Case, case_id)
        case.state = CaseState.PLANNED
        flushes = []

        def reject_flush(session, context, instances):
            flushes.append(True)
            raise AssertionError("Denied approval document mutation must not flush draft")

        event.listen(db, "before_flush", reject_flush)
        try:
            with pytest.raises(HTTPException) as denied:
                CaseWorkflowService().bind_approval_document(
                    db,
                    approval_submission_id="00000000-0000-4000-8000-000000000002",
                    document_id="00000000-0000-4000-8000-000000000003",
                    expected_version=1, reason=None,
                    user=build_authenticated_user(
                        "approval-reader-only", "viewer", permissions={"document.read"},
                    ),
                )
        finally:
            event.remove(db, "before_flush", reject_flush)
        assert denied.value.status_code == 403
        assert flushes == []
        assert case in db.dirty
        db.rollback()


def test_explicit_decision_persists_once_and_scoped_get_has_no_side_effects(scenario):
    engine, (case_id, other_id, _) = scenario
    service = CaseWorkflowService()
    with Session(engine) as db:
        assert service.get_case_nonissuance_decision(db, case_id=case_id)["decision"] is None
        created = _record(db, case_id)
        assert created["decision"]["decision_reference"] == "DEC-001"
        assert db.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        db.commit()
    with Session(engine) as db:
        assert service.get_case_nonissuance_decision(db, case_id=other_id)["decision"] is None
        receipt = service.get_case_nonissuance_decision(db, case_id=case_id)
        assert receipt == created
        assert service.get_case_certificate_issue_readiness(db, case_id=case_id, user=_actor())["reason_code"] == "case_nonissuance_decision_recorded"
        assert service.get_case_certificate_issue_readiness(db, case_id=other_id, user=_actor())["available"]
        assert db.scalar(select(func.count(AuditEvent.id))) == 1
        assert db.scalar(select(func.count(CaseCertificateNonissuanceDecision.id))) == 1
        assert not db.new and not db.dirty
    with Session(engine) as db:
        with pytest.raises(HTTPException) as repeated:
            _record(db, case_id)
        assert repeated.value.status_code == 409
        db.rollback()
    with Session(engine) as db:
        assert db.scalar(select(func.count(AuditEvent.id))) == 1



def test_nonissuance_and_issuance_readers_never_flush_or_discard_dirty_drafts(scenario):
    """Three GET surfaces must read persisted facts without modifying a caller's draft."""
    engine, (case_id, _, site_id) = scenario
    svc = CaseWorkflowService()
    with Session(engine) as db:
        case = db.get(Case, case_id)
        outcome = db.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case_id))
        case.state = CaseState.CERTIFIED
        outcome.final_evaluation = None
        pending = Certificate(
            site_id=site_id, case_id=case_id, certificate_type="GMP",
            issuance_basis="inspection_case", latest_flag=False,
        )
        db.add(pending)
        flushes = []

        def reject_flush(session, context, instances):
            flushes.append(True)
            raise AssertionError("Advisory GET must not flush pending business changes")

        event.listen(db, "before_flush", reject_flush)
        try:
            assert svc.get_case_nonissuance_decision(db, case_id=case_id)["decision"] is None
            decision = svc.get_case_nonissuance_record_readiness(
                db, case_id=case_id, user=_actor(),
            )
            issuance = svc.get_case_certificate_issue_readiness(
                db, case_id=case_id, user=_actor(),
            )
        finally:
            event.remove(db, "before_flush", reject_flush)
        assert decision["available"] is True
        assert decision["reason_code"] is None
        assert issuance["available"] is True
        assert issuance["reason_code"] is None
        assert not flushes
        assert case.state == CaseState.CERTIFIED
        assert outcome.final_evaluation is None
        assert pending in db.new
        assert case in db.dirty and outcome in db.dirty
        db.rollback()
    with Session(engine) as verify:
        assert verify.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert verify.scalar(
            select(InspectionOutcome.final_evaluation)
            .where(InspectionOutcome.case_id == case_id)
        ) == "Recorded final assessment"
        assert verify.scalar(select(func.count(Certificate.id))) == 0


def test_readiness_uses_current_sql_case_state_without_overwriting_cached_case(scenario):
    """Source is SQL-current even when the ORM identity is stale."""
    engine, (case_id, _, _) = scenario
    svc = CaseWorkflowService()
    with Session(engine) as db:
        cached = db.get(Case, case_id)
        assert cached.state == CaseState.AWAITING_CERTIFICATE_DECISION
        db.execute(
            update(Case).where(Case.id == case_id)
            .values(state=CaseState.PLANNED)
            .execution_options(synchronize_session=False)
        )
        assert cached.state == CaseState.AWAITING_CERTIFICATE_DECISION
        decision = svc.get_case_nonissuance_record_readiness(
            db, case_id=case_id, user=_actor(),
        )
        issuance = svc.get_case_certificate_issue_readiness(
            db, case_id=case_id, user=_actor(),
        )
        assert decision["reason_code"] == "case_state_not_eligible"
        assert issuance["reason_code"] == "case_state_not_eligible"
        assert cached.state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert not db.new and not db.dirty
        db.rollback()


def test_readiness_uses_persisted_capa_status_without_discarding_pending_edit(scenario):
    """A pending CAPA edit cannot authorize a decision, or be destroyed by GET."""
    engine, (case_id, _, _) = scenario
    with Session(engine) as seed:
        cycle = CapaCycle(case_id=case_id, round_no=1, status="requested")
        seed.add(cycle)
        seed.commit()
        cycle_id = cycle.id
    with Session(engine) as db:
        cached = db.get(CapaCycle, cycle_id)
        cached.status = "accepted"
        svc = CaseWorkflowService()
        decision = svc.get_case_nonissuance_record_readiness(
            db, case_id=case_id, user=_actor(),
        )
        issuance = svc.get_case_certificate_issue_readiness(
            db, case_id=case_id, user=_actor(),
        )
        assert decision["reason_code"] == "latest_capa_not_accepted"
        assert issuance["reason_code"] == "latest_capa_not_accepted"
        assert cached.status == "accepted"
        assert cached in db.dirty
        db.rollback()
    with Session(engine) as verify:
        assert verify.get(CapaCycle, cycle_id).status == "requested"


def test_canonical_get_does_not_flush_unpersisted_nonissuance_fact(scenario):
    """Unknown-outcome readback must never promote a pending in-memory decision."""
    engine, (case_id, _, _) = scenario
    with Session(engine) as db:
        db.add(CaseCertificateNonissuanceDecision(
            case_id=case_id, decided_on=date(2026, 11, 15),
            decision_reference="PENDING-NOT-COMMITTED", explanation="Synthetic",
            recorded_by_user_id="00000000-0000-4000-8000-000000000001",
        ))
        result = CaseWorkflowService().get_case_nonissuance_decision(db, case_id=case_id)
        assert result == {"case_id": case_id, "decision": None}
        assert len(db.new) == 1
        db.rollback()


@pytest.mark.parametrize("permissions", [
    {"inspection.edit"}, {"certificate.approve"}, {"certificate.edit"},
])
def test_direct_certificate_issue_requires_issue_permission_without_effects(scenario, permissions):
    """The service owner, not just the HTTP endpoint, must reject unprivileged issuance."""
    engine, (case_id, _, site_id) = scenario
    actor = build_authenticated_user("unprivileged-certificate-actor", "viewer", permissions=permissions)
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            CaseWorkflowService().issue_certificate(
                db, site_id=site_id, case_id=case_id,
                certificate_type="GMP", issuance_basis="inspection_case",
                certificate_number="MUST-NOT-ISSUE", issue_date=date(2026, 11, 15),
                expiry_date=date(2028, 11, 15), scopes=[], reason=None, user=actor,
            )
        assert error.value.status_code == 403
        assert db.scalar(select(func.count(Certificate.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == 0
        assert not db.new and not db.dirty


def test_unauthorized_certificate_issue_does_not_probe_site_case_or_create_audit(scenario):
    engine, _ = scenario
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            CaseWorkflowService().issue_certificate(
                db, site_id="00000000-0000-4000-8000-000000000001",
                case_id="00000000-0000-4000-8000-000000000002",
                certificate_type="GMP", issuance_basis="inspection_case",
                certificate_number="DENIED", issue_date=date(2026, 11, 15),
                expiry_date=None, scopes=[], reason=None,
                user=build_authenticated_user("unprivileged-certificate-reader", "viewer"),
            )
        assert error.value.status_code == 403
        assert db.scalar(select(func.count(AuditEvent.id))) == 0
        assert not db.new and not db.dirty

def test_decision_prevents_future_case_backed_certificate_issue(scenario):
    engine, (case_id, _, site_id) = scenario
    with Session(engine) as db:
        _record(db, case_id)
        db.commit()
    with Session(engine) as db:
        with pytest.raises(HTTPException) as blocked:
            CaseWorkflowService().issue_certificate(
                db, site_id=site_id, case_id=case_id,
                certificate_type="GMP", issuance_basis="inspection_case",
                certificate_number="MUST-NOT-ISSUE", issue_date=date(2026, 11, 13),
                expiry_date=date(2028, 11, 13), scopes=[], reason=None, user=_actor(),
            )
        assert blocked.value.status_code == 409
        db.rollback()
        assert db.scalar(select(func.count(Certificate.id))) == 0


@pytest.mark.parametrize("change", ["wrong_state", "missing_final", "existing_certificate", "blank_reference", "blank_explanation", "stale_case_version"])
def test_decision_fails_closed_without_mutation(scenario, change):
    engine, (case_id, _, site_id) = scenario
    with Session(engine) as db:
        if change == "wrong_state":
            db.get(Case, case_id).state = CaseState.CERTIFIED
        if change == "missing_final":
            db.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case_id)).final_evaluation = None
        if change == "existing_certificate":
            db.add(Certificate(site_id=site_id, case_id=case_id, certificate_type="GMP", issuance_basis="inspection_case", latest_flag=False))
        db.commit()
    with Session(engine) as db:
        kwargs = {
            "case_id": case_id, "expected_case_version": 999 if change == "stale_case_version" else db.get(Case, case_id).row_version,
            "decided_on": date(2026, 11, 13),
            "decision_reference": "   " if change == "blank_reference" else "DEC-001",
            "explanation": " " if change == "blank_explanation" else "Documented explicit reason",
            "reason": None, "user": _actor(),
        }
        with pytest.raises(HTTPException) as error:
            CaseWorkflowService().record_case_nonissuance_decision(db, **kwargs)
        assert error.value.status_code in {409, 422}
        db.rollback()
        assert db.scalar(select(func.count(CaseCertificateNonissuanceDecision.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == 0


def test_http_permissions_and_canonical_get(scenario):
    engine, (case_id, _, _) = scenario
    app = FastAPI()
    register_workflow_routes(app, lambda: None)
    paths = [r for r in app.routes if getattr(r, "path", "") == "/cases/{case_id}/certificate-nonissuance-decision"]
    assert {frozenset(r.methods) for r in paths} == {frozenset({"GET"}), frozenset({"POST"})}
    post = next(r.endpoint for r in paths if r.methods == {"POST"})
    get = next(r.endpoint for r in paths if r.methods == {"GET"})
    from backend.app.read_models import CaseNonissuanceDecisionRecordRequest
    with Session(engine) as db:
        payload = CaseNonissuanceDecisionRecordRequest(
            expected_case_version=1, decided_on=date(2026, 11, 13),
            decision_reference="DEC-001", explanation="Documented decision",
        )
        denied = build_authenticated_user("denied", permissions={"inspection.edit"})
        with pytest.raises(HTTPException) as error:
            post(case_id=case_id, payload=payload, session=db, user=denied)
        assert error.value.status_code == 403
        reader = build_authenticated_user("reader", "reader")
        result = get(case_id=case_id, session=db, user=reader)
        assert result.decision is None



@pytest.mark.parametrize("permissions", [set(), {"inspection.edit"}, {"certificate.issue"}])
def test_direct_service_nonissuance_requires_approval_permission_without_side_effects(scenario, permissions):
    """Service callers cannot bypass the HTTP permission owner.

    Authorization must fail before any Case lock, actor creation, business
    decision or audit write. The denied actor must not be persisted.
    """
    engine, (case_id, _, _) = scenario
    denied = build_authenticated_user("nonissuance-service-denied", "viewer", permissions=permissions)
    with Session(engine) as db:
        service = CaseWorkflowService()
        before_case = db.get(Case, case_id).row_version
        with pytest.raises(HTTPException) as error:
            service.record_case_nonissuance_decision(
                db, case_id=case_id, expected_case_version=before_case,
                decided_on=date(2026, 11, 13), decision_reference="DENIED-001",
                explanation="Must never persist", reason="synthetic permission probe",
                user=denied,
            )
        assert error.value.status_code == 403
        assert service.get_case_nonissuance_record_readiness(
            db, case_id=case_id, user=denied
        )["reason_code"] == "missing_permission"
        assert db.scalar(select(func.count(CaseCertificateNonissuanceDecision.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == 0
        assert db.get(Case, case_id).row_version == before_case
        assert not db.new and not db.dirty


def test_service_permission_guard_precedes_case_lookup(scenario):
    """Do not reveal Case existence to unauthorized direct service calls."""
    engine, (_, _, _) = scenario
    with Session(engine) as db:
        with pytest.raises(HTTPException) as error:
            CaseWorkflowService().record_case_nonissuance_decision(
                db, case_id="00000000-0000-4000-8000-000000000001",
                expected_case_version=1, decided_on=date(2026, 11, 13),
                decision_reference="DENIED-404", explanation="Denied",
                reason=None,
                user=build_authenticated_user("nonissuance-unknown-reader", "viewer", permissions=set()),
            )
        assert error.value.status_code == 403
        assert db.scalar(select(func.count(AuditEvent.id))) == 0
        assert not db.new and not db.dirty

def test_no_certificate_row_does_not_imply_nonissuance(scenario):
    engine, (case_id, _, _) = scenario
    with Session(engine) as db:
        assert db.scalar(select(func.count(Certificate.id))) == 0
        assert CaseWorkflowService().get_case_nonissuance_decision(db, case_id=case_id)["decision"] is None


def test_explicit_decision_blocks_case_state_transition_and_workspace_action(scenario):
    engine, (case_id, _, _) = scenario
    from backend.app.services.catalog import CatalogReadService
    from backend.app.read_models import CaseWorkspaceRead
    actor = build_authenticated_user(
        "decision-and-transition-reader", "manager",
        permissions={"certificate.approve", "certificate.issue", "case.edit"},
    )
    with Session(engine) as db:
        _record(db, case_id)
        db.commit()
    with Session(engine) as db:
        workspace = CaseWorkspaceRead.model_validate(
            CatalogReadService().get_case_workspace(db, case_id=case_id, user=actor)
        )
        assert workspace.nonissuance_decision is not None
        assert workspace.nonissuance_decision.decision is not None
        assert workspace.nonissuance_decision.decision.decision_reference == "DEC-001"
        actions = {a.target_state: a for a in workspace.transition_actions}
        for target in ("certified", "cancelled"):
            assert actions[target].available is False
            assert actions[target].reason_code == "nonissuance_decision_recorded"
            with pytest.raises(HTTPException) as denied:
                CaseWorkflowService().transition_case(
                    db, case_id=case_id, target_state=target,
                    expected_version=db.get(Case, case_id).row_version,
                    reason="Must not misclassify a recorded non-issuance", user=actor,
                )
            assert denied.value.status_code == 409
            db.rollback()
    with Session(engine) as db:
        assert db.get(Case, case_id).state == CaseState.AWAITING_CERTIFICATE_DECISION
        assert db.scalar(select(func.count(AuditEvent.id))) == 1

def test_explicit_nonissuance_readiness_permission_case_state_and_canonical_workspace(scenario):
    from backend.app.read_models import CaseNonissuanceDecisionReadinessRead
    from backend.app.services.catalog import CatalogReadService
    engine, (case_id, other_id, _) = scenario
    svc = CaseWorkflowService()
    reader = build_authenticated_user("nonissuance-reader", "reader")
    with Session(engine) as db:
        eligible = svc.get_case_nonissuance_record_readiness(db, case_id=case_id, user=_actor())
        assert eligible["action_key"] == "record_certificate_nonissuance_decision"
        assert eligible["available"] is True and eligible["reason_code"] is None
        assert eligible["expected_case_version"] == db.get(Case, case_id).row_version
        assert eligible["required_permissions"] == ["certificate.approve"]
        assert CaseNonissuanceDecisionReadinessRead(**eligible).available is True
        denied = svc.get_case_nonissuance_record_readiness(db, case_id=case_id, user=reader)
        assert denied["available"] is False and denied["reason_code"] == "missing_permission"
        workspace = CatalogReadService().get_case_workspace(db, case_id=case_id, user=_actor())
        assert workspace["nonissuance_record_readiness"]["available"] is True
        assert workspace["nonissuance_decision"]["decision"] is None
        assert not db.new and not db.dirty
    with Session(engine) as db:
        _record(db, case_id)
        db.commit()
    with Session(engine) as db:
        recorded = svc.get_case_nonissuance_record_readiness(db, case_id=case_id, user=_actor())
        assert recorded["available"] is False and recorded["reason_code"] == "nonissuance_already_recorded"
        assert svc.get_case_nonissuance_record_readiness(db, case_id=other_id, user=_actor())["available"] is True


@pytest.mark.parametrize("change,reason", [
    ("wrong_state", "case_state_not_eligible"),
    ("missing_final", "final_evaluation_missing"),
    ("existing_certificate", "linked_certificate_exists"),
])
def test_readiness_matches_mutation_blocking_reason(scenario, change, reason):
    engine, (case_id, _, site_id) = scenario
    with Session(engine) as db:
        if change == "wrong_state":
            db.get(Case, case_id).state = CaseState.CERTIFIED
        if change == "missing_final":
            db.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case_id)).final_evaluation = None
        if change == "existing_certificate":
            db.add(Certificate(site_id=site_id, case_id=case_id, certificate_type="GMP", latest_flag=False))
        db.commit()
    with Session(engine) as db:
        before = db.scalar(select(func.count(AuditEvent.id)))
        state = CaseWorkflowService().get_case_nonissuance_record_readiness(db, case_id=case_id, user=_actor())
        assert state["available"] is False and state["reason_code"] == reason
        assert db.scalar(select(func.count(AuditEvent.id))) == before
        with pytest.raises(HTTPException) as failed:
            _record(db, case_id, expected=db.get(Case, case_id).row_version)
        assert failed.value.status_code == 409
        db.rollback()


def test_readiness_http_route_read_role_and_nonexistent_case(scenario):
    engine, (case_id, _, _) = scenario
    app = FastAPI()
    register_workflow_routes(app, lambda: None)
    endpoint = next(
        r.endpoint for r in app.routes if getattr(r, "path", "")
        == "/cases/{case_id}/certificate-nonissuance-decision/readiness"
    )
    with Session(engine) as db:
        row = endpoint(case_id=case_id, session=db, user=build_authenticated_user("reader", "reader"))
        assert row.available is False and row.reason_code == "missing_permission"
        assert row.case_id == case_id
        assert row.expected_case_version == db.get(Case, case_id).row_version
        with pytest.raises(HTTPException) as forbidden:
            endpoint(case_id=case_id, session=db, user=build_authenticated_user("viewer", "viewer"))
        assert forbidden.value.status_code == 403
        with pytest.raises(HTTPException) as missing:
            endpoint(case_id="00000000-0000-4000-8000-000000000001", session=db, user=build_authenticated_user("reader", "reader"))
        assert missing.value.status_code == 404

