import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import ROLE_PERMISSIONS, build_authenticated_user, get_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent,
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion,
    CapaCycle,
    Case,
    CaseApplication,
    CaseAssessment,
    CaseEvaluationScope,
    Certificate,
    CertificateScope,
    CertificateVersion,
    Company,
    InspectionEvent,
    InspectionOutcome,
    InspectionPeriodSegment,
    InspectionPlan,
    InspectionTeam,
    InspectionTeamMember,
    InspectorProfile,
    Person,
    ProductionLine,
    Site,
)
from backend.app.main import create_app
from backend.app.read_models import (
    CapaCycleAssessRequest,
    CapaCycleCreateRequest,
    CaseApplicationUpsertRequest,
    InspectionCaseCreateRequest,
    InspectionOutcomeUpsertRequest,
    InspectionPlanUpsertRequest,
    InspectionTeamUpsertRequest,
)
from backend.app.services.workflow import CaseWorkflowService


def seed_case(session: Session, *, gxp_type: str = "GMP") -> str:
    company = Company(legal_name="Test Company", short_name="TC")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="Test Site")
    session.add(site)
    session.flush()
    case = Case(site_id=site.id, gxp_type=gxp_type, state=CaseState.DRAFT)
    session.add(case)
    session.commit()
    return case.id


def test_reassessment_scope_copy_uses_canonical_production_line_id_over_stale_scope_text():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Canonical identity", short_name="CID")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Canonical site")
        session.add(site)
        session.flush()
        line = ProductionLine(site_id=site.id, code="A", effective_from=date(2020, 1, 1))
        session.add(line)
        session.flush()
        source = Case(site_id=site.id, gxp_type="GMP", production_line_id=line.id, scope_code="OLD-A", state=CaseState.CLOSED)
        target = Case(site_id=site.id, gxp_type="GMP", production_line_id=line.id, scope_code="A", state=CaseState.DRAFT)
        session.add_all([source, target])
        session.flush()
        session.add(
            CaseEvaluationScope(
                case_id=source.id,
                source_classification="LEGACY_IMPORTED",
                raw_legacy_value="Canonical source scope",
                rendered_prose="Canonical source scope",
            )
        )
        session.commit()

    with Session(engine) as session:
        source = session.scalar(select(Case).where(Case.scope_code == "OLD-A"))
        target = session.scalar(select(Case).where(Case.scope_code == "A"))
        assert source is not None and target is not None
        CaseWorkflowService()._copy_evaluation_scope_for_reassessment(
            session,
            source_case_id=source.id,
            target_case=target,
        )
        session.commit()
        copied = session.scalar(select(CaseEvaluationScope).where(CaseEvaluationScope.case_id == target.id))

    assert copied is not None
    assert copied.rendered_prose == "Canonical source scope"


def seed_inspection_team_identities(session: Session) -> dict[str, str]:
    inspector_person = Person(full_name="Inspector One", display_name="Inspector 1")
    direct_person = Person(full_name="Member Two", display_name="Member 2")
    session.add_all([inspector_person, direct_person])
    session.flush()
    profile = InspectorProfile(person_id=inspector_person.id, legacy_display_text="Inspector 1", is_active=True)
    session.add(profile)
    session.flush()
    return {"profile_id": profile.id, "inspector_person_id": inspector_person.id, "direct_person_id": direct_person.id}


def seed_create_inspection_case_context(
    session: Session,
    *,
    gxp_type: str = "GMP",
    line_code: str | None = "A",
    case_state: CaseState = CaseState.CLOSED,
    include_case: bool = True,
    include_certificate: bool = False,
    site_name: str = "Create Case Site",
) -> dict[str, str | None]:
    company = Company(legal_name=f"{site_name} Company", short_name="CCS")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name=site_name)
    session.add(site)
    session.flush()
    line = None if line_code is None else ProductionLine(site_id=site.id, code=line_code, effective_from=date(2000, 1, 1))
    if line is not None:
        session.add(line)
        session.flush()

    seeded_case_id: str | None = None
    if include_case:
        seeded_case = Case(
            site_id=site.id,
            gxp_type=gxp_type,
            scope_code=line_code,
            production_line_id=None if line is None else line.id,
            applicable_standard="WHO-GMP",
            inspection_type="Định kỳ",
            state=case_state,
        )
        session.add(seeded_case)
        session.flush()
        seeded_case_id = seeded_case.id

    if include_certificate:
        certificate = Certificate(
            site_id=site.id,
            case_id=seeded_case_id,
            certificate_type=gxp_type,
            line_code=line_code,
            production_line_id=None if line is None else line.id,
            latest_flag=True,
        )
        session.add(certificate)
        session.flush()
        session.add(
            CertificateVersion(
                certificate_id=certificate.id,
                version_no=1,
                certificate_number="GCN-CREATE-001",
                issue_date=date(2026, 8, 1),
                expiry_date=date(2027, 8, 1),
                applicable_standard="WHO-GMP",
                is_latest_version=True,
            )
        )

    session.commit()
    return {"site_id": site.id, "seeded_case_id": seeded_case_id, "production_line_id": None if line is None else line.id}


def test_phase10_transition_route_is_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/cases/{case_id}/transition" in routes
    assert "/cases/{case_id}/application" in routes
    assert "/cases/{case_id}/assessment" in routes
    assert "/cases/{case_id}/evaluation-scope" in routes
    assert "/cases/{case_id}/plan" in routes
    assert "/cases/{case_id}/outcome" in routes
    assert "/cases/{case_id}/team" in routes
    assert "/sites/{site_id}/inspection-cases" in routes
    assert "/cases/{case_id}/capa-cycles" in routes
    assert "/capa-cycles/{capa_cycle_id}" in routes
    assert "/capa-cycles/{capa_cycle_id}/submit" in routes
    assert "/capa-cycles/{capa_cycle_id}/assess" in routes
    assert "/sites/{site_id}/certificates" in routes
    assert "/certificates/{certificate_id}/latest-version" in routes
    assert "/certificates/{certificate_id}/promote-current" in routes
    assert "/sites/{site_id}/business-eligibility-certificates" in routes
    assert "/business-eligibility-certificates/{business_eligibility_certificate_id}/latest-version" in routes
    assert "/business-eligibility-certificates/{business_eligibility_certificate_id}/promote-current" in routes


def test_create_inspection_case_persists_draft_case_without_downstream_rows():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.CLOSED)

    with Session(engine) as session:
        result = service.create_inspection_case(
            session,
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="A",
            production_line_id=seeded["production_line_id"],
            applicable_standard="WHO-GMP",
            reason="Open new inspection case.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["site_id"] == seeded["site_id"]
    assert result["gxp_type"] == "GMP"
    assert result["line_code"] == "A"
    assert result["production_line_id"] == seeded["production_line_id"]
    assert result["inspection_type"] == "Tái"
    assert result["applicable_standard"] == "WHO-GMP"
    assert result["state"] == "draft"
    assert result["legacy_inspection_id"] is None
    assert result["legacy_inspection_code"] is None
    assert result["audit_event_id"] is not None

    with Session(engine) as session:
        created = session.get(Case, result["case_id"])
        assert created is not None
        assert created.state == CaseState.DRAFT
        assert created.scope_code == "A"
        assert created.production_line_id == seeded["production_line_id"]
        assert session.scalar(select(CaseApplication).where(CaseApplication.case_id == created.id)) is None
        assert session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == created.id)) is None
        assert session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == created.id)) is None
        assert session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == created.id)) is None
        assert session.scalar(select(InspectionEvent).where(InspectionEvent.case_id == created.id)) is None
        audit_event = session.get(AuditEvent, result["audit_event_id"])
        assert audit_event is not None
        assert audit_event.action == "case.create_reassessment_case"
        assert json.loads(audit_event.payload_redacted)["line_code"] == "A"


