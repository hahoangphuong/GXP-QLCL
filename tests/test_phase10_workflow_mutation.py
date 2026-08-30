import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, select
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
    Certificate,
    CertificateScope,
    CertificateVersion,
    Company,
    InspectionEvent,
    InspectionOutcome,
    InspectionPlan,
    InspectionTeam,
    InspectionTeamMember,
    Site,
)
from backend.app.main import create_app
from backend.app.read_models import InspectionCaseCreateRequest
from backend.app.services.workflow import CaseWorkflowService


def seed_case(session: Session) -> str:
    company = Company(legal_name="Test Company", short_name="TC")
    session.add(company)
    session.flush()
    site = Site(company_id=company.id, site_name="Test Site")
    session.add(site)
    session.flush()
    case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
    session.add(case)
    session.commit()
    return case.id


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

    seeded_case_id: str | None = None
    if include_case:
        seeded_case = Case(
            site_id=site.id,
            gxp_type=gxp_type,
            scope_code=line_code,
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
    return {"site_id": site.id, "seeded_case_id": seeded_case_id}


def test_phase10_transition_route_is_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/cases/{case_id}/transition" in routes
    assert "/cases/{case_id}/application" in routes
    assert "/cases/{case_id}/assessment" in routes
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
            inspection_type="Định kỳ",
            applicable_standard="WHO-GMP",
            reason="Open new inspection case.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["site_id"] == seeded["site_id"]
    assert result["gxp_type"] == "GMP"
    assert result["line_code"] == "A"
    assert result["inspection_type"] == "Định kỳ"
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
        assert session.scalar(select(CaseApplication).where(CaseApplication.case_id == created.id)) is None
        assert session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == created.id)) is None
        assert session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == created.id)) is None
        assert session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == created.id)) is None
        assert session.scalar(select(InspectionEvent).where(InspectionEvent.case_id == created.id)) is None
        audit_event = session.get(AuditEvent, result["audit_event_id"])
        assert audit_event is not None
        assert audit_event.action == "case.create_inspection_case"
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
            inspection_type="Định kỳ",
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
            inspection_type="Đột xuất",
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
                inspection_type="Định kỳ",
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
            ("GMP", "Z", "authoritative existing context"),
        ]:
            try:
                service.create_inspection_case(
                    session,
                    site_id=seeded["site_id"],
                    gxp_type=gxp_type,
                    line_code=line_code,
                    inspection_type="Định kỳ",
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
                inspection_type="Định kỳ",
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
            inspection_type="Định kỳ",
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
                inspection_type="Định kỳ",
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
            inspection_type="Định kỳ",
            applicable_standard=None,
            reason="Different site context.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["site_id"] == seeded["site_id"]


def test_create_inspection_case_rolls_back_cleanly_after_validation_failure():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        seeded = seed_create_inspection_case_context(session, line_code="A", case_state=CaseState.CLOSED)
        baseline_case_count = len(list(session.scalars(select(Case))))

    with Session(engine) as session:
        try:
            service.create_inspection_case(
                session,
                site_id=seeded["site_id"],
                gxp_type="GMP",
                line_code="A",
                inspection_type="   ",
                applicable_standard=None,
                reason="Blank type.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "inspection_type is required" in str(exc)
            session.rollback()
        else:
            raise AssertionError("Expected blank inspection_type to fail")

    with Session(engine) as session:
        assert len(list(session.scalars(select(Case)))) == baseline_case_count


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
        inspection_type="Định kỳ",
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
    assert body["inspection_type"] == "Định kỳ"
    assert body["state"] == "draft"


def test_transition_case_persists_audit_and_event():
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
    assert result["inspection_event_id"] is not None

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
        assert session.scalars(select(InspectionEvent)).first() is not None


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
            dossier_reference="REF-001",
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
            "dossier_reference": "REF-001",
            "submitted_on": None,
        }


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
            dossier_reference="REF-002",
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
            decision_document_hint="QD-01",
            reason="Planning baseline.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["planning_sheet_name"] == "KHKT-2026-08"

    with Session(engine) as session:
        row = session.scalars(select(InspectionPlan)).first()
        assert row is not None
        assert row.decision_document_hint == "QD-01"


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
            decision_reference="QD-02",
            bbkt_reference="BBKT-02",
            outcome_result="compliant",
            reason="Outcome recorded.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["outcome_result"] == "compliant"
    assert result["inspection_event_id"] is not None

    with Session(engine) as session:
        row = session.scalars(select(InspectionOutcome)).first()
        assert row is not None
        assert row.bbkt_reference == "BBKT-02"


def test_upsert_inspection_team_replaces_member_list_and_writes_audit():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    service = CaseWorkflowService()

    with Session(engine) as session:
        case_id = seed_case(session)

    with Session(engine) as session:
        result = service.upsert_inspection_team(
            session,
            case_id=case_id,
            display_text="Lead: Inspector A; Member: Specialist B",
            members=[
                {"person_id": "00000000-0000-0000-0000-0000000000a1", "inspector_profile_id": None, "role_label": "lead", "sort_order": 1},
                {"person_id": "00000000-0000-0000-0000-0000000000b2", "inspector_profile_id": None, "role_label": "member", "sort_order": 2},
            ],
            reason="Initial team assignment.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    assert result["team_id"] is not None
    assert len(result["members"]) == 2
    assert result["audit_event_id"] is not None

    with Session(engine) as session:
        team = session.scalars(select(InspectionTeam)).first()
        assert team is not None
        assert team.display_text == "Lead: Inspector A; Member: Specialist B"
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id)))
        assert len(members) == 2
        assert session.scalars(select(AuditEvent).where(AuditEvent.action == "inspection_team.upsert")).first() is not None

    with Session(engine) as session:
        service.upsert_inspection_team(
            session,
            case_id=case_id,
            display_text="Lead: Inspector A",
            members=[
                {"person_id": "00000000-0000-0000-0000-0000000000a1", "inspector_profile_id": None, "role_label": "lead", "sort_order": 1},
            ],
            reason="Team narrowed.",
            user=build_authenticated_user("manager01", "manager"),
        )
        session.commit()

    with Session(engine) as session:
        team = session.scalars(select(InspectionTeam)).first()
        assert team is not None
        members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id)))
        assert len(members) == 1


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
                display_text=None,
                members=[
                    {"person_id": None, "inspector_profile_id": None, "role_label": "lead", "sort_order": 1},
                ],
                reason="Invalid payload.",
                user=build_authenticated_user("manager01", "manager"),
            )
        except Exception as exc:
            assert "exactly one" in str(exc)
        else:
            raise AssertionError("Expected invalid inspection team member to fail")


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

    with Session(engine) as session:
        listed = service.list_capa_cycles(session, case_id=case_id)
        assert len(listed) == 1
        assert listed[0]["capa_cycle_id"] == created["capa_cycle_id"]
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
            assert "immutable" in str(exc)
        else:
            raise AssertionError("Expected accepted CAPA cycle to reject updates")


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
            certificate_type="GSP",
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
