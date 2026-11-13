"""Synthetic Case decision regression: explicit no-issuance fact is not inferred."""
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.api.routers.workflow import register_workflow_routes
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, CaseCertificateNonissuanceDecision, Certificate,
    Company, InspectionOutcome, Site,
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
        reader = build_authenticated_user("reader", "viewer")
        result = get(case_id=case_id, session=db, user=reader)
        assert result.decision is None


def test_no_certificate_row_does_not_imply_nonissuance(scenario):
    engine, (case_id, _, _) = scenario
    with Session(engine) as db:
        assert db.scalar(select(func.count(Certificate.id))) == 0
        assert CaseWorkflowService().get_case_nonissuance_decision(db, case_id=case_id)["decision"] is None