def test_create_inspection_case_allows_authoritative_certificate_only_line_context():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(
            session,
            line_code="B",
            include_case=False,
            include_certificate=True,
            site_name="Certificate Only Site",
        )

    with Session(engine) as session:
        result = service.create_inspection_case(
            session,
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="B",
            production_line_id=seeded["production_line_id"],
            applicable_standard=None,
            reason="Create from certificate-owned line context.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["line_code"] == "B"
    assert result["applicable_standard"] is None


def test_create_inspection_case_allows_facility_wide_context_without_inventing_line():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code=None, case_state=CaseState.CLOSED)

    with Session(engine) as session:
        result = service.create_inspection_case(
            session,
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code=None,
            applicable_standard=None,
            reason="Facility-wide create.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["line_code"] is None


def test_create_inspection_case_rejects_invalid_site_gxp_or_line_context():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.CLOSED)

    with Session(engine) as session:
        try:
            service.create_inspection_case(
                session,
                site_id="missing-site",
                gxp_type="GMP",
                line_code="A",
                applicable_standard=None,
                reason="Missing site.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "Site not found" in str(exc)
        else:
            raise AssertionError("Expected missing site to fail")

    with Session(engine) as session:
        for gxp_type, line_code, expected_detail in [
            ("GDP", "A", "Unsupported GxP context"),
            ("GMP", "Z", "Canonical ProductionLine identity has not been resolved"),
        ]:
            try:
                service.create_inspection_case(
                    session,
                    site_id=seeded["site_id"],
                    gxp_type=gxp_type,
                    line_code=line_code,
                    applicable_standard=None,
                    reason="Invalid context.",
                    user=build_authenticated_user("manager01", "manager"),
                )
            except Exception as exc:
                assert expected_detail in str(exc)
            else:
                raise AssertionError("Expected invalid create context to fail")


def test_create_inspection_case_rejects_duplicate_open_case_and_is_retry_safe():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.DRAFT)

    with Session(engine) as session:
        try:
            service.create_inspection_case(
                session,
                site_id=seeded["site_id"],
                gxp_type="GMP",
                line_code="A",
                production_line_id=seeded["production_line_id"],
                applicable_standard=None,
                reason="Duplicate.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "open inspection case already exists" in str(exc)
        else:
            raise AssertionError("Expected duplicate create to fail")

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code="B", case_state=CaseState.CLOSED, site_name="Retry Site")

    with Session(engine) as session:
        created = service.create_inspection_case(
            session,
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="B",
            production_line_id=seeded["production_line_id"],
            applicable_standard=None,
            reason="First create.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.create_inspection_case(
                session,
                site_id=seeded["site_id"],
                gxp_type="GMP",
                line_code="B",
                production_line_id=seeded["production_line_id"],
                applicable_standard=None,
                reason="Retry create.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "open inspection case already exists" in str(exc)
        else:
            raise AssertionError("Expected retry create to fail")
        assert session.scalar(select(Case).where(Case.id == created["case_id"])) is not None


def test_create_inspection_case_duplicate_rule_is_site_scoped():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.DRAFT, site_name="Open Site")
        seeded = seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.CLOSED, site_name="Target Site")

    with Session(engine) as session:
        result = service.create_inspection_case(
            session,
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="A",
            production_line_id=seeded["production_line_id"],
            applicable_standard=None,
            reason="Different site context.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["site_id"] == seeded["site_id"]


def test_create_inspection_case_server_owns_reassessment_type():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.CLOSED)

    with Session(engine) as session:
        result = service.create_inspection_case(
            session,
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="A",
            production_line_id=seeded["production_line_id"],
            applicable_standard=None,
            reason="Server-owned reassessment type.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["inspection_type"] == "Tái"


def test_create_inspection_case_route_enforces_auth_and_returns_created_read_model(tmp_path):
    database_path = tmp_path / "workflow-create-route.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.CLOSED)

    app = create_app(database_url)
    route = next(route for route in app.routes if getattr(route, "path", "") == "/sites/{site_id}/inspection-cases")
    payload = InspectionCaseCreateRequest(
        gxp_type="GMP",
        line_code="A",
        production_line_id=seeded["production_line_id"],
        applicable_standard="WHO-GMP",
        reason="HTTP create",
    )

    try:
        get_authenticated_user(SimpleNamespace(app=app, headers={}))
    except Exception as exc:
        assert "Missing authenticated username" in str(exc)
    else:
        raise AssertionError("Expected missing auth headers to fail closed")

    with Session(engine) as session:
        try:
            route.endpoint(
                site_id=seeded["site_id"],
                payload=payload,
                session=session,
                user=build_authenticated_user("reader01", "reader"),
            )
        except Exception as exc:
            assert "missing required permission" in str(exc).lower()
        else:
            raise AssertionError("Expected reader create to fail")

    with Session(engine) as session:
        body = route.endpoint(
            site_id=seeded["site_id"],
            payload=payload,
            session=session,
            user=build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"]),
        ).model_dump(mode="json")

    assert body["site_id"] == seeded["site_id"]
    assert body["gxp_type"] == "GMP"
    assert body["line_code"] == "A"
    assert body["inspection_type"] == "Tái"
    assert body["state"] == "draft"


def test_transition_case_persists_audit_without_fabricating_business_event():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        result = service.transition_case(
            session,
            case_id=case_id,
            target_state="application_received",
            reason="Initial intake completed.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["previous_state"] == "draft"
    assert result["current_state"] == "application_received"
    assert result["audit_event_id"] is not None
    assert result["inspection_event_id"] is None

    with Session(engine) as session:
        case_row = session.get(Case, case_id)
        assert case_row is not None
        assert case_row.state == CaseState.APPLICATION_RECEIVED
        audit_event = session.scalars(select(AuditEvent)).first()
        assert audit_event is not None
        assert json.loads(audit_event.old_values_json) == {"state": "draft"}
        assert json.loads(audit_event.new_values_json) == {"state": "application_received"}
        assert json.loads(audit_event.changed_fields_json) == {
            "state": {"old": "draft", "new": "application_received"}
        }
        assert json.loads(audit_event.payload_redacted) == {
            "current_state": "application_received",
            "inspection_event_id": result["inspection_event_id"],
            "previous_state": "draft",
            "reason": "Initial intake completed.",
        }
        assert session.scalars(select(InspectionEvent)).first() is None


def test_transition_case_rejects_invalid_transition_order():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        try:
            service.transition_case(
                session,
                case_id=case_id,
                target_state="certified",
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "not allowed" in str(exc)
        else:
            raise AssertionError("Expected invalid transition to fail")


def test_upsert_case_application_persists_stage_and_audit():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        result = service.upsert_case_application(
            session,
            case_id=case_id,
            submitted_on=None,
            dossier_code="HS-001",
            dossier_reference=None,
            applicant_name="Applicant A",
            reason="Initial intake metadata.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["dossier_code"] == "HS-001"
    assert result["audit_event_id"] is not None

    with Session(engine) as session:
        row = session.scalars(select(CaseApplication)).first()
        assert row is not None
        assert row.dossier_code == "HS-001"
        audit_event = session.scalars(select(AuditEvent).where(AuditEvent.action == "case_application.upsert")).first()
        assert audit_event is not None
        assert json.loads(audit_event.old_values_json) == {
            "applicant_name": None,
            "dossier_code": None,
            "dossier_reference": None,
            "submitted_on": None,
        }
        assert json.loads(audit_event.new_values_json) == {
            "applicant_name": "Applicant A",
            "dossier_code": "HS-001",
            "dossier_reference": None,
            "submitted_on": None,
        }
        case_row = session.get(Case, case_id)
        assert case_row is not None
        assert case_row.state == CaseState.DRAFT
        assert session.scalar(select(InspectionEvent).where(InspectionEvent.case_id == case_id)) is None


def test_upsert_case_application_writes_submission_event_without_transitioning_case_state():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        result = service.upsert_case_application(
            session,
            case_id=case_id,
            submitted_on=datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc),
            dossier_code="HS-003",
            dossier_reference=None,
            applicant_name="Applicant C",
            reason="Submission captured.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["inspection_event_id"] is not None

    with Session(engine) as session:
        case_row = session.get(Case, case_id)
        assert case_row is not None
        assert case_row.state == CaseState.DRAFT
        event = session.scalar(select(InspectionEvent).where(InspectionEvent.case_id == case_id))
        assert event is not None
        assert event.event_type == "application_submitted"


def test_upsert_case_application_rejects_stale_version_and_terminal_states():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        draft_case_id = seed_case(session)

    with Session(engine) as session:
        created = service.upsert_case_application(
            session,
            case_id=draft_case_id,
            submitted_on=None,
            dossier_code="HS-004",
            dossier_reference=None,
            applicant_name="Applicant D",
            reason="Initial create.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.upsert_case_application(
                session,
                case_id=draft_case_id,
                expected_version=created["row_version"] - 1,
                submitted_on=None,
                dossier_code="HS-004-STALE",
                dossier_reference=None,
                applicant_name="Applicant D",
                reason="Should conflict.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "Stale case_application update" in str(exc)
        else:
            raise AssertionError("Expected stale case application update to fail")

    for terminal_state in (CaseState.CLOSED, CaseState.CANCELLED):
        with Session(engine) as session:
            case_id = seed_case(session)
            case_row = session.get(Case, case_id)
            assert case_row is not None
            case_row.state = terminal_state
            session.commit()

        with Session(engine) as session:
            try:
                service.upsert_case_application(
                    session,
                    case_id=case_id,
                    submitted_on=None,
                    dossier_code="HS-TERMINAL",
                    dossier_reference=None,
                    applicant_name="Applicant Terminal",
                    reason="Should be blocked.",
                    user=build_authenticated_user("manager01", "manager"),
                )
            except Exception as exc:
                assert f"terminal state {terminal_state.value}" in str(exc)
            else:
                raise AssertionError("Expected terminal case application update to fail")


def test_upsert_case_application_route_enforces_auth_and_returns_read_model(tmp_path):
    database_path = tmp_path / "workflow-application-route.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        case_id = seed_case(session)

    app = create_app(database_url)
    route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/application")
    payload = CaseApplicationUpsertRequest(
        expected_version=None,
        submitted_on=datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc),
        dossier_code="HS-HTTP",
        applicant_name="Applicant HTTP",
    )

    with Session(engine) as session:
        try:
            route.endpoint(
                case_id=case_id,
                payload=payload,
                session=session,
                user=build_authenticated_user("reader01", "reader"),
            )
        except Exception as exc:
            assert "missing required permission" in str(exc).lower()
        else:
            raise AssertionError("Expected reader application upsert to fail")

    with Session(engine) as session:
        body = route.endpoint(
            case_id=case_id,
            payload=payload,
            session=session,
            user=build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"]),
        ).model_dump(mode="json")
        persisted = session.scalar(select(CaseApplication).where(CaseApplication.case_id == case_id))

    assert body["case_id"] == case_id
    assert persisted is not None
    assert body["row_version"] == persisted.row_version
    assert body["submitted_on"] == "2026-08-31T00:00:00Z"


def test_workflow_audit_payload_redacts_sensitive_keys():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        service.upsert_case_application(
            session,
            case_id=case_id,
            submitted_on=None,
            dossier_code="HS-002",
            dossier_reference=None,
            applicant_name="Applicant B",
            reason="Sensitive payload check.",
            user=build_authenticated_user("manager01", "manager"),
        )
        service._write_audit_event(
            session,
            actor=service._get_or_create_app_user(session, build_authenticated_user("manager01", "manager")),
            entity_type="case_application",
            entity_id=case_id,
            action="case_application.sensitive_test",
            payload={
                "authorization": "Bearer top-secret",
                "nested": {"api_token": "abc123", "normal": "ok"},
                "content_bytes": "010203",
            },
        )
        session.commit()

    with Session(engine) as session:
        audit_event = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "case_application.sensitive_test")
        ).one()
        assert json.loads(audit_event.payload_redacted) == {
            "authorization": "<redacted>",
            "content_bytes": "<redacted>",
            "nested": {"api_token": "<redacted>", "normal": "ok"},
        }


def test_upsert_case_assessment_persists_stage_and_event_when_assessed_on_present():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        result = service.upsert_case_assessment(
            session,
            case_id=case_id,
            assessed_on=datetime(2026, 8, 16, 8, 30, tzinfo=timezone.utc),
            assessor_name="Inspector A",
            assessment_result="accepted",
            notes="Assessment complete.",
            reason="Assessment captured.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["assessment_result"] == "accepted"
    assert result["inspection_event_id"] is not None

    with Session(engine) as session:
        row = session.scalars(select(CaseAssessment)).first()
        assert row is not None
        assert row.assessment_result == "accepted"
        assert session.scalars(select(InspectionEvent).where(InspectionEvent.event_type == "assessment_completed")).first() is not None


def test_upsert_inspection_plan_persists_stage():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        result = service.upsert_inspection_plan(
            session,
            case_id=case_id,
            plan_start_on=date(2026, 8, 20),
            plan_end_on=date(2026, 8, 22),
            planning_sheet_name="KHKT-2026-08",
            decision_document_hint=None,
            decision_reference="QD-01",
            reason="Planning baseline.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["planning_sheet_name"] == "KHKT-2026-08"

    with Session(engine) as session:
        row = session.scalars(select(InspectionPlan)).first()
        assert row is not None
        assert row.decision_document_hint is None
        assert row.decision_reference == "QD-01"


def test_upsert_inspection_plan_route_enforces_auth_and_returns_read_model(tmp_path):
    database_path = tmp_path / "workflow-plan-route.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        case_id = seed_case(session)

    app = create_app(database_url)
    route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/plan")
    payload = InspectionPlanUpsertRequest(
        expected_version=None,
        plan_start_on=date(2026, 8, 20),
        plan_end_on=date(2026, 8, 21),
        planning_sheet_name="KHKT-HTTP",
        decision_reference="QD-HTTP",
    )

    with Session(engine) as session:
        try:
            route.endpoint(
                case_id=case_id,
                payload=payload,
                session=session,
                user=build_authenticated_user("reader01", "reader"),
            )
        except Exception as exc:
            assert "missing required permission" in str(exc).lower()
        else:
            raise AssertionError("Expected reader inspection-plan upsert to fail")

    with Session(engine) as session:
        body = route.endpoint(
            case_id=case_id,
            payload=payload,
            session=session,
            user=build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"]),
        ).model_dump(mode="json")
        persisted = session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case_id))

    assert body["case_id"] == case_id
    assert persisted is not None
    assert body["row_version"] == persisted.row_version
    assert body["plan_start_on"] == "2026-08-20"


def test_upsert_inspection_plan_blocks_terminal_cases_and_skips_duplicate_event():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        first = service.upsert_inspection_plan(
            session,
            case_id=case_id,
            plan_start_on=date(2026, 8, 20),
            plan_end_on=date(2026, 8, 22),
            planning_sheet_name="KHKT-2026-08",
            decision_document_hint=None,
            decision_reference="QD-01",
            reason="Initial plan.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert first["inspection_event_id"] is not None

    with Session(engine) as session:
        second = service.upsert_inspection_plan(
            session,
            case_id=case_id,
            expected_version=first["row_version"],
            plan_start_on=date(2026, 8, 20),
            plan_end_on=date(2026, 8, 22),
            planning_sheet_name="KHKT-2026-08",
            decision_document_hint=None,
            decision_reference="QD-01",
            reason="No-op save.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert second["inspection_event_id"] is None

    with Session(engine) as session:
        events = list(session.scalars(select(InspectionEvent).where(InspectionEvent.case_id == case_id)))
        assert [event.event_type.value for event in events] == ["plan_created", "decision_issued"]
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.CLOSED
        session.commit()

    with Session(engine) as session:
        try:
            service.upsert_inspection_plan(
                session,
                case_id=case_id,
                expected_version=second["row_version"],
                plan_start_on=date(2026, 8, 23),
                plan_end_on=date(2026, 8, 24),
                planning_sheet_name="KHKT-2026-09",
                decision_document_hint=None,
                decision_reference="QD-02",
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "terminal state closed" in str(exc)
        else:
            raise AssertionError("Expected terminal inspection plan update to fail")


def test_upsert_inspection_outcome_persists_stage_and_event():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        result = service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            inspected_on=date(2026, 8, 25),
            inspected_to_on=date(2026, 8, 26),
            decision_reference=None,
            bbkt_reference=None,
            outcome_result="compliant",
            reason="Outcome recorded.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["outcome_result"] == "compliant"
    assert result["inspection_event_id"] is not None
    assert result["inspection_period_state"] == "KNOWN"

    with Session(engine) as session:
        row = session.scalars(select(InspectionOutcome)).first()
        segment = session.scalars(select(InspectionPeriodSegment)).one()
        assert row is not None
        assert row.bbkt_reference is None
        assert row.inspection_period_state == "KNOWN"
        assert (segment.ordinal, segment.started_on, segment.ended_on) == (1, date(2026, 8, 25), date(2026, 8, 26))
        assert (row.inspected_on, row.inspected_to_on) == (segment.started_on, segment.ended_on)


def test_outcome_compatibility_writer_does_not_infer_a_zero_segment_source_state():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        result = service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            inspected_on=None,
            inspected_to_on=None,
            decision_reference=None,
            bbkt_reference=None,
                outcome_result=None,
                reason="Metadata only.",
                user=build_authenticated_user("manager01", "manager"),
                fields_set=set(),
        )
        session.commit()
        row = session.scalar(select(InspectionOutcome))
    assert row is not None
    assert row.inspection_period_state is None
    assert result["inspection_period_state"] is None
    assert row.inspected_on is None


def test_outcome_compatibility_writer_normalizes_one_day_and_updates_one_canonical_segment():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        first = service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            inspected_on=date(2011, 10, 20),
            inspected_to_on=None,
            decision_reference=None,
            bbkt_reference=None,
            outcome_result=None,
            reason="One-day visit.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()
    assert (first["inspected_on"], first["inspected_to_on"], first["inspection_period_state"]) == (
        date(2011, 10, 20), date(2011, 10, 20), "KNOWN"
    )

    with Session(engine) as session:
        updated = service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            expected_version=first["row_version"],
            inspected_on=date(2011, 10, 20),
            inspected_to_on=date(2011, 10, 21),
            decision_reference=None,
            bbkt_reference=None,
            outcome_result=None,
            reason="Corrected visit.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()
        outcome = session.scalar(select(InspectionOutcome))
        segments = list(session.scalars(select(InspectionPeriodSegment)))
    assert outcome is not None
    assert updated["inspection_period_state"] == "KNOWN"
    assert [(segment.ordinal, segment.started_on, segment.ended_on) for segment in segments] == [
        (1, date(2011, 10, 20), date(2011, 10, 21))
    ]
    assert (outcome.inspected_on, outcome.inspected_to_on) == (date(2011, 10, 20), date(2011, 10, 21))


def test_outcome_compatibility_writer_metadata_only_preserves_period_truth():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        outcome = InspectionOutcome(
            case_id=case_id,
            inspection_period_state="KNOWN",
            inspected_on=date(2026, 8, 25),
            inspected_to_on=date(2026, 8, 26),
        )
        session.add(outcome)
        session.flush()
        session.add(
            InspectionPeriodSegment(
                inspection_outcome_id=outcome.id,
                ordinal=1,
                started_on=date(2026, 8, 25),
                ended_on=date(2026, 8, 26),
            )
        )
        session.commit()

    with Session(engine) as session:
        service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            inspected_on=None,
            inspected_to_on=None,
            decision_reference=None,
            bbkt_reference=None,
                outcome_result=None,
                reason="Metadata only.",
                user=build_authenticated_user("manager01", "manager"),
                fields_set=set(),
        )
        session.commit()
        outcome = session.scalar(select(InspectionOutcome))
        segments = list(session.scalars(select(InspectionPeriodSegment)))
    assert outcome is not None
    assert outcome.inspection_period_state == "KNOWN"
    assert (outcome.inspected_on, outcome.inspected_to_on) == (date(2026, 8, 25), date(2026, 8, 26))
    assert [(segment.ordinal, segment.started_on, segment.ended_on) for segment in segments] == [
        (1, date(2026, 8, 25), date(2026, 8, 26))
    ]


def test_outcome_compatibility_writer_rejects_invalid_dates_and_multi_segment_truth():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        outcome = InspectionOutcome(case_id=case_id, inspection_period_state="KNOWN")
        session.add(outcome)
        session.flush()
        for ordinal, day in ((1, 25), (2, 27)):
            session.add(
                InspectionPeriodSegment(
                    inspection_outcome_id=outcome.id,
                    ordinal=ordinal,
                    started_on=date(2026, 8, day),
                    ended_on=date(2026, 8, day),
                )
            )
        session.commit()

    with Session(engine) as session:
        with pytest.raises(Exception, match="end date requires a start date"):
            service.upsert_inspection_outcome(
                session,
                case_id=case_id,
                inspected_on=None,
                inspected_to_on=date(2026, 8, 26),
                decision_reference=None,
                bbkt_reference=None,
                outcome_result=None,
                reason=None,
                user=build_authenticated_user("manager01", "manager"),
            )
        with pytest.raises(Exception, match="multiple canonical period segments"):
            service.upsert_inspection_outcome(
                session,
                case_id=case_id,
                inspected_on=date(2026, 8, 25),
                inspected_to_on=None,
                decision_reference=None,
                bbkt_reference=None,
                outcome_result=None,
                reason=None,
                user=build_authenticated_user("manager01", "manager"),
            )


def test_outcome_compatibility_writer_does_not_replace_a_source_owned_non_known_state():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        session.add(InspectionOutcome(case_id=case_id, inspection_period_state="PENDING_INPUT"))
        session.commit()

    with Session(engine) as session:
        with pytest.raises(Exception, match="source-owned non-KNOWN"):
            service.upsert_inspection_outcome(
                session,
                case_id=case_id,
                inspected_on=date(2026, 8, 25),
                inspected_to_on=None,
                decision_reference=None,
                bbkt_reference=None,
                outcome_result=None,
                reason=None,
                user=build_authenticated_user("manager01", "manager"),
            )
        session.rollback()
        outcome = session.scalar(select(InspectionOutcome))
        assert outcome is not None
        assert outcome.inspection_period_state == "PENDING_INPUT"
        assert session.scalars(select(InspectionPeriodSegment)).all() == []


def test_outcome_timing_mutation_rolls_back_segment_and_compatibility_together(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit failure")

    monkeypatch.setattr(service, "_write_audit_event", fail_audit)
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="audit failure"):
            service.upsert_inspection_outcome(
                session,
                case_id=case_id,
                inspected_on=date(2011, 10, 20),
                inspected_to_on=None,
                decision_reference=None,
                bbkt_reference=None,
                outcome_result=None,
                reason=None,
                user=build_authenticated_user("manager01", "manager"),
            )
        session.rollback()
        assert session.scalars(select(InspectionOutcome)).all() == []
        assert session.scalars(select(InspectionPeriodSegment)).all() == []


def test_upsert_inspection_outcome_route_enforces_auth_and_returns_read_model(tmp_path):
    database_path = tmp_path / "workflow-outcome-route.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        case_id = seed_case(session)

    app = create_app(database_url)
    route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/outcome")
    payload = InspectionOutcomeUpsertRequest(
        expected_version=None,
        inspected_on=date(2026, 8, 25),
        inspected_to_on=date(2026, 8, 26),
        outcome_result="Đạt",
    )

    with Session(engine) as session:
        try:
            route.endpoint(
                case_id=case_id,
                payload=payload,
                session=session,
                user=build_authenticated_user("reader01", "reader"),
            )
        except Exception as exc:
            assert "missing required permission" in str(exc).lower()
        else:
            raise AssertionError("Expected reader inspection-outcome upsert to fail")

    with Session(engine) as session:
        body = route.endpoint(
            case_id=case_id,
            payload=payload,
            session=session,
            user=build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"]),
        ).model_dump(mode="json")
        persisted = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case_id))

    assert body["case_id"] == case_id
    assert persisted is not None
    assert body["row_version"] == persisted.row_version
    assert body["inspected_on"] == "2026-08-25"


def test_upsert_inspection_outcome_blocks_terminal_cases_and_skips_duplicate_event():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        first = service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            inspected_on=date(2026, 8, 25),
            inspected_to_on=date(2026, 8, 26),
            decision_reference=None,
            bbkt_reference=None,
            outcome_result="compliant",
            reason="Initial outcome.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert first["inspection_event_id"] is not None

    with Session(engine) as session:
        second = service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            expected_version=first["row_version"],
            inspected_on=date(2026, 8, 25),
            inspected_to_on=date(2026, 8, 26),
            decision_reference=None,
            bbkt_reference=None,
            outcome_result="compliant",
            reason="No-op save.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert second["inspection_event_id"] is None

    with Session(engine) as session:
        events = list(session.scalars(select(InspectionEvent).where(InspectionEvent.case_id == case_id)))
        assert [event.event_type for event in events] == ["outcome_recorded"]
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.CANCELLED
        session.commit()

    with Session(engine) as session:
        try:
            service.upsert_inspection_outcome(
                session,
                case_id=case_id,
                expected_version=second["row_version"],
                inspected_on=date(2026, 8, 27),
                inspected_to_on=date(2026, 8, 28),
                decision_reference=None,
                bbkt_reference=None,
                outcome_result="needs-follow-up",
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "terminal state cancelled" in str(exc)
        else:
            raise AssertionError("Expected terminal inspection outcome update to fail")


def test_upsert_inspection_team_replaces_member_list_and_writes_audit():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        identities = seed_inspection_team_identities(session)
        session.commit()

    with Session(engine) as session:
        result = service.upsert_inspection_team(
            session,
            case_id=case_id,
            members=[
                {"person_id": None, "inspector_profile_id": identities["profile_id"], "role_code": "LEADER", "role_label": "lead", "sort_order": 1},
                {"person_id": identities["direct_person_id"], "inspector_profile_id": None, "role_code": "SECRETARY", "role_label": "member", "sort_order": 2},
            ],
            reason="Initial team assignment.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["team_id"] is not None
    assert len(result["members"]) == 2
    assert [member["role_code"] for member in result["members"]] == ["LEADER", "SECRETARY"]
    assert result["audit_event_id"] is not None

    with Session(engine) as session:
        team = session.scalars(select(InspectionTeam)).first()
        assert team is not None
        assert team.display_text is None
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id).order_by(InspectionTeamMember.sort_order)))
        assert len(members) == 2
        assert session.scalars(select(AuditEvent).where(AuditEvent.action == "inspection_team.upsert")).first() is not None

    with Session(engine) as session:
        service.upsert_inspection_team(
            session,
            case_id=case_id,
            expected_version=result["row_version"],
            members=[
                {"person_id": None, "inspector_profile_id": identities["profile_id"], "role_code": "SECRETARY", "role_label": "chair", "sort_order": 2},
                {"person_id": identities["direct_person_id"], "inspector_profile_id": None, "role_code": "LEADER", "role_label": "member", "sort_order": 1},
            ],
            reason="Team narrowed.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        team = session.scalars(select(InspectionTeam)).first()
        assert team is not None
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id).order_by(InspectionTeamMember.sort_order)))
        assert [(member.inspector_profile_id, member.person_id, member.role_label, member.sort_order) for member in members] == [
            (None, identities["direct_person_id"], "member", 1),
            (identities["profile_id"], None, "chair", 2),
        ]


def test_upsert_inspection_team_route_serializes_role_code(tmp_path):
    database_path = tmp_path / "workflow-team-route.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        case_id = seed_case(session)
        identities = seed_inspection_team_identities(session)
        session.commit()

    app = create_app(database_url)
    route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/team")
    payload = InspectionTeamUpsertRequest(
        members=[
            {"person_id": None, "inspector_profile_id": identities["profile_id"], "role_code": "LEADER", "role_label": "lead", "sort_order": 1},
            {"person_id": identities["direct_person_id"], "inspector_profile_id": None, "role_code": "SECRETARY", "role_label": "secretary", "sort_order": 2},
        ]
    )
    with Session(engine) as session:
        body = route.endpoint(
            case_id=case_id,
            payload=payload,
            session=session,
            user=build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"]),
        ).model_dump(mode="json")

    assert [member["role_code"] for member in body["members"]] == ["LEADER", "SECRETARY"]


def test_upsert_inspection_team_rejects_member_without_identity():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        try:
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                members=[
                    {"person_id": None, "inspector_profile_id": None, "role_code": "LEADER", "role_label": "lead", "sort_order": 1},
                ],
                reason="Invalid payload.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "exactly one" in str(exc)
        else:
            raise AssertionError("Expected invalid inspection team member to fail")


def test_upsert_inspection_team_rejects_inactive_inspector_profile_for_runtime_composition():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        identities = seed_inspection_team_identities(session)
        profile = session.get(InspectorProfile, identities["profile_id"])
        assert profile is not None
        profile.is_active = False
        session.commit()

    with Session(engine) as session:
        with pytest.raises(Exception, match="inactive_inspector_profile"):
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                members=[
                    {
                        "person_id": None,
                        "inspector_profile_id": identities["profile_id"],
                        "role_code": "LEADER",
                        "role_label": "lead",
                        "sort_order": 1,
                    },
                ],
                reason="Inactive profile cannot compose a current team.",
                user=build_authenticated_user("manager01", "manager"),
            )
        with pytest.raises(Exception, match="inspector_profile-owned"):
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                members=[
                    {
                        "person_id": identities["inspector_person_id"],
                        "inspector_profile_id": None,
                        "role_code": "LEADER",
                        "role_label": "lead",
                        "sort_order": 1,
                    },
                ],
                reason="Inactive inspector cannot bypass profile identity through Person.",
                user=build_authenticated_user("manager01", "manager"),
            )
        assert session.scalars(select(InspectionTeam).where(InspectionTeam.case_id == case_id)).first() is None


def test_upsert_inspection_team_rejects_active_inspector_person_compatibility_bypass():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        identities = seed_inspection_team_identities(session)
        session.commit()

    with Session(engine) as session:
        with pytest.raises(Exception, match="inspector_profile-owned"):
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                members=[
                    {
                        "person_id": identities["inspector_person_id"],
                        "inspector_profile_id": None,
                        "role_code": "LEADER",
                        "role_label": "lead",
                        "sort_order": 1,
                    },
                ],
                reason="Inspector must use the inspector profile identity.",
                user=build_authenticated_user("manager01", "manager"),
            )
        result = service.upsert_inspection_team(
            session,
            case_id=case_id,
            members=[
                {
                    "person_id": identities["direct_person_id"],
                    "inspector_profile_id": None,
                    "role_code": "LEADER",
                    "role_label": "lead",
                    "sort_order": 1,
                },
            ],
            reason="A non-inspector Person remains a compatibility identity.",
            user=build_authenticated_user("manager01", "manager"),
        )
        assert result["members"][0]["person_id"] == identities["direct_person_id"]


def test_upsert_inspection_team_rejects_display_text_as_a_second_member_source():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        identities = seed_inspection_team_identities(session)
        with pytest.raises(Exception, match="legacy snapshot"):
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                display_text="Do not parse me",
                members=[{"person_id": identities["direct_person_id"], "inspector_profile_id": None, "role_code": "LEADER", "role_label": "lead", "sort_order": 1}],
                reason="Invalid dual source.",
                user=build_authenticated_user("manager01", "manager"),
            )


def test_upsert_inspection_team_rejects_unknown_identity_and_stale_version_without_data_loss():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        identities = seed_inspection_team_identities(session)
        team = InspectionTeam(case_id=case_id, display_text="Legacy snapshot")
        session.add(team)
        session.flush()
        session.add(InspectionTeamMember(team_id=team.id, inspector_profile_id=identities["profile_id"], person_id=None, role_label="lead", sort_order=0))
        session.commit()

    with Session(engine) as session:
        try:
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                expected_version=1,
                members=[{"person_id": "00000000-0000-0000-0000-0000000000ff", "inspector_profile_id": None, "role_code": "LEADER", "role_label": "lead", "sort_order": 1}],
                reason="Invalid identity.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "unknown identity" in str(exc)
        else:
            raise AssertionError("Expected unknown inspection team identity to fail")
        session.rollback()

        updated = service.upsert_inspection_team(
            session,
            case_id=case_id,
            expected_version=1,
            members=[{"person_id": identities["direct_person_id"], "inspector_profile_id": None, "role_code": "LEADER", "role_label": "lead", "sort_order": 1}],
            reason="Replace member from authoritative projection.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                expected_version=1,
                members=[{"person_id": identities["direct_person_id"], "inspector_profile_id": None, "role_code": "LEADER", "role_label": "member", "sort_order": 1}],
                reason="Stale write.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "Stale inspection_team update" in str(exc)
        else:
            raise AssertionError("Expected stale inspection team update to fail")

    assert updated["row_version"] == 2
    with Session(engine) as session:
        team = session.scalars(select(InspectionTeam).where(InspectionTeam.case_id == case_id)).one()
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id)))
        assert team.display_text == "Legacy snapshot"
        assert [(member.person_id, member.role_label) for member in members] == [(identities["direct_person_id"], "lead")]


def test_upsert_inspection_team_blocks_terminal_case_before_replacing_members():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        team = InspectionTeam(case_id=case_id, display_text="Legacy team")
        session.add(team)
        session.flush()
        session.add(
            InspectionTeamMember(
                team_id=team.id,
                person_id="00000000-0000-0000-0000-0000000000a1",
                inspector_profile_id=None,
                role_label="lead",
                sort_order=1,
            )
        )
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.CLOSED
        session.commit()

    with Session(engine) as session:
        try:
            service.upsert_inspection_team(
                session,
                case_id=case_id,
                expected_version=1,
                members=[
                    {
                        "person_id": "00000000-0000-0000-0000-0000000000b2",
                        "inspector_profile_id": None,
                        "role_label": "member",
                        "sort_order": 1,
                    },
                ],
                reason="Blocked terminal case.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "terminal state closed" in str(exc)
        else:
            raise AssertionError("Expected terminal inspection team update to fail")

    with Session(engine) as session:
        team = session.scalars(select(InspectionTeam).where(InspectionTeam.case_id == case_id)).first()
        assert team is not None
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id)))
        assert team.display_text == "Legacy team"
        assert len(members) == 1


def test_capa_cycle_workflow_blocks_case_transition_until_latest_round_accepted():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        session.commit()

    with Session(engine) as session:
        created = service.create_capa_cycle(
            session,
            case_id=case_id,
            requested_on=date(2026, 8, 18),
            notes="Round 1 requested.",
            reason="Need corrective actions.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert created["round_no"] == 1
    assert created["status"] == "requested"
    assert created["row_version"] == 1

    with Session(engine) as session:
        listed = service.list_capa_cycles(session, case_id=case_id)
        assert len(listed) == 1
        assert listed[0]["capa_cycle_id"] == created["capa_cycle_id"]
        assert listed[0]["row_version"] == 1
        try:
            service.transition_case(
                session,
                case_id=case_id,
                target_state="awaiting_certificate_decision",
                reason="Should still be blocked.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "CAPA remains required or unaccepted" in str(exc)
        else:
            raise AssertionError("Expected pending CAPA to block transition")

    with Session(engine) as session:
        submitted = service.submit_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=created["row_version"],
            submitted_on=date(2026, 8, 19),
            notes="Submitted round 1.",
            reason="Operator submitted CAPA.",
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        rejected = service.assess_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=submitted["row_version"],
            assessed_on=date(2026, 8, 20),
            assessor_name="Assessor A",
            result="rejected",
            notes="Need another round.",
            reason="Round 1 rejected.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert rejected["status"] == "rejected"

    with Session(engine) as session:
        second_round = service.create_capa_cycle(
            session,
            case_id=case_id,
            requested_on=date(2026, 8, 21),
            notes="Round 2 requested.",
            reason="Follow-up CAPA.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert second_round["round_no"] == 2

    with Session(engine) as session:
        submitted_round_2 = service.submit_capa_cycle(
            session,
            capa_cycle_id=second_round["capa_cycle_id"],
            expected_version=second_round["row_version"],
            submitted_on=date(2026, 8, 22),
            notes="Submitted round 2.",
            reason="Round 2 submit.",
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        accepted = service.assess_capa_cycle(
            session,
            capa_cycle_id=second_round["capa_cycle_id"],
            expected_version=submitted_round_2["row_version"],
            assessed_on=date(2026, 8, 23),
            assessor_name="Assessor B",
            result="accepted",
            notes="CAPA accepted.",
            reason="Round 2 accepted.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert accepted["status"] == "accepted"

    with Session(engine) as session:
        transitioned = service.transition_case(
            session,
            case_id=case_id,
            target_state="awaiting_certificate_decision",
            reason="CAPA done.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert transitioned["current_state"] == "awaiting_certificate_decision"


def test_create_capa_cycle_rejects_case_already_awaiting_certificate_decision():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        session.commit()

    with Session(engine) as session:
        try:
            service.create_capa_cycle(
                session,
                case_id=case_id,
                requested_on=date(2026, 8, 24),
                notes="Should fail.",
                reason="Late CAPA request.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "inspection_completed" in str(exc)
        else:
            raise AssertionError("Expected CAPA creation in awaiting_certificate_decision to fail")


def test_create_capa_cycle_route_enforces_permission_and_returns_read_model(tmp_path):
    database_path = tmp_path / "workflow-capa-create-route.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        session.commit()

    app = create_app(database_url)
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", "") == "/cases/{case_id}/capa-cycles" and "POST" in getattr(route, "methods", set())
    )
    payload = CapaCycleCreateRequest(
        expected_case_version=2,
        requested_on=date(2026, 8, 24),
        notes="Tạo vòng CAPA",
    )

    with Session(engine) as session:
        try:
            route.endpoint(
                case_id=case_id,
                payload=payload,
                session=session,
                user=build_authenticated_user("reader01", "reader"),
            )
        except Exception as exc:
            assert "missing required permission" in str(exc).lower()
        else:
            raise AssertionError("Expected reader CAPA create to fail")

    with Session(engine) as session:
        body = route.endpoint(
            case_id=case_id,
            payload=payload,
            session=session,
            user=build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"]),
        ).model_dump(mode="json")

    assert body["case_id"] == case_id
    assert body["round_no"] == 1
    assert body["row_version"] == 1


def test_update_capa_cycle_rejects_mutation_after_acceptance():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        session.commit()

    with Session(engine) as session:
        created = service.create_capa_cycle(
            session,
            case_id=case_id,
            requested_on=date(2026, 8, 18),
            notes="Round 1.",
            reason="Need CAPA.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        submitted = service.submit_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=created["row_version"],
            submitted_on=date(2026, 8, 19),
            notes="Submitted.",
            reason="Submit.",
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        accepted = service.assess_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=submitted["row_version"],
            assessed_on=date(2026, 8, 20),
            assessor_name="Assessor",
            result="accepted",
            notes="Accepted.",
            reason="Assess.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.update_capa_cycle(
                session,
                capa_cycle_id=created["capa_cycle_id"],
                expected_version=accepted["row_version"],
                requested_on=date(2026, 8, 18),
                notes="Should fail.",
                reason="Attempt mutate accepted cycle.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "requested or rejected" in str(exc)
        else:
            raise AssertionError("Expected accepted CAPA cycle to reject updates")


def test_update_capa_cycle_rejects_mutation_while_submitted():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        session.commit()

    with Session(engine) as session:
        created = service.create_capa_cycle(
            session,
            case_id=case_id,
            requested_on=date(2026, 8, 18),
            notes="Round 1.",
            reason="Need CAPA.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        submitted = service.submit_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=created["row_version"],
            submitted_on=date(2026, 8, 19),
            notes="Submitted.",
            reason="Submit.",
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.update_capa_cycle(
                session,
                capa_cycle_id=created["capa_cycle_id"],
                expected_version=submitted["row_version"],
                requested_on=date(2026, 8, 18),
                notes="Should fail.",
                reason="Attempt mutate submitted cycle.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "requested or rejected" in str(exc)
        else:
            raise AssertionError("Expected submitted CAPA cycle to reject updates")


def test_capa_mutations_block_terminal_case():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        session.commit()

    with Session(engine) as session:
        created = service.create_capa_cycle(
            session,
            case_id=case_id,
            requested_on=date(2026, 8, 18),
            notes="Round 1.",
            reason="Need CAPA.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.CLOSED
        session.commit()

    with Session(engine) as session:
        for action in (
            lambda: service.create_capa_cycle(
                session,
                case_id=case_id,
                expected_case_version=created["row_version"],
                requested_on=date(2026, 8, 24),
                notes="Should fail.",
                reason="Terminal create.",
                user=build_authenticated_user("manager01", "manager"),
            ),
            lambda: service.update_capa_cycle(
                session,
                capa_cycle_id=created["capa_cycle_id"],
                expected_version=created["row_version"],
                requested_on=date(2026, 8, 18),
                notes="Should fail.",
                reason="Terminal update.",
                user=build_authenticated_user("manager01", "manager"),
            ),
            lambda: service.submit_capa_cycle(
                session,
                capa_cycle_id=created["capa_cycle_id"],
                expected_version=created["row_version"],
                submitted_on=date(2026, 8, 19),
                notes="Should fail.",
                reason="Terminal submit.",
                user=build_authenticated_user("inspector01", "inspector"),
            ),
        ):
            try:
                action()
            except Exception as exc:
                assert "terminal state closed" in str(exc)
            else:
                raise AssertionError("Expected terminal CAPA mutation to fail")

    with Session(engine) as session:
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        session.commit()

    with Session(engine) as session:
        submitted = service.submit_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=created["row_version"],
            submitted_on=date(2026, 8, 19),
            notes="Submitted.",
            reason="Submit.",
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.CANCELLED
        session.commit()

    with Session(engine) as session:
        try:
            service.assess_capa_cycle(
                session,
                capa_cycle_id=created["capa_cycle_id"],
                expected_version=submitted["row_version"],
                assessed_on=date(2026, 8, 20),
                assessor_name="Should not persist",
                result="accepted",
                notes="Should fail.",
                reason="Terminal assess.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "terminal state cancelled" in str(exc)
        else:
            raise AssertionError("Expected terminal CAPA assess to fail")


def test_issue_certificate_allows_administrative_no_case_and_persists_scope():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.commit()

    with Session(engine) as session:
        result = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=None,
            certificate_type="GMP",
            issuance_basis="administrative_no_inspection",
            certificate_number="CERT-001",
            issue_date=date(2026, 8, 15),
            expiry_date=date(2027, 8, 15),
            scopes=[
                {"scope_key": "line_1", "scope_text": "Tablet line", "language_code": "vi", "sort_order": 1},
            ],
            reason="Administrative reissue.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["case_id"] is None
    assert result["latest_flag"] is False
    assert len(result["scopes"]) == 1
    assert result["inspection_event_id"] is None

    with Session(engine) as session:
        certificate = session.scalars(select(Certificate)).one()
        assert certificate.case_id is None
        assert certificate.issuance_basis == "administrative_no_inspection"
        version = session.scalars(select(CertificateVersion)).one()
        assert version.certificate_number == "CERT-001"
        scope = session.scalars(select(CertificateScope)).one()
        assert scope.scope_text == "Tablet line"


def test_issue_certificate_rejects_inspection_basis_without_case():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.commit()

    with Session(engine) as session:
        try:
            service.issue_certificate(
                session,
                site_id=site_id,
                case_id=None,
                certificate_type="GMP",
                issuance_basis="inspection_case",
                certificate_number="CERT-002",
                issue_date=date(2026, 8, 16),
                expiry_date=date(2027, 8, 16),
                scopes=[],
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "requires a backing case_id" in str(exc)
        else:
            raise AssertionError("Expected inspection_case issuance without case to fail")


def test_issue_certificate_rejects_certificate_type_mismatching_backing_case():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.commit()

    with Session(engine) as session:
        try:
            service.issue_certificate(
                session,
                site_id=site_id,
                case_id=case_id,
                certificate_type="GSP",
                issuance_basis="inspection_case",
                certificate_number="CERT-TYPE-MISMATCH",
                issue_date=date(2026, 8, 16),
                expiry_date=date(2027, 8, 16),
                scopes=[],
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "certificate_type must match" in str(exc)
        else:
            raise AssertionError("Expected inspection_case issuance with a mismatched certificate type to fail")


@pytest.mark.parametrize("gxp_type", ["GLP", "GMPbb"])
def test_issue_certificate_accepts_matching_non_gmp_case_type(gxp_type: str):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session, gxp_type=gxp_type)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.commit()

    with Session(engine) as session:
        result = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=case_id,
            certificate_type=gxp_type,
            issuance_basis="inspection_case",
            certificate_number=f"CERT-{gxp_type}",
            issue_date=date(2026, 8, 16),
            expiry_date=date(2027, 8, 16),
            scopes=[],
            reason="Matching case type.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["certificate_type"] == gxp_type


def test_issue_certificate_rejects_case_not_yet_awaiting_certificate_decision():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        site_id = case_row.site_id
        session.commit()

    with Session(engine) as session:
        try:
            service.issue_certificate(
                session,
                site_id=site_id,
                case_id=case_id,
                certificate_type="GMP",
                issuance_basis="inspection_case",
                certificate_number="CERT-STATE-001",
                issue_date=date(2026, 8, 16),
                expiry_date=date(2027, 8, 16),
                scopes=[],
                reason="Too early.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "awaiting_certificate_decision" in str(exc)
        else:
            raise AssertionError("Expected inspection_case issuance before awaiting state to fail")


def test_issue_certificate_rejects_pending_capa_for_case_backed_certificate():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.add(
            CapaCycle(
                case_id=case_id,
                round_no=1,
                requested_on=date(2026, 8, 15),
                status="submitted",
            )
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.issue_certificate(
                session,
                site_id=site_id,
                case_id=case_id,
                certificate_type="GMP",
                issuance_basis="inspection_case",
                certificate_number="CERT-CAPA-001",
                issue_date=date(2026, 8, 16),
                expiry_date=date(2027, 8, 16),
                scopes=[],
                reason="Blocked by CAPA.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "latest CAPA cycle is accepted" in str(exc)
        else:
            raise AssertionError("Expected pending CAPA to block case-backed certificate issuance")


def test_issue_certificate_allows_case_backed_certificate_when_latest_capa_is_accepted():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.add(
            CapaCycle(
                case_id=case_id,
                round_no=1,
                requested_on=date(2026, 8, 15),
                submitted_on=date(2026, 8, 16),
                assessed_on=date(2026, 8, 17),
                status="accepted",
                result="accepted",
                assessor_name="manager01",
            )
        )
        session.commit()

    with Session(engine) as session:
        result = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=case_id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            certificate_number="CERT-CAPA-OK",
            issue_date=date(2026, 8, 18),
            expiry_date=date(2027, 8, 18),
            scopes=[],
            reason="CAPA accepted.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["case_id"] == case_id


def test_certificate_action_readiness_uses_the_same_promotion_blockers_as_mutation():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        issued = service.issue_certificate(
            session,
            site_id=case_row.site_id,
            case_id=case_id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            certificate_number="CERT-READY-001",
            issue_date=date(2026, 8, 18),
            expiry_date=date(2027, 8, 18),
            scopes=[],
            reason="Seed readiness.",
            user=build_authenticated_user("admin01", "admin"),
        )
        session.commit()

    manager = build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"])
    admin = build_authenticated_user("admin01", "admin", permissions=ROLE_PERMISSIONS["admin"])
    reader = build_authenticated_user("reader01", "reader", permissions=ROLE_PERMISSIONS["reader"])
    with Session(engine) as session:
        issue_action = service.get_case_certificate_issue_readiness(
            session,
            case_id=case_id,
            user=admin,
        )
        assert issue_action["available"] is True
        assert issue_action["certificate_type"] == "GMP"
        actions = {item["action_key"]: item for item in service.get_certificate_action_readiness(
            session,
            certificate_id=issued["certificate_id"],
            user=manager,
        )}
        assert actions["edit_latest_version"]["available"] is True
        assert actions["promote_current"]["available"] is True
        assert actions["promote_current"]["expected_version"] == issued["row_version"]
        reader_actions = {item["action_key"]: item for item in service.get_certificate_action_readiness(
            session,
            certificate_id=issued["certificate_id"],
            user=reader,
        )}
        assert reader_actions["edit_latest_version"]["reason_code"] == "missing_permission"
        assert reader_actions["promote_current"]["reason_code"] == "missing_permission"

        session.add(CapaCycle(case_id=case_id, round_no=1, status="submitted"))
        session.commit()

    with Session(engine) as session:
        issue_action = service.get_case_certificate_issue_readiness(
            session,
            case_id=case_id,
            user=admin,
        )
        assert issue_action["reason_code"] == "latest_capa_not_accepted"
        actions = {item["action_key"]: item for item in service.get_certificate_action_readiness(
            session,
            certificate_id=issued["certificate_id"],
            user=manager,
        )}
        assert actions["promote_current"]["reason_code"] == "latest_capa_not_accepted"
        try:
            service.promote_certificate_current(
                session,
                certificate_id=issued["certificate_id"],
                expected_version=issued["row_version"],
                reason="Must remain blocked.",
                user=manager,
            )
        except Exception as exc:
            assert "latest CAPA cycle is accepted" in str(exc)
        else:
            raise AssertionError("Expected promotion to use the readiness blocker")

        try:
            service.promote_certificate_current(
                session,
                certificate_id=issued["certificate_id"],
                expected_version=999,
                reason="Stale update.",
                user=manager,
            )
        except Exception as exc:
            assert "Stale certificate update" in str(exc)
        else:
            raise AssertionError("Expected stale certificate promotion to fail")


def test_certificate_latest_version_round_trips_structured_scopes_and_bumps_certificate_version():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        case.state = CaseState.AWAITING_CERTIFICATE_DECISION
        issued = service.issue_certificate(
            session, site_id=case.site_id, case_id=case_id, certificate_type="GMP", issuance_basis="inspection_case",
            certificate_number="CERT-SCOPE", issue_date=date(2026, 8, 1), expiry_date=date(2027, 8, 1),
            scopes=[{"scope_key": "a", "scope_text": "A", "language_code": "vi", "sort_order": 2}, {"scope_key": "b", "scope_text": "B", "language_code": "en", "sort_order": 1}],
            reason="Seed.", user=build_authenticated_user("admin01", "admin"),
        )
        session.commit()
    with Session(engine) as session:
        updated = service.upsert_certificate_latest_version(
            session, certificate_id=issued["certificate_id"], expected_version=issued["row_version"],
            certificate_number="CERT-SCOPE", issue_date=date(2026, 8, 1), expiry_date=date(2027, 8, 1),
            scopes=[{"scope_key": "b", "scope_text": "B", "language_code": "en", "sort_order": 1}, {"scope_key": "a", "scope_text": "A", "language_code": "vi", "sort_order": 2}],
            reason="Round trip.", user=build_authenticated_user("admin01", "admin"),
        )
        session.commit()
    assert updated["row_version"] > issued["row_version"]
    assert [(item["scope_key"], item["language_code"], item["sort_order"]) for item in updated["scopes"]] == [("b", "en", 1), ("a", "vi", 2)]


def test_promote_certificate_current_rejects_pending_capa_for_case_backed_certificate():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.add(
            CapaCycle(
                case_id=case_id,
                round_no=1,
                requested_on=date(2026, 8, 15),
                status="requested",
            )
        )
        session.commit()

    with Session(engine) as session:
        issued = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=None,
            certificate_type="GMP",
            issuance_basis="administrative_no_inspection",
            certificate_number="CERT-PROMOTE-BLOCK",
            issue_date=date(2026, 8, 18),
            expiry_date=date(2027, 8, 18),
            scopes=[],
            reason="Seed cert.",
            user=build_authenticated_user("manager01", "manager"),
        )
        certificate = session.get(Certificate, issued["certificate_id"])
        assert certificate is not None
        certificate.case_id = case_id
        certificate.issuance_basis = "inspection_case"
        session.commit()

    with Session(engine) as session:
        try:
            service.promote_certificate_current(
                session,
                certificate_id=issued["certificate_id"],
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "latest CAPA cycle is accepted" in str(exc)
        else:
            raise AssertionError("Expected pending CAPA to block current promotion")


def test_assess_capa_cycle_binds_assessor_to_authenticated_actor():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        session.commit()

    with Session(engine) as session:
        created = service.create_capa_cycle(
            session,
            case_id=case_id,
            requested_on=date(2026, 8, 18),
            notes="Round 1.",
            reason="Need CAPA.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        submitted = service.submit_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=created["row_version"],
            submitted_on=date(2026, 8, 19),
            notes="Submitted.",
            reason="Submit.",
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    with Session(engine) as session:
        assessed = service.assess_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=submitted["row_version"],
            assessed_on=date(2026, 8, 20),
            assessor_name="Fake Client Value",
            result="accepted",
            notes="Accepted.",
            reason="Assess.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert assessed["assessor_name"] == "manager01"
    assert assessed["assessor_user_id"] is not None

    with Session(engine) as session:
        row = session.get(CapaCycle, created["capa_cycle_id"])
        assert row is not None
        assert row.assessor_name == "manager01"
        actor = session.get(AuditEvent, assessed["audit_event_id"])
        assert actor is not None
        payload = json.loads(actor.payload_redacted)
        assert payload["assessor_name_input"] == "Fake Client Value"
        assert payload["assessor_name_resolved"] == "manager01"
        assert payload["assessor_user_id"] == row.assessor_user_id


def test_assess_capa_cycle_route_requires_capa_assess_permission(tmp_path):
    database_path = tmp_path / "workflow-capa-assess-route.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.INSPECTION_COMPLETED
        created = service.create_capa_cycle(
            session,
            case_id=case_id,
            requested_on=date(2026, 8, 18),
            notes="Round 1.",
            reason="Need CAPA.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        submitted = service.submit_capa_cycle(
            session,
            capa_cycle_id=created["capa_cycle_id"],
            expected_version=created["row_version"],
            submitted_on=date(2026, 8, 19),
            notes="Submitted.",
            reason="Submit.",
            user=build_authenticated_user("inspector01", "inspector"),
        )
        session.commit()

    app = create_app(database_url)
    route = next(route for route in app.routes if getattr(route, "path", "") == "/capa-cycles/{capa_cycle_id}/assess")
    payload = CapaCycleAssessRequest(
        expected_version=submitted["row_version"],
        assessed_on=date(2026, 8, 20),
        assessor_name="Client supplied",
        result="accepted",
        notes="Accepted.",
    )

    with Session(engine) as session:
        try:
            route.endpoint(
                capa_cycle_id=created["capa_cycle_id"],
                payload=payload,
                session=session,
                user=build_authenticated_user("inspector01", "inspector", permissions=ROLE_PERMISSIONS["inspector"]),
            )
        except Exception as exc:
            assert "missing required permission" in str(exc).lower()
        else:
            raise AssertionError("Expected inspector assess route to fail without capa.assess")

    with Session(engine) as session:
        body = route.endpoint(
            capa_cycle_id=created["capa_cycle_id"],
            payload=payload,
            session=session,
            user=build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"]),
        ).model_dump(mode="json")

    assert body["status"] == "accepted"
    assert body["assessor_name"] == "manager01"


def test_transition_case_to_certified_rejects_latest_rejected_capa():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        session.add(
            CapaCycle(
                case_id=case_id,
                round_no=1,
                requested_on=date(2026, 8, 18),
                submitted_on=date(2026, 8, 19),
                assessed_on=date(2026, 8, 20),
                assessor_name="manager01",
                result="rejected",
                status="rejected",
            )
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.transition_case(
                session,
                case_id=case_id,
                target_state="certified",
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "CAPA remains required or unaccepted" in str(exc)
        else:
            raise AssertionError("Expected rejected CAPA to block certified transition")


def test_transition_case_to_certified_allows_no_capa_when_workflow_state_is_correct():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        session.commit()

    with Session(engine) as session:
        result = service.transition_case(
            session,
            case_id=case_id,
            target_state="certified",
            reason="Eligible.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["current_state"] == "certified"


def test_non_latest_capa_cycle_is_historical_and_cannot_be_reopened():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        case.state = CaseState.INSPECTION_COMPLETED
        first = CapaCycle(case_id=case_id, round_no=1, status="rejected", result="rejected")
        second = CapaCycle(case_id=case_id, round_no=2, status="requested")
        session.add_all([first, second])
        session.commit()
        with pytest.raises(HTTPException, match="latest CAPA cycle"):
            service.update_capa_cycle(
                session, capa_cycle_id=first.id, expected_version=first.row_version,
                requested_on=None, incoming_reference=None, notes=None, reason=None,
                user=build_authenticated_user("manager01", "manager"),
            )
        with pytest.raises(HTTPException, match="latest CAPA cycle"):
            service.submit_capa_cycle(
                session, capa_cycle_id=first.id, expected_version=first.row_version,
                submitted_on=date(2026, 10, 1), notes=None, reason=None,
                user=build_authenticated_user("manager01", "manager"),
            )


def test_promote_certificate_current_rejects_older_candidate_than_current():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.commit()

    with Session(engine) as session:
        current_result = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=case_id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            certificate_number="CERT-100",
            issue_date=date(2026, 8, 16),
            expiry_date=date(2027, 8, 16),
            scopes=[],
            reason="Current baseline.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        promoted = service.promote_certificate_current(
            session,
            certificate_id=current_result["certificate_id"],
            reason="Promote current baseline.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert promoted["latest_flag"] is True

    with Session(engine) as session:
        older_candidate = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=case_id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            certificate_number="CERT-099",
            issue_date=date(2026, 8, 10),
            expiry_date=date(2027, 8, 10),
            scopes=[],
            reason="Older successor.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        try:
            service.promote_certificate_current(
                session,
                certificate_id=older_candidate["certificate_id"],
                reason="Should fail.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "not older than the current active certificate" in str(exc)
        else:
            raise AssertionError("Expected older certificate promotion to fail")


def test_certificate_promotion_isolated_by_canonical_production_line_uuid_and_returns_identity():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("admin01", "admin")

    with Session(engine) as session:
        company = Company(legal_name="Promotion identity", short_name="PI")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Promotion site")
        session.add(site)
        session.flush()
        p1 = ProductionLine(site_id=site.id, code="A", effective_from=date(2020, 1, 1))
        p2 = ProductionLine(site_id=site.id, code="A", effective_from=date(2021, 1, 1))
        session.add_all([p1, p2])
        session.flush()

        def add_certificate(line_id, current, number, issued):
            certificate = Certificate(site_id=site.id, certificate_type="GMP", production_line_id=line_id, line_code="A", latest_flag=current)
            session.add(certificate)
            session.flush()
            session.add(CertificateVersion(certificate_id=certificate.id, version_no=1, certificate_number=number, issue_date=issued, expiry_date=date(2027, 9, 1), is_latest_version=True))
            return certificate

        first_current = add_certificate(p1.id, True, "P1-CURRENT", date(2026, 9, 20))
        second_current = add_certificate(p2.id, True, "P2-CURRENT", date(2026, 8, 1))
        second_candidate = add_certificate(p2.id, False, "P2-CANDIDATE", date(2026, 9, 1))
        session.commit()
        candidate_id, first_id, second_id, p2_id = second_candidate.id, first_current.id, second_current.id, p2.id

    with Session(engine) as session:
        result = service.promote_certificate_current(session, certificate_id=candidate_id, reason="Same-code UUID isolation.", user=user)
        session.commit()
        assert session.get(Certificate, first_id).latest_flag is True
        assert session.get(Certificate, second_id).latest_flag is False
        assert session.get(Certificate, candidate_id).latest_flag is True

    from backend.app.read_models import CertificateMutationRead
    response = CertificateMutationRead(**result)
    assert response.production_line_id == p2_id
    assert response.production_line_code == "A"
    assert response.production_line_identity_state == "canonical"


def test_certificate_promotion_keeps_canonical_legacy_and_facility_contexts_isolated():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        company = Company(legal_name="Context isolation", short_name="CTX")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Context site")
        session.add(site); session.flush()
        line = ProductionLine(site_id=site.id, code="A", effective_from=date(2020, 1, 1))
        session.add(line); session.flush()
        def certificate(line_id, raw, current, number, issued):
            row = Certificate(site_id=site.id, certificate_type="GMP", production_line_id=line_id, line_code=raw, latest_flag=current)
            session.add(row); session.flush()
            session.add(CertificateVersion(certificate_id=row.id, version_no=1, certificate_number=number, issue_date=issued, expiry_date=date(2027, 1, 1), is_latest_version=True))
            return row
        canonical_current = certificate(line.id, "A", True, "C0", date(2026, 10, 1))
        canonical_candidate = certificate(line.id, "A", False, "C1", date(2026, 10, 2))
        legacy_current = certificate(None, "A", True, "L0", date(2026, 12, 1))
        legacy_candidate = certificate(None, "A", False, "L1", date(2026, 12, 2))
        facility_current = certificate(None, None, True, "F0", date(2027, 1, 1))
        facility_candidate = certificate(None, None, False, "F1", date(2027, 1, 2))
        session.commit()
        ids = [row.id for row in (canonical_current, canonical_candidate, legacy_current, legacy_candidate, facility_current, facility_candidate)]
    for candidate_index, prior_index, untouched in ((1, 0, (2, 4)), (3, 2, (1, 4)), (5, 4, (1, 3))):
        with Session(engine) as session:
            service.promote_certificate_current(session, certificate_id=ids[candidate_index], reason="Context isolation.", user=user)
            session.commit()
            assert session.get(Certificate, ids[prior_index]).latest_flag is False
            assert session.get(Certificate, ids[candidate_index]).latest_flag is True
            for index in untouched:
                assert session.get(Certificate, ids[index]).latest_flag is True


def test_certificate_promotion_normalizes_legacy_trim_and_facility_blank_peers():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        company = Company(legal_name="Normalization", short_name="NORM")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Normalization site")
        session.add(site); session.flush()
        def add(raw, current, number):
            row = Certificate(site_id=site.id, certificate_type="GMP", line_code=raw, latest_flag=current)
            session.add(row); session.flush()
            session.add(CertificateVersion(certificate_id=row.id, version_no=1, certificate_number=number, issue_date=date(2026, 1, 1), expiry_date=date(2027, 1, 1), is_latest_version=True))
            return row
        legacy_current = add("a", True, "L0")
        legacy_candidate = add(" a ", False, "L1")
        facility_current = add("   ", True, "F0")
        facility_candidate = add(None, False, "F1")
        session.commit(); ids = [row.id for row in (legacy_current, legacy_candidate, facility_current, facility_candidate)]
    for current_index, candidate_index in ((0, 1), (2, 3)):
        with Session(engine) as session:
            service.promote_certificate_current(session, certificate_id=ids[candidate_index], reason="Normalize peers.", user=user)
            session.commit()
            assert session.get(Certificate, ids[current_index]).latest_flag is False
            assert session.get(Certificate, ids[candidate_index]).latest_flag is True


def test_legacy_certificate_effective_line_uses_valid_linked_case_for_identity_and_peers():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        company = Company(legal_name="Linked legacy context", short_name="LINK")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Linked legacy site")
        other_site = Site(company_id=company.id, site_name="Other site")
        fallback_only_site = Site(company_id=company.id, site_name="Fallback-only site")
        session.add_all([site, other_site, fallback_only_site]); session.flush()
        linked_a = Case(site_id=site.id, gxp_type="GMP", scope_code="A", state=CaseState.CERTIFIED)
        linked_b = Case(site_id=site.id, gxp_type="GMP", scope_code="B", state=CaseState.CERTIFIED)
        invalid_link = Case(site_id=other_site.id, gxp_type="GMP", scope_code="Z", state=CaseState.CERTIFIED)
        fallback_only_case = Case(site_id=fallback_only_site.id, gxp_type="GMP", scope_code="A", state=CaseState.CERTIFIED)
        session.add_all([linked_a, linked_b, invalid_link, fallback_only_case]); session.flush()

        def add(*, line_code, case_id, latest, number):
            row = Certificate(site_id=site.id, certificate_type="GMP", line_code=line_code, case_id=case_id, latest_flag=latest)
            session.add(row); session.flush()
            session.add(CertificateVersion(certificate_id=row.id, version_no=1, certificate_number=number, issue_date=date(2026, 1, 1), expiry_date=date(2027, 1, 1), is_latest_version=True))
            return row

        legacy_current = add(line_code="A", case_id=None, latest=True, number="L0")
        fallback_candidate = add(line_code="   ", case_id=linked_a.id, latest=False, number="L1")
        facility_current = add(line_code=None, case_id=None, latest=True, number="F0")
        direct_precedence = add(line_code="A", case_id=linked_b.id, latest=False, number="P0")
        invalid_fallback = add(line_code=None, case_id=invalid_link.id, latest=False, number="X0")
        fallback_only = Certificate(site_id=fallback_only_site.id, certificate_type="GMP", case_id=fallback_only_case.id, line_code=None, latest_flag=True)
        session.add(fallback_only); session.flush()
        session.add(CertificateVersion(certificate_id=fallback_only.id, version_no=1, certificate_number="ONLY-A", issue_date=date(2026, 1, 1), expiry_date=date(2027, 1, 1), is_latest_version=True))
        session.commit()
        ids = legacy_current.id, fallback_candidate.id, facility_current.id, direct_precedence.id, invalid_fallback.id
        site_id = site.id
        fallback_only_site_id = fallback_only_site.id

    with Session(engine) as session:
        candidate = session.get(Certificate, ids[1])
        precedence = session.get(Certificate, ids[3])
        invalid = session.get(Certificate, ids[4])
        assert candidate is not None and precedence is not None and invalid is not None
        assert service._certificate_line_identity(session, candidate) == {
            "production_line_id": None, "production_line_code": "A", "production_line_identity_state": "legacy_unlinked",
        }
        assert service._certificate_line_identity(session, precedence)["production_line_code"] == "A"
        with pytest.raises(Exception, match="invalid linked Case"):
            service._certificate_line_identity(session, invalid)
        assert service._site_has_gxp_context(session, site_id=site_id, gxp_type="GMP", line_code="A") is True
        assert service._site_has_gxp_context(session, site_id=fallback_only_site_id, gxp_type="GMP", line_code="A") is True
        assert service._site_has_gxp_context(session, site_id=fallback_only_site_id, gxp_type="GMP", line_code=None) is False
        peer_ids = set(session.scalars(select(Certificate.id).where(service._certificate_context_clause(session, candidate))).all())
        assert peer_ids == {ids[0], ids[1], ids[3]}
        service.promote_certificate_current(session, certificate_id=ids[1], reason="Linked legacy context.", user=user)
        session.commit()
        assert session.get(Certificate, ids[0]).latest_flag is False
        assert session.get(Certificate, ids[1]).latest_flag is True
        assert session.get(Certificate, ids[2]).latest_flag is True


def test_certificate_invalid_linked_cases_fail_closed_before_identity_or_mutation():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        company = Company(legal_name="Invalid links", short_name="IL")
        session.add(company); session.flush()
        site_a = Site(company_id=company.id, site_name="A")
        site_b = Site(company_id=company.id, site_name="B")
        session.add_all([site_a, site_b]); session.flush()
        line = ProductionLine(site_id=site_a.id, code="A", effective_from=date(2020, 1, 1))
        wrong_site = Case(site_id=site_b.id, gxp_type="GMP", scope_code="A", state=CaseState.CERTIFIED)
        wrong_gxp = Case(site_id=site_a.id, gxp_type="GLP", scope_code="A", state=CaseState.CERTIFIED)
        session.add_all([line, wrong_site, wrong_gxp]); session.flush()

        def add(*, case_id, line_code=None, line_id=None, number, latest=False):
            certificate = Certificate(site_id=site_a.id, case_id=case_id, certificate_type="GMP", line_code=line_code, production_line_id=line_id, latest_flag=latest)
            session.add(certificate); session.flush()
            session.add(CertificateVersion(certificate_id=certificate.id, version_no=1, certificate_number=number, issue_date=date(2026, 1, 1), expiry_date=date(2027, 1, 1), is_latest_version=True))
            return certificate

        certificates = [
            add(case_id=wrong_site.id, number="SITE"),
            add(case_id=wrong_gxp.id, number="GXP"),
            add(case_id=wrong_site.id, line_code="A", number="DIRECT"),
            add(case_id=wrong_site.id, line_id=line.id, number="CANONICAL", latest=True),
            add(case_id="deadbeef-dead-4bad-8ace-deadbeefcafe", number="MISSING"),
        ]
        session.commit(); certificate_ids = [row.id for row in certificates]; site_a_id = site_a.id; line_id = line.id

    with Session(engine) as session:
        for certificate_id in certificate_ids:
            certificate = session.get(Certificate, certificate_id)
            assert certificate is not None
            with pytest.raises(Exception, match="invalid linked Case"):
                service._certificate_line_identity(session, certificate)
            with pytest.raises(Exception, match="invalid linked Case"):
                service.get_certificate_action_readiness(session, certificate_id=certificate_id, user=user)
            with pytest.raises(Exception, match="invalid linked Case"):
                service.promote_certificate_current(session, certificate_id=certificate_id, reason="Reject invalid relation.", user=user)
        assert service._site_has_gxp_context(session, site_id=certificate.site_id, gxp_type="GMP", line_code=None) is False
        invalid_readiness = service.get_create_reassessment_case_action_readiness(
            session,
            site_id=site_a_id,
            gxp_type="GMP",
            line_code="A",
            production_line_id=line_id,
            user=SimpleNamespace(permissions={"case.edit"}),
        )
        assert invalid_readiness["readiness_status"] != "available"

        administrative = Certificate(
            site_id=site_a_id,
            certificate_type="GMP",
            production_line_id=line_id,
            latest_flag=True,
            issuance_basis="administrative_no_inspection",
        )
        session.add(administrative); session.flush()
        session.add(CertificateVersion(
            certificate_id=administrative.id,
            version_no=1,
            certificate_number="ADMIN-CANONICAL",
            issue_date=date(2026, 2, 1),
            expiry_date=date(2027, 2, 1),
            is_latest_version=True,
        ))
        session.commit()
        valid_readiness = service.get_create_reassessment_case_action_readiness(
            session,
            site_id=site_a_id,
            gxp_type="GMP",
            line_code="A",
            production_line_id=line_id,
            user=SimpleNamespace(permissions={"case.edit"}),
        )
        assert valid_readiness["readiness_status"] == "available"


def test_certificate_promotion_checks_and_demotes_all_current_context_peers():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        company = Company(legal_name="Multiple currents", short_name="MC")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Multiple current site")
        session.add(site); session.flush()

        def add(*, latest, issued, number):
            certificate = Certificate(site_id=site.id, certificate_type="GMP", line_code="A", latest_flag=latest)
            session.add(certificate); session.flush()
            session.add(CertificateVersion(certificate_id=certificate.id, version_no=1, certificate_number=number, issue_date=issued, expiry_date=date(2027, 1, 1), is_latest_version=True))
            return certificate

        current_early = add(latest=True, issued=date(2026, 1, 1), number="EARLY")
        current_late = add(latest=True, issued=date(2026, 9, 20), number="LATE")
        blocked_candidate = add(latest=False, issued=date(2026, 9, 1), number="BLOCKED")
        accepted_candidate = add(latest=False, issued=date(2026, 10, 1), number="ACCEPTED")
        session.commit(); ids = current_early.id, current_late.id, blocked_candidate.id, accepted_candidate.id

    with Session(engine) as session:
        with pytest.raises(Exception, match="not older than the current active certificate"):
            service.promote_certificate_current(session, certificate_id=ids[2], reason="All peers must block.", user=user)
        service.promote_certificate_current(session, certificate_id=ids[3], reason="Demote all peers.", user=user)
        session.commit()
        assert session.get(Certificate, ids[0]).latest_flag is False
        assert session.get(Certificate, ids[1]).latest_flag is False
        assert session.get(Certificate, ids[2]).latest_flag is False
        assert session.get(Certificate, ids[3]).latest_flag is True


def test_cross_site_certificate_and_reassessment_contexts_fail_closed():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = build_authenticated_user("admin01", "admin")
    with Session(engine) as session:
        company = Company(legal_name="Cross-site", short_name="XS")
        session.add(company); session.flush()
        site_a = Site(company_id=company.id, site_name="A")
        site_b = Site(company_id=company.id, site_name="B")
        session.add_all([site_a, site_b]); session.flush()
        line = ProductionLine(site_id=site_b.id, code="A", effective_from=date(2020, 1, 1))
        session.add(line); session.flush()
        certificate = Certificate(site_id=site_a.id, certificate_type="GMP", production_line_id=line.id, latest_flag=False)
        corrupt_case = Case(site_id=site_a.id, gxp_type="GMP", production_line_id=line.id, scope_code="A", state=CaseState.CLOSED)
        session.add_all([certificate, corrupt_case]); session.flush()
        session.add(CertificateVersion(certificate_id=certificate.id, version_no=1, certificate_number="XS", issue_date=date(2026, 1, 1), expiry_date=date(2027, 1, 1), is_latest_version=True))
        session.commit(); certificate_id, site_id, line_id = certificate.id, site_a.id, line.id
    with Session(engine) as session:
        with pytest.raises(Exception, match="invalid canonical ProductionLine"):
            service.get_certificate_action_readiness(session, certificate_id=certificate_id, user=user)
        with pytest.raises(Exception, match="invalid canonical ProductionLine"):
            service.promote_certificate_current(session, certificate_id=certificate_id, reason="Reject corrupt.", user=user)
        readiness = service.get_create_reassessment_case_action_readiness(session, site_id=site_id, gxp_type="GMP", line_code="A", production_line_id=line_id, user=SimpleNamespace(permissions={"case.edit"}))
        assert readiness["readiness_status"] == "unavailable"
        with pytest.raises(Exception, match="does not belong"):
            service.create_inspection_case(session, site_id=site_id, gxp_type="GMP", line_code="A", production_line_id=line_id, applicable_standard="WHO-GMP", source_case_id=None, reason="Reject corrupt.", user=user)


def test_reassessment_open_case_conflict_uses_production_line_uuid_not_same_code():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    user = SimpleNamespace(permissions={"case.edit"})
    with Session(engine) as session:
        company = Company(legal_name="Open context", short_name="OC")
        session.add(company); session.flush()
        site = Site(company_id=company.id, site_name="Open site")
        session.add(site); session.flush()
        first = ProductionLine(site_id=site.id, code="A", effective_from=date(2020, 1, 1))
        second = ProductionLine(site_id=site.id, code="A", effective_from=date(2021, 1, 1))
        session.add_all([first, second]); session.flush()
        session.add_all([
            Case(site_id=site.id, gxp_type="GMP", production_line_id=first.id, scope_code="A", state=CaseState.PLANNED),
            Case(site_id=site.id, gxp_type="GMP", production_line_id=second.id, scope_code="A", state=CaseState.CLOSED),
        ])
        session.commit(); site_id, first_id, second_id = site.id, first.id, second.id
    with Session(engine) as session:
        first_ready = service.get_create_reassessment_case_action_readiness(session, site_id=site_id, gxp_type="GMP", line_code="A", production_line_id=first_id, user=user)
        second_ready = service.get_create_reassessment_case_action_readiness(session, site_id=site_id, gxp_type="GMP", line_code="A", production_line_id=second_id, user=user)
    assert first_ready["readiness_status"] == "conflict"
    assert second_ready["readiness_status"] == "available"


def test_upsert_business_eligibility_latest_version_replaces_links():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        case_row.state = CaseState.AWAITING_CERTIFICATE_DECISION
        site_id = case_row.site_id
        session.commit()

    with Session(engine) as session:
        certificate = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=case_id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            certificate_number="CERT-LINK-1",
            issue_date=date(2026, 8, 18),
            expiry_date=date(2027, 8, 18),
            scopes=[],
            reason="Linked cert 1.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        dkkd = service.issue_business_eligibility(
            session,
            site_id=site_id,
            certificate_number="DDKD-001",
            issued_on=date(2026, 8, 19),
            expires_on=date(2027, 8, 19),
            professional_responsible_person_name="Pharmacist A",
            notes="Initial issue.",
            linked_certificates=[
                {"certificate_id": certificate["certificate_id"], "link_role": "source_certificate"},
            ],
            reason="Initial DDKD issue.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert len(dkkd["linked_certificates"]) == 1

    with Session(engine) as session:
        replacement_certificate = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=case_id,
            certificate_type="GMP",
            issuance_basis="inspection_case",
            certificate_number="CERT-LINK-2",
            issue_date=date(2026, 8, 20),
            expiry_date=date(2027, 8, 20),
            scopes=[],
            reason="Linked cert 2.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        updated = service.upsert_business_eligibility_latest_version(
            session,
            business_eligibility_certificate_id=dkkd["business_eligibility_certificate_id"],
            certificate_number="DDKD-001-REV",
            issued_on=date(2026, 8, 21),
            expires_on=date(2027, 8, 21),
            professional_responsible_person_name="Pharmacist B",
            notes="Updated links.",
            linked_certificates=[
                {"certificate_id": replacement_certificate["certificate_id"], "link_role": "replacement_certificate"},
            ],
            reason="Replace linked cert list.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert updated["certificate_number"] == "DDKD-001-REV"
    assert len(updated["linked_certificates"]) == 1

    with Session(engine) as session:
        version = session.scalars(select(BusinessEligibilityVersion)).one()
        assert version.professional_responsible_person_name == "Pharmacist B"
        links = list(session.scalars(select(BusinessEligibilityCertificateLink)))
        assert len(links) == 1
        assert links[0].certificate_id == replacement_certificate["certificate_id"]


def _seed_invalid_dkkd_certificate(session: Session, *, cross_site_line: bool = False) -> tuple[str, str]:
    case_id = seed_case(session)
    case = session.get(Case, case_id)
    assert case is not None
    company = session.get(Company, session.get(Site, case.site_id).company_id)
    assert company is not None
    other_site = Site(company_id=company.id, site_name="Invalid DDKD target")
    session.add(other_site); session.flush()
    certificate = Certificate(site_id=case.site_id, certificate_type="GMP", line_code="A", latest_flag=False)
    if cross_site_line:
        line = ProductionLine(site_id=other_site.id, code="A", effective_from=date(2020, 1, 1))
        session.add(line); session.flush()
        certificate.production_line_id = line.id
    else:
        invalid_case = Case(site_id=other_site.id, gxp_type="GMP", scope_code="A", state=CaseState.CERTIFIED)
        session.add(invalid_case); session.flush()
        certificate.case_id = invalid_case.id
    session.add(certificate); session.flush()
    session.add(CertificateVersion(certificate_id=certificate.id, version_no=1, certificate_number="INVALID", is_latest_version=True))
    session.commit()
    return case.site_id, certificate.id


@pytest.mark.parametrize("cross_site_line", [False, True])
def test_business_eligibility_issue_rejects_invalid_certificate_identity(cross_site_line):
    engine = create_engine("sqlite:///:memory:", future=True); Base.metadata.create_all(engine)
    service = CaseWorkflowService(); user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        site_id, certificate_id = _seed_invalid_dkkd_certificate(session, cross_site_line=cross_site_line)
    with Session(engine) as session:
        with pytest.raises(Exception, match="invalid linked Case|invalid canonical ProductionLine"):
            service.issue_business_eligibility(session, site_id=site_id, certificate_number="D", issued_on=date(2026, 1, 1), expires_on=None, professional_responsible_person_name=None, notes=None, linked_certificates=[{"certificate_id": certificate_id}], reason="reject", user=user)
        session.rollback()
        assert session.scalar(select(func.count()).select_from(BusinessEligibilityCertificateLink).where(BusinessEligibilityCertificateLink.certificate_id == certificate_id)) == 0


def test_business_eligibility_update_rolls_back_when_replacement_certificate_is_invalid():
    engine = create_engine("sqlite:///:memory:", future=True); Base.metadata.create_all(engine)
    service = CaseWorkflowService(); user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        site_id, invalid_id = _seed_invalid_dkkd_certificate(session)
        good = Certificate(site_id=site_id, certificate_type="GMP", line_code="A", latest_flag=False)
        session.add(good); session.flush(); session.add(CertificateVersion(certificate_id=good.id, version_no=1, certificate_number="GOOD", is_latest_version=True)); session.flush()
        issued = service.issue_business_eligibility(session, site_id=site_id, certificate_number="D", issued_on=date(2026, 1, 1), expires_on=None, professional_responsible_person_name=None, notes="old", linked_certificates=[{"certificate_id": good.id}], reason="good", user=user)
        session.commit(); dkkd_id, good_id = issued["business_eligibility_certificate_id"], good.id
    with Session(engine) as session:
        with pytest.raises(Exception, match="invalid linked Case"):
            service.upsert_business_eligibility_latest_version(session, business_eligibility_certificate_id=dkkd_id, certificate_number="BAD", issued_on=date(2026, 2, 1), expires_on=None, professional_responsible_person_name=None, notes="bad", linked_certificates=[{"certificate_id": invalid_id}], reason="bad", user=user)
        session.rollback()
    with Session(engine) as session:
        links = list(session.scalars(select(BusinessEligibilityCertificateLink)))
        assert [link.certificate_id for link in links] == [good_id]
        assert session.get(BusinessEligibilityVersion, links[0].business_eligibility_version_id).certificate_number == "D"


def test_business_eligibility_promotion_validates_historical_invalid_link_before_mutation():
    engine = create_engine("sqlite:///:memory:", future=True); Base.metadata.create_all(engine)
    service = CaseWorkflowService(); user = build_authenticated_user("manager01", "manager")
    with Session(engine) as session:
        site_id, invalid_id = _seed_invalid_dkkd_certificate(session)
        site = session.get(Site, site_id); assert site is not None
        current = BusinessEligibilityCertificate(site_id=site.id, company_id=site.company_id, latest_flag=True)
        candidate = BusinessEligibilityCertificate(site_id=site.id, company_id=site.company_id, latest_flag=False)
        session.add_all([current, candidate]); session.flush()
        session.add_all([BusinessEligibilityVersion(business_eligibility_certificate_id=current.id, version_no=1, certificate_number="CURRENT", issued_on=date(2026, 1, 1)), BusinessEligibilityVersion(business_eligibility_certificate_id=candidate.id, version_no=1, certificate_number="CANDIDATE", issued_on=date(2026, 2, 1))]); session.flush()
        candidate_version = session.scalars(select(BusinessEligibilityVersion).where(BusinessEligibilityVersion.business_eligibility_certificate_id == candidate.id)).one()
        session.add(BusinessEligibilityCertificateLink(business_eligibility_version_id=candidate_version.id, certificate_id=invalid_id, link_role="historical")); session.commit(); current_id, candidate_id = current.id, candidate.id
    with Session(engine) as session:
        with pytest.raises(Exception, match="invalid linked Case"):
            service.promote_business_eligibility_current(session, business_eligibility_certificate_id=candidate_id, reason="reject", user=user)
        session.rollback()
        assert session.get(BusinessEligibilityCertificate, current_id).latest_flag is True
        assert session.get(BusinessEligibilityCertificate, candidate_id).latest_flag is False


def test_promote_business_eligibility_current_demotes_previous_current():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)
        case_row = session.get(Case, case_id)
        assert case_row is not None
        site_id = case_row.site_id

    with Session(engine) as session:
        first = service.issue_business_eligibility(
            session,
            site_id=site_id,
            certificate_number="DDKD-100",
            issued_on=date(2026, 8, 10),
            expires_on=date(2027, 8, 10),
            professional_responsible_person_name="Pharmacist A",
            notes=None,
            linked_certificates=[],
            reason="First current.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        service.promote_business_eligibility_current(
            session,
            business_eligibility_certificate_id=first["business_eligibility_certificate_id"],
            reason="Promote first current.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        second = service.issue_business_eligibility(
            session,
            site_id=site_id,
            certificate_number="DDKD-101",
            issued_on=date(2026, 8, 12),
            expires_on=date(2027, 8, 12),
            professional_responsible_person_name="Pharmacist B",
            notes=None,
            linked_certificates=[],
            reason="Second candidate.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        promoted = service.promote_business_eligibility_current(
            session,
            business_eligibility_certificate_id=second["business_eligibility_certificate_id"],
            reason="Promote newer current.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert promoted["latest_flag"] is True

    with Session(engine) as session:
        rows = list(session.scalars(select(BusinessEligibilityCertificate).order_by(BusinessEligibilityCertificate.created_at)))
        assert len(rows) == 2
        assert rows[0].latest_flag is False
        assert rows[1].latest_flag is True


def test_a4_business_eligibility_readiness_and_mutation_fail_closed_on_duplicate_current():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    manager = build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"])

    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        site = session.get(Site, case.site_id)
        assert site is not None
        candidate = BusinessEligibilityCertificate(site_id=site.id, company_id=site.company_id, latest_flag=False)
        current_a = BusinessEligibilityCertificate(site_id=site.id, company_id=site.company_id, latest_flag=True)
        current_b = BusinessEligibilityCertificate(site_id=site.id, company_id=site.company_id, latest_flag=True)
        session.add_all([candidate, current_a, current_b])
        session.flush()
        session.add_all([
            BusinessEligibilityVersion(business_eligibility_certificate_id=candidate.id, version_no=1, certificate_number="CANDIDATE", issued_on=date(2026, 10, 1)),
            BusinessEligibilityVersion(business_eligibility_certificate_id=current_a.id, version_no=1, certificate_number="CURRENT-A", issued_on=date(2026, 9, 1)),
            BusinessEligibilityVersion(business_eligibility_certificate_id=current_b.id, version_no=1, certificate_number="CURRENT-B", issued_on=date(2026, 9, 2)),
        ])
        session.commit()
        candidate_id, candidate_version = candidate.id, candidate.row_version
        current_ids = [current_a.id, current_b.id]

    with Session(engine) as session:
        readiness = service.get_business_eligibility_action_readiness(
            session,
            business_eligibility_certificate_id=candidate_id,
            user=manager,
        )
        promote = next(item for item in readiness if item["action_key"] == "promote_current")
        assert promote["available"] is False
        assert promote["reason_code"] == "multiple_current_records"
        with pytest.raises(HTTPException, match="multiple current records"):
            service.promote_business_eligibility_current(
                session,
                business_eligibility_certificate_id=candidate_id,
                expected_version=candidate_version,
                reason="Must fail closed.",
                user=manager,
            )
        session.rollback()

    with Session(engine) as session:
        assert session.get(BusinessEligibilityCertificate, candidate_id).latest_flag is False
        assert all(session.get(BusinessEligibilityCertificate, item).latest_flag is True for item in current_ids)


def test_a4_business_eligibility_older_candidate_readiness_matches_mutation():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    manager = build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"])

    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        site = session.get(Site, case.site_id)
        assert site is not None
        current = BusinessEligibilityCertificate(site_id=site.id, company_id=site.company_id, latest_flag=True)
        candidate = BusinessEligibilityCertificate(site_id=site.id, company_id=site.company_id, latest_flag=False)
        session.add_all([current, candidate])
        session.flush()
        session.add_all([
            BusinessEligibilityVersion(business_eligibility_certificate_id=current.id, version_no=1, certificate_number="CURRENT", issued_on=date(2026, 10, 2)),
            BusinessEligibilityVersion(business_eligibility_certificate_id=candidate.id, version_no=1, certificate_number="OLDER", issued_on=date(2026, 10, 1)),
        ])
        session.commit()
        candidate_id, expected_version = candidate.id, candidate.row_version

    with Session(engine) as session:
        promote = next(
            item
            for item in service.get_business_eligibility_action_readiness(
                session,
                business_eligibility_certificate_id=candidate_id,
                user=manager,
            )
            if item["action_key"] == "promote_current"
        )
        assert promote["available"] is False
        assert promote["reason_code"] == "candidate_issue_date_precedes_current"
        with pytest.raises(HTTPException, match="not older than the current active record"):
            service.promote_business_eligibility_current(
                session,
                business_eligibility_certificate_id=candidate_id,
                expected_version=expected_version,
                reason="Parity check.",
                user=manager,
            )


def test_a4_business_eligibility_latest_version_advances_parent_optimistic_lock():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    manager = build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"])

    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        issued = service.issue_business_eligibility(
            session,
            site_id=case.site_id,
            certificate_number="DDKD-A4",
            issued_on=date(2026, 10, 1),
            expires_on=date(2027, 10, 1),
            professional_responsible_person_name="PTCM A",
            notes="initial",
            linked_certificates=[],
            reason="Issue candidate.",
            user=manager,
        )
        session.commit()
        dkkd_id = issued["business_eligibility_certificate_id"]
        original_version = issued["row_version"]

    with Session(engine) as session:
        updated = service.upsert_business_eligibility_latest_version(
            session,
            business_eligibility_certificate_id=dkkd_id,
            expected_version=original_version,
            certificate_number="DDKD-A4-REV",
            issued_on=date(2026, 10, 2),
            expires_on=date(2027, 10, 2),
            professional_responsible_person_name="PTCM B",
            notes="updated",
            linked_certificates=[],
            reason="Update candidate.",
            user=manager,
        )
        session.commit()
        assert updated["row_version"] > original_version

    with Session(engine) as session:
        with pytest.raises(HTTPException, match="Stale business_eligibility_certificate update"):
            service.upsert_business_eligibility_latest_version(
                session,
                business_eligibility_certificate_id=dkkd_id,
                expected_version=original_version,
                certificate_number="STALE",
                issued_on=date(2026, 10, 3),
                expires_on=None,
                professional_responsible_person_name=None,
                notes=None,
                linked_certificates=[],
                reason="Stale overwrite.",
                user=manager,
            )


def test_a4_business_eligibility_issue_readiness_is_permission_owned():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        issuer = build_authenticated_user("issuer01", "manager", permissions={"certificate.issue"})
        manager = build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"])
        allowed = service.get_business_eligibility_issue_readiness(session, site_id=case.site_id, user=issuer)
        blocked = service.get_business_eligibility_issue_readiness(session, site_id=case.site_id, user=manager)
    assert allowed["available"] is True
    assert allowed["reason_code"] is None
    assert blocked["available"] is False
    assert blocked["reason_code"] == "missing_permission"


def test_a4_business_eligibility_rejects_cross_site_gxp_basis_before_link_write():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()
    manager = build_authenticated_user("manager01", "manager", permissions=ROLE_PERMISSIONS["manager"])

    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        site = session.get(Site, case.site_id)
        assert site is not None
        other_site = Site(company_id=site.company_id, site_name="Other canonical site")
        session.add(other_site)
        session.flush()
        foreign_certificate = Certificate(site_id=other_site.id, certificate_type="GMP", latest_flag=True)
        session.add(foreign_certificate)
        session.flush()
        session.add(CertificateVersion(
            certificate_id=foreign_certificate.id,
            version_no=1,
            certificate_number="FOREIGN-GMP",
            issue_date=date(2026, 9, 1),
            expiry_date=date(2027, 9, 1),
            is_latest_version=True,
        ))
        session.commit()
        site_id, foreign_id = site.id, foreign_certificate.id

    with Session(engine) as session:
        with pytest.raises(HTTPException, match="different site"):
            service.issue_business_eligibility(
                session,
                site_id=site_id,
                certificate_number="DDKD-CROSS-SITE",
                issued_on=date(2026, 10, 1),
                expires_on=None,
                professional_responsible_person_name=None,
                notes=None,
                linked_certificates=[{"certificate_id": foreign_id, "link_role": "source_certificate"}],
                reason="Must not cross site ownership.",
                user=manager,
            )
        session.rollback()
        assert session.scalar(select(func.count()).select_from(BusinessEligibilityCertificateLink)) == 0


def test_a4_business_eligibility_promotion_locks_site_before_revalidation():
    class OrderingService(CaseWorkflowService):
        def __init__(self):
            super().__init__()
            self.site_locked = False

        def _lock_site(self, session, site_id):
            locked = super()._lock_site(session, site_id)
            self.site_locked = True
            return locked

        def _get_business_eligibility_promotion_blocker(self, session, *, certificate, version):
            assert self.site_locked is True
            return super()._get_business_eligibility_promotion_blocker(
                session,
                certificate=certificate,
                version=version,
            )

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = OrderingService()
    approver = build_authenticated_user("manager01", "manager", permissions={"certificate.approve"})

    with Session(engine) as session:
        case_id = seed_case(session)
        case = session.get(Case, case_id)
        assert case is not None
        site = session.get(Site, case.site_id)
        assert site is not None
        candidate = BusinessEligibilityCertificate(
            site_id=site.id,
            company_id=site.company_id,
            latest_flag=False,
        )
        session.add(candidate)
        session.flush()
        session.add(
            BusinessEligibilityVersion(
                business_eligibility_certificate_id=candidate.id,
                version_no=1,
                certificate_number="DDKD-LOCKED",
                issued_on=date(2026, 10, 5),
            )
        )
        session.commit()
        candidate_id = candidate.id
        expected_version = candidate.row_version

    with Session(engine) as session:
        result = service.promote_business_eligibility_current(
            session,
            business_eligibility_certificate_id=candidate_id,
            expected_version=expected_version,
            reason="Serialize current-owner mutation.",
            user=approver,
        )
        session.commit()

    assert service.site_locked is True
    assert result["latest_flag"] is True
