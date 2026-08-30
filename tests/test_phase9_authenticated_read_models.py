import ast
import anyio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from backend.app.auth import (
    authenticate_google_iap_request,
    build_authenticated_user,
    parse_role_map,
    require_role,
    resolve_mapped_role,
)
from backend.app.document.runtime_artifacts import assert_required_phase5_runtime_artifacts_exist
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, ChangeRequestState, DocumentVariantType
from backend.app.db.models.phase1 import (
    AppUser,
    AppUserRole,
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion,
    Case,
    CaseApplication,
    CaseAssessment,
    CapaCycle,
    Certificate,
    CertificateScope,
    CertificateVersion,
    ChangeApproval,
    ChangeRequest,
    ChangeRequestDetail,
    Company,
    Document,
    DocumentVariant,
    DocumentVersion,
    InspectionEvent,
    InspectionEventType,
    InspectionPlan,
    InspectionOutcome,
    InspectionTeam,
    RbacPermission,
    RbacRole,
    RbacRolePermission,
    Site,
)
from backend.app.main import create_app
from backend.app.read_models import (
    CaseDetailRead,
    CaseRead,
    CompanyDetailRead,
    CompanyRead,
    FacilitySearchPageRead,
    SiteDetailRead,
    SiteRead,
)
from backend.app.domain.phase2_import import import_snapshot
from backend.app.services.catalog import CatalogReadService

ROOT = Path(__file__).resolve().parents[1]

ACTIVE_CASE_STATES = [
    "draft",
    "application_received",
    "under_assessment",
    "planned",
    "decision_issued",
    "inspection_in_progress",
    "inspection_completed",
    "awaiting_certificate_decision",
]

WAITING_INSPECTION_CASE_STATES = [
    "planned",
    "decision_issued",
    "inspection_in_progress",
]


def _extract_git_archive(export_root: Path) -> Path:
    export_root.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    for relative_path in completed.stdout.splitlines():
        if not relative_path:
            continue
        source = ROOT / relative_path
        target = export_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return export_root


def test_build_authenticated_user_accepts_valid_stub_headers():
    user = build_authenticated_user("alice", "manager")

    assert user.username == "alice"
    assert user.role == "manager"
    assert user.auth_mode == "header_stub"


def test_build_authenticated_user_rejects_missing_identity():
    try:
        build_authenticated_user("", "reader")
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected HTTPException for missing username")


def test_require_role_rejects_disallowed_role():
    user = build_authenticated_user("alice", "viewer")

    try:
        require_role(user, {"reader", "manager"})
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for disallowed role")


def test_phase9_detail_routes_are_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/companies/{company_id}" in routes
    assert "/sites/{site_id}" in routes
    assert "/cases/{case_id}" in routes
    assert "/cases/{case_id}/workspace" in routes
    assert "/change-requests/{change_request_id}/workspace" in routes
    assert "/dashboard/summary" in routes
    assert "/search/facilities" in routes
    assert "/sites/{site_id}/workspace" in routes
    assert "/sites/{site_id}/gxp-certificates" in routes
    assert "/certificates/{certificate_id}" in routes
    assert "/sites/{site_id}/business-eligibility-certificates" in routes
    assert "/business-eligibility-certificates/{business_eligibility_certificate_id}" in routes


def test_parse_role_map_accepts_email_role_pairs():
    mapping = parse_role_map("alice@example.com=manager;bob@example.com=admin")

    assert mapping == {
        "alice@example.com": "manager",
        "bob@example.com": "admin",
    }


def test_resolve_mapped_role_prefers_explicit_email_mapping():
    role = resolve_mapped_role(
        "alice@example.com",
        default_role="reader",
        role_map_raw="alice@example.com=manager",
    )

    assert role == "manager"


def test_authenticate_google_iap_request_uses_verified_claims():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_DEFAULT_ROLE": "reader",
            "AUTH_ROLE_MAP": "alice@example.com=manager",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={"X-Goog-IAP-JWT-Assertion": "token"},
    )

    user = authenticate_google_iap_request(
        request,
        verifier=lambda assertion, audience: {
            "email": "alice@example.com",
            "sub": "accounts.google.com:alice-subject",
            "aud": audience,
            "raw": assertion,
        },
    )

    assert user.username == "alice@example.com"
    assert user.role == "manager"
    assert user.auth_mode == "google_iap_jwt"
    assert user.email == "alice@example.com"
    assert user.subject == "accounts.google.com:alice-subject"


def test_authenticate_google_iap_request_can_use_explicit_header_fallback():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_DEFAULT_ROLE": "inspector",
            "AUTH_TRUSTED_HEADER_FALLBACK": "true",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:inspector@example.com",
            "X-Goog-Authenticated-User-Id": "accounts.google.com:abc123",
        },
    )

    user = authenticate_google_iap_request(request)

    assert user.username == "inspector@example.com"
    assert user.role == "inspector"
    assert user.email == "inspector@example.com"
    assert user.subject == "abc123"


def test_authenticate_google_iap_request_fails_closed_without_assertion_or_fallback():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
        },
    )
    request = SimpleNamespace(app=app, headers={})

    try:
        authenticate_google_iap_request(request)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected HTTPException for missing Google Cloud IAP identity assertion")


def test_authenticate_google_iap_request_rejects_outside_domain():
    app = create_app(
        "sqlite:///:memory:",
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={"X-Goog-IAP-JWT-Assertion": "token"},
    )

    try:
        authenticate_google_iap_request(
            request,
            verifier=lambda assertion, audience: {"email": "outsider@other.com", "sub": "outsider"},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for outside Google identity domain")


def test_authenticate_google_iap_request_fails_closed_on_ambiguous_database_identity(tmp_path):
    database_path = tmp_path / "auth-ambiguity.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        role = RbacRole(role_code="manager", description="Manager")
        permission = RbacPermission(permission_code="case.edit", description="Edit case")
        user_by_email = AppUser(
            username="email-owner",
            external_email="alice@example.com",
            display_name="Email Owner",
            is_active=True,
        )
        user_by_subject = AppUser(
            username="subject-owner",
            external_subject="subject-123",
            display_name="Subject Owner",
            is_active=True,
        )
        session.add_all([role, permission, user_by_email, user_by_subject])
        session.flush()
        session.add(AppUserRole(app_user_id=user_by_email.id, rbac_role_id=role.id))
        session.add(AppUserRole(app_user_id=user_by_subject.id, rbac_role_id=role.id))
        session.add(RbacRolePermission(rbac_role_id=role.id, rbac_permission_id=permission.id))
        session.commit()

    app = create_app(
        database_url,
        app_env={
            "AUTH_MODE": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/global/backendServices/456",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
        },
    )
    request = SimpleNamespace(
        app=app,
        headers={"X-Goog-IAP-JWT-Assertion": "token"},
    )

    try:
        authenticate_google_iap_request(
            request,
            verifier=lambda assertion, audience: {
                "email": "alice@example.com",
                "sub": "subject-123",
            },
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "different provisioned users" in exc.detail
    else:
        raise AssertionError("Expected ambiguity between email and subject claims to fail closed")


def test_get_case_detail_returns_row_version_and_matches_database_value(tmp_path):
    database_path = tmp_path / "catalog-detail.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Case Detail Company", short_name="CDC")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Case Detail Site")
        session.add(site)
        session.flush()
        case = Case(
            site_id=site.id,
            gxp_type="GMP",
            state=CaseState.INSPECTION_COMPLETED,
            legacy_inspection_id=123,
            legacy_inspection_code="KT-123",
            scope_code="WHO-GMP",
            applicable_standard="WHO-GMP",
            inspection_type="Định kỳ",
            opened_year=2026,
        )
        session.add(case)
        session.commit()
        case_id = case.id
        expected_row_version = case.row_version

    app = create_app(database_url)
    detail_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}")
    list_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases")
    with Session(engine) as session:
        detail_payload = detail_route.endpoint(
            case_id=case_id,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        list_payload = list_route.endpoint(
            q=None,
            gxp_type=None,
            limit=20,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    response = SimpleNamespace(
        status_code=200,
        json=lambda: CaseDetailRead.model_validate(detail_payload).model_dump(mode="json"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == case_id
    assert payload["row_version"] == expected_row_version
    assert payload["legacy_inspection_id"] == 123
    assert payload["legacy_inspection_code"] == "KT-123"
    assert payload["state"] == "inspection_completed"
    assert CaseDetailRead.model_validate(payload).row_version == expected_row_version

    assert isinstance(list_payload, list)
    assert len(list_payload) == 1
    list_item = CaseRead.model_validate(list_payload[0]).model_dump(mode="json")
    assert list_item["id"] == payload["id"]
    assert list_item["legacy_inspection_id"] == payload["legacy_inspection_id"]
    assert list_item["legacy_inspection_code"] == payload["legacy_inspection_code"]
    assert list_item["site_id"] == payload["site_id"]
    assert list_item["gxp_type"] == payload["gxp_type"]
    assert list_item["state"] == payload["state"]


def seed_cross_gxp_catalog(session: Session):
    company = Company(legal_name="Công ty GxP", short_name="GXP")
    session.add(company)
    session.flush()
    site = Site(
        company_id=company.id,
        site_name="Cơ sở đa GxP",
        province_name="Hà Nội",
        legacy_site_id=501,
        legacy_gmp_site_code="GMP-501",
        legacy_glp_site_code="GLP-501",
        site_address="KCN Bắc Thăng Long",
    )
    session.add(site)
    session.flush()

    gmp_case = Case(
        site_id=site.id,
        gxp_type="GMP",
        state=CaseState.INSPECTION_COMPLETED,
        legacy_inspection_id=1001,
        legacy_inspection_code="KT-GMP-2025",
        applicable_standard="WHO-GMP",
        inspection_type="Định kỳ",
        opened_year=2025,
    )
    glp_case = Case(
        site_id=site.id,
        gxp_type="GLP",
        state=CaseState.AWAITING_CERTIFICATE_DECISION,
        legacy_inspection_id=2002,
        legacy_inspection_code="KT-GLP-2026",
        applicable_standard="GLP-WHO",
        inspection_type="Tái đánh giá",
        opened_year=2026,
    )
    session.add_all([gmp_case, glp_case])
    session.flush()

    session.add_all(
        [
            InspectionEvent(
                case_id=gmp_case.id,
                event_type=InspectionEventType.INSPECTION_EXECUTED,
                occurred_at=datetime(2025, 5, 20, tzinfo=timezone.utc),
            ),
            InspectionEvent(
                case_id=glp_case.id,
                event_type=InspectionEventType.INSPECTION_EXECUTED,
                occurred_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
            ),
        ]
    )

    gmp_certificate = Certificate(
        site_id=site.id,
        case_id=gmp_case.id,
        certificate_type="GMP",
        latest_flag=True,
    )
    glp_certificate = Certificate(
        site_id=site.id,
        case_id=glp_case.id,
        certificate_type="GLP",
        latest_flag=True,
    )
    session.add_all([gmp_certificate, glp_certificate])
    session.flush()
    session.add_all(
        [
            CertificateVersion(
                certificate_id=gmp_certificate.id,
                version_no=1,
                issue_date=date(2025, 6, 1),
                expiry_date=date(2027, 6, 1),
                certificate_number="GCN-GMP-001",
                is_latest_version=True,
            ),
            CertificateVersion(
                certificate_id=glp_certificate.id,
                version_no=1,
                issue_date=date(2026, 8, 1),
                expiry_date=date(2026, 11, 15),
                certificate_number="GCN-GLP-009",
                is_latest_version=True,
            ),
        ]
    )

    received_change = ChangeRequest(
        site_id=site.id,
        legacy_change_request_id=9001,
        scope_label="Mở rộng kho",
        submitted_on=date(2026, 8, 10),
        state=ChangeRequestState.RECEIVED,
    )
    session.add(received_change)
    session.commit()

    return {
        "site_id": site.id,
        "gmp_case_id": gmp_case.id,
        "glp_case_id": glp_case.id,
    }


def seed_line_grain_catalog(session: Session):
    company = Company(legal_name="Công ty dây chuyền", short_name="LINE", legal_address="123 Trụ sở chính")
    session.add(company)
    session.flush()
    site = Site(
        company_id=company.id,
        site_name="Nhà máy viên nén",
        province_name="Bắc Ninh",
        legacy_site_id=111,
        legacy_gmp_site_code="1.1",
        site_address="KCN Yên Phong",
    )
    session.add(site)
    session.flush()

    case_a = Case(
        site_id=site.id,
        gxp_type="GMP",
        scope_code="A",
        state=CaseState.AWAITING_CERTIFICATE_DECISION,
        legacy_inspection_id=3001,
        legacy_inspection_code="KT-GMP-A",
        applicable_standard="WHO-GMP",
        inspection_type="Định kỳ",
        opened_year=2026,
    )
    case_b = Case(
        site_id=site.id,
        gxp_type="GMP",
        scope_code="B",
        state=CaseState.INSPECTION_IN_PROGRESS,
        legacy_inspection_id=3002,
        legacy_inspection_code="KT-GMP-B",
        applicable_standard="PIC/S-GMP",
        inspection_type="Mở rộng",
        opened_year=2026,
    )
    case_c = Case(
        site_id=site.id,
        gxp_type="GMP",
        scope_code="C",
        state=CaseState.PLANNED,
        legacy_inspection_id=3003,
        legacy_inspection_code="KT-GMP-C",
        applicable_standard="EU-GMP",
        inspection_type="Định kỳ",
        opened_year=2025,
    )
    session.add_all([case_a, case_b, case_c])
    session.flush()

    certificate_a = Certificate(site_id=site.id, case_id=case_a.id, certificate_type="GMP", latest_flag=True)
    certificate_b = Certificate(site_id=site.id, case_id=case_b.id, certificate_type="GMP", latest_flag=True)
    session.add_all([certificate_a, certificate_b])
    session.flush()

    version_a = CertificateVersion(
        certificate_id=certificate_a.id,
        version_no=1,
        issue_date=date(2026, 6, 1),
        expiry_date=date(2027, 6, 1),
        certificate_number="GCN-A",
        applicable_standard="WHO-GMP",
        is_latest_version=True,
    )
    version_b = CertificateVersion(
        certificate_id=certificate_b.id,
        version_no=1,
        issue_date=date(2026, 7, 15),
        expiry_date=date(2027, 7, 15),
        certificate_number="GCN-B",
        applicable_standard="PIC/S-GMP",
        is_latest_version=True,
    )
    session.add_all([version_a, version_b])
    session.flush()
    session.add_all(
        [
            CertificateScope(
                certificate_version_id=version_a.id,
                scope_key="A",
                scope_text="Dây chuyền viên nén A",
                sort_order=1,
            ),
            CertificateScope(
                certificate_version_id=version_b.id,
                scope_key="B",
                scope_text="Dây chuyền thuốc bột B",
                sort_order=1,
            ),
        ]
    )
    session.add(
        ChangeRequest(
            site_id=site.id,
            legacy_change_request_id=9100,
            scope_label="Điều chỉnh khu pha chế",
            submitted_on=date(2026, 8, 10),
            state=ChangeRequestState.RECEIVED,
        )
    )
    session.commit()
    return {"site_id": site.id}


def seed_certificate_workspace_catalog(session: Session):
    company = Company(
        legal_name="Công ty chứng nhận",
        short_name="CERT",
        legal_address="88 Trụ sở",
        assigned_specialist_text="Hà Hoàng Phương",
    )
    session.add(company)
    session.flush()
    site = Site(
        company_id=company.id,
        site_name="Cơ sở chứng nhận",
        site_address="KCN Chứng nhận",
        legacy_site_id=222,
        legacy_gmp_site_code="2.2",
    )
    session.add(site)
    session.flush()

    case_a = Case(
        site_id=site.id,
        gxp_type="GMP",
        scope_code="A",
        state=CaseState.CERTIFIED,
        legacy_inspection_id=4201,
        legacy_inspection_code="KT-GMP-A-2025",
        applicable_standard="WHO-GMP",
        inspection_type="Tái đánh giá",
        opened_year=2025,
    )
    case_b = Case(
        site_id=site.id,
        gxp_type="GMP",
        scope_code="B",
        state=CaseState.INSPECTION_COMPLETED,
        legacy_inspection_id=4202,
        legacy_inspection_code="KT-GMP-B-2026",
        applicable_standard="PIC/S-GMP",
        inspection_type="Định kỳ",
        opened_year=2026,
    )
    session.add_all([case_a, case_b])
    session.flush()

    session.add(
        CaseApplication(
            case_id=case_a.id,
            submitted_on=datetime(2025, 1, 2, tzinfo=timezone.utc),
            dossier_code="HS-GMP-A",
            dossier_reference="QĐ-TN-4201",
            applicant_name="Nguyễn Văn A",
        )
    )
    session.add(
        CaseAssessment(
            case_id=case_a.id,
            assessed_on=datetime(2025, 1, 6, tzinfo=timezone.utc),
            assessor_name="Hà Hoàng Phương",
            assessment_result="Đề xuất cấp chứng nhận GMP",
            notes="Đủ điều kiện theo hồ sơ",
        )
    )
    session.add(
        InspectionPlan(
            case_id=case_a.id,
            plan_start_on=date(2025, 1, 10),
            plan_end_on=date(2025, 1, 11),
            planning_sheet_name="KH-KT-4201",
            decision_document_hint="QĐ-KT-4201",
        )
    )
    session.add(
        InspectionTeam(
            case_id=case_a.id,
            display_text="Đoàn kiểm tra GMP dây chuyền A",
        )
    )
    session.add(
        InspectionOutcome(
            case_id=case_a.id,
            inspected_on=date(2025, 1, 10),
            inspected_to_on=date(2025, 1, 10),
            decision_reference="QĐ-KT-4201",
            bbkt_reference="BBKT-4201",
            outcome_result="Đạt WHO-GMP dây chuyền A",
        )
    )
    session.add_all(
        [
            InspectionEvent(
                case_id=case_a.id,
                event_type=InspectionEventType.APPLICATION_SUBMITTED,
                occurred_at=datetime(2025, 1, 2, 8, 0, tzinfo=timezone.utc),
                payload="HS-GMP-A",
            ),
            InspectionEvent(
                case_id=case_a.id,
                event_type=InspectionEventType.ASSESSMENT_COMPLETED,
                occurred_at=datetime(2025, 1, 6, 9, 0, tzinfo=timezone.utc),
                payload="Đề xuất cấp chứng nhận GMP",
            ),
            InspectionEvent(
                case_id=case_a.id,
                event_type=InspectionEventType.INSPECTION_EXECUTED,
                occurred_at=datetime(2025, 1, 10, 10, 0, tzinfo=timezone.utc),
                payload="QĐ-KT-4201",
            ),
            InspectionEvent(
                case_id=case_a.id,
                event_type=InspectionEventType.CERTIFICATE_ISSUED,
                occurred_at=datetime(2025, 4, 17, 10, 0, tzinfo=timezone.utc),
                payload="GMP",
            ),
        ]
    )
    session.add_all(
        [
            CapaCycle(
                case_id=case_a.id,
                round_no=1,
                requested_on=date(2025, 1, 12),
                submitted_on=date(2025, 1, 14),
                assessed_on=date(2025, 1, 20),
                assessor_name="Hà Hoàng Phương",
                result="Đạt",
                status="accepted",
                notes="Hoàn tất CAPA lần 1",
            ),
            CapaCycle(
                case_id=case_a.id,
                round_no=2,
                requested_on=date(2025, 2, 1),
                submitted_on=date(2025, 2, 3),
                assessed_on=date(2025, 2, 10),
                assessor_name="Hà Hoàng Phương",
                result="Đạt",
                status="accepted",
                notes="Hoàn tất CAPA lần 2",
            ),
        ]
    )
    session.flush()
    capa_round_1, capa_round_2 = session.scalars(select(CapaCycle).where(CapaCycle.case_id == case_a.id).order_by(CapaCycle.round_no.asc())).all()

    change_request = ChangeRequest(
        site_id=site.id,
        legacy_change_request_id=9101,
        scope_label="Đổi địa chỉ",
        description="Điều chỉnh địa chỉ kho bảo quản",
        submitted_on=date(2026, 8, 6),
        requester_name="Phòng QA",
        state=ChangeRequestState.UNDER_REVIEW,
    )
    session.add(change_request)
    session.flush()
    session.add(
        ChangeApproval(
            change_request_id=change_request.id,
            handled_on=date(2026, 8, 7),
            handled_by_name="Hà Hoàng Phương",
            result_label="Đang thẩm tra hồ sơ thay đổi",
            effective_on=None,
            approval_reference=None,
        )
    )
    session.add(
        ChangeRequestDetail(
            change_request_id=change_request.id,
            legacy_change_detail_id=501,
            classification_id=1,
            classification_label="Đổi địa chỉ",
            approval_status=None,
            old_value="Địa chỉ cũ",
            new_value="Địa chỉ mới",
            note=None,
        )
    )

    cert_a_new = Certificate(site_id=site.id, case_id=case_a.id, certificate_type="GMP", line_code="A", latest_flag=True)
    cert_a_old = Certificate(site_id=site.id, case_id=case_a.id, certificate_type="GMP", line_code="A", latest_flag=False)
    cert_facility = Certificate(
        site_id=site.id,
        case_id=None,
        certificate_type="GMP",
        line_code=None,
        latest_flag=False,
        issuance_basis="administrative_no_inspection",
    )
    cert_b = Certificate(site_id=site.id, case_id=case_b.id, certificate_type="GMP", line_code="B", latest_flag=True)
    session.add_all([cert_a_new, cert_a_old, cert_facility, cert_b])
    session.flush()

    version_a_new = CertificateVersion(
        certificate_id=cert_a_new.id,
        version_no=1,
        issue_date=date(2025, 4, 17),
        expiry_date=date(2027, 4, 17),
        certificate_number="195/GCN-QLD",
        applicable_standard="WHO-GMP",
        issuing_authority="Cục Quản lý Dược Việt Nam",
        is_latest_version=True,
    )
    version_a_old = CertificateVersion(
        certificate_id=cert_a_old.id,
        version_no=1,
        issue_date=date(2021, 9, 14),
        expiry_date=date(2027, 9, 14),
        certificate_number="533/GCN-QLD",
        applicable_standard="WHO-GMP",
        issuing_authority="Cục Quản lý Dược Việt Nam",
        is_latest_version=True,
    )
    version_facility = CertificateVersion(
        certificate_id=cert_facility.id,
        version_no=1,
        issue_date=date(2020, 5, 1),
        expiry_date=date(2023, 5, 1),
        certificate_number="ADMIN-001",
        applicable_standard="WHO-GMP",
        issuing_authority="Bộ Y tế",
        is_latest_version=True,
    )
    version_b = CertificateVersion(
        certificate_id=cert_b.id,
        version_no=1,
        issue_date=date(2026, 6, 1),
        expiry_date=date(2028, 6, 1),
        certificate_number="B-001",
        applicable_standard="PIC/S-GMP",
        issuing_authority="Cục Quản lý Dược Việt Nam",
        is_latest_version=True,
    )
    session.add_all([version_a_new, version_a_old, version_facility, version_b])
    session.flush()
    session.add_all(
        [
            CertificateScope(
                certificate_version_id=version_a_new.id,
                scope_key="A",
                scope_text="Thuốc không vô trùng",
                sort_order=1,
            ),
            CertificateScope(
                certificate_version_id=version_a_old.id,
                scope_key="A",
                scope_text="Thuốc không vô trùng cũ",
                sort_order=1,
            ),
            CertificateScope(
                certificate_version_id=version_b.id,
                scope_key="B",
                scope_text="Dây chuyền B",
                sort_order=1,
            ),
        ]
    )

    dkkd_previous = BusinessEligibilityCertificate(
        site_id=site.id,
        company_id=company.id,
        legacy_dkkd_id=700,
        latest_flag=False,
    )
    dkkd_current = BusinessEligibilityCertificate(
        site_id=site.id,
        company_id=company.id,
        legacy_dkkd_id=701,
        latest_flag=True,
        replaces_legacy_dkkd_id=700,
    )
    session.add_all([dkkd_previous, dkkd_current])
    session.flush()
    previous_version = BusinessEligibilityVersion(
        business_eligibility_certificate_id=dkkd_previous.id,
        version_no=1,
        certificate_number="703/ĐKKDD-BYT",
        issued_on=date(2022, 5, 30),
        issuance_sequence_text="4",
    )
    current_version = BusinessEligibilityVersion(
        business_eligibility_certificate_id=dkkd_current.id,
        version_no=1,
        certificate_number="1201/ĐKKDD-BYT",
        issued_on=date(2025, 6, 9),
        decision_reference="QĐ-1201",
        issuance_sequence_text="5",
        issuance_history_text="Lần 1, Lần 2, Lần 3, Lần 4, Lần 5",
        professional_responsible_person_name="Nguyễn Khắc Minh",
        quality_assurance_person_name="Võ Việt Hùng",
        professional_qualification_text="Dược sĩ đại học",
        professional_license_number="2241/BD-CCHND",
        professional_license_issued_on=date(2013, 8, 8),
        professional_license_issuer="Sở Y tế",
        responsible_license_issued_on=date(2020, 7, 14),
        responsible_license_issuer="Sở Y tế Hà Tĩnh",
        business_activity_text="Bán buôn thuốc",
        current_status_text="Chưa cấp chứng chỉ",
        handled_by_name="Hà Hoàng Phương",
        application_dossier_reference="HS-001",
    )
    session.add_all([previous_version, current_version])
    session.flush()
    session.add(
        BusinessEligibilityCertificateLink(
            business_eligibility_version_id=current_version.id,
            certificate_id=cert_a_new.id,
            link_role="source_certificate",
        )
    )
    case_document = Document(
        family_code="CERTIFICATE_DECISION",
        document_type_code="CERTIFICATE_DECISION",
        title="Certificate Decision",
        case_id=case_a.id,
    )
    capa_document = Document(
        family_code="INSPECTION_CAPA_LAN_1",
        document_type_code="INSPECTION_CAPA_LAN_1",
        title="Đánh giá CAPA 1",
        case_id=case_a.id,
        capa_cycle_id=capa_round_1.id,
    )
    change_document = Document(
        family_code="NAME_ADDRESS_CHANGE_LETTER",
        document_type_code="NAME_ADDRESS_CHANGE_LETTER",
        title="Đổi tên, địa chỉ",
        change_request_id=change_request.id,
    )
    session.add_all([case_document, capa_document, change_document])
    session.flush()

    case_variant = DocumentVariant(
        document_id=case_document.id,
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        language_code="vi",
        is_active=True,
    )
    capa_variant = DocumentVariant(
        document_id=capa_document.id,
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        language_code="vi",
        is_active=True,
    )
    change_variant = DocumentVariant(
        document_id=change_document.id,
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        language_code="vi",
        is_active=True,
    )
    session.add_all([case_variant, capa_variant, change_variant])
    session.flush()
    session.add_all(
        [
            DocumentVersion(
                document_variant_id=case_variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root=None,
                storage_relative_path=None,
                original_filename="8 qd cap cc GMP.docx",
                checksum_sha256=None,
                is_current=True,
                issued_on=datetime(2025, 4, 17, tzinfo=timezone.utc),
            ),
            DocumentVersion(
                document_variant_id=capa_variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root=None,
                storage_relative_path=None,
                original_filename="5. Danh gia CAPA - GMP.dotx",
                checksum_sha256=None,
                is_current=True,
                issued_on=datetime(2025, 1, 20, tzinfo=timezone.utc),
            ),
            DocumentVersion(
                document_variant_id=change_variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root=None,
                storage_relative_path=None,
                original_filename="doi-ten-dia-chi.docx",
                checksum_sha256=None,
                is_current=True,
                issued_on=datetime(2026, 8, 8, tzinfo=timezone.utc),
            ),
        ]
    )
    session.commit()
    return {
        "site_id": site.id,
        "case_ids": {
            "a": case_a.id,
            "b": case_b.id,
        },
        "change_request_ids": {
            "primary": change_request.id,
        },
        "gxp_certificate_ids": {
            "a_new": cert_a_new.id,
            "a_old": cert_a_old.id,
            "facility": cert_facility.id,
            "b": cert_b.id,
        },
        "eligibility_certificate_ids": {
            "current": dkkd_current.id,
            "previous": dkkd_previous.id,
        },
    }


def test_catalog_manual_response_constructors_populate_all_required_schema_fields():
    router_path = ROOT / "backend" / "app" / "api" / "routers" / "catalog.py"
    tree = ast.parse(router_path.read_text(encoding="utf-8"))
    models = {
        "CompanyRead": CompanyRead,
        "SiteRead": SiteRead,
        "CaseRead": CaseRead,
        "CompanyDetailRead": CompanyDetailRead,
        "SiteDetailRead": SiteDetailRead,
        "CaseDetailRead": CaseDetailRead,
        "FacilitySearchPageRead": FacilitySearchPageRead,
    }
    seen_models: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        model_name = node.func.id
        if model_name not in models:
            continue
        seen_models.add(model_name)
        keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
        required_fields = {
            field_name
            for field_name, field in models[model_name].model_fields.items()
            if field.is_required()
        }
        assert keyword_names == required_fields, f"{model_name} constructor fields drifted from response schema"

    assert seen_models == set(models)


def test_search_facilities_and_workspace_keep_current_semantics_inside_selected_gxp(tmp_path):
    database_path = tmp_path / "catalog-cross-gxp.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_cross_gxp_catalog(session)

    app = create_app(database_url)
    search_route = next(route for route in app.routes if getattr(route, "path", "") == "/search/facilities")
    workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/sites/{site_id}/workspace")

    with Session(engine) as session:
        gmp_search = search_route.endpoint(
            q=None,
            gxp_type="GMP",
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        glp_search = search_route.endpoint(
            q=None,
            gxp_type="GLP",
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        gmp_workspace = workspace_route.endpoint(
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code=None,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        glp_workspace = workspace_route.endpoint(
            site_id=seeded["site_id"],
            gxp_type="GLP",
            line_code=None,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert gmp_search.total_count == 1
    assert len(gmp_search.items) == 1
    assert gmp_search.items[0].context_code == "GMP-501"
    assert gmp_search.items[0].line_code is None
    assert gmp_search.items[0].gxp_type == "GMP"
    assert gmp_search.items[0].last_inspection_on == date(2025, 5, 20)
    assert gmp_search.items[0].current_state == "inspection_completed"
    assert gmp_search.items[0].current_certificate_number == "GCN-GMP-001"
    assert gmp_search.items[0].certificate_scope_summary is None

    assert glp_search.total_count == 1
    assert len(glp_search.items) == 1
    assert glp_search.items[0].context_code == "GLP-501"
    assert glp_search.items[0].line_code is None
    assert glp_search.items[0].gxp_type == "GLP"
    assert glp_search.items[0].last_inspection_on == date(2026, 7, 15)
    assert glp_search.items[0].current_state == "awaiting_certificate_decision"
    assert glp_search.items[0].current_certificate_number == "GCN-GLP-009"

    assert gmp_workspace.summary.selected_gxp_type == "GMP"
    assert gmp_workspace.summary.primary_standard == "WHO-GMP"
    assert gmp_workspace.summary.current_state == "inspection_completed"
    assert gmp_workspace.summary.current_certificate_number == "GCN-GMP-001"
    assert [item.reference_code for item in gmp_workspace.history if item.source_type == "case"] == ["KT-GMP-2025"]

    assert glp_workspace.summary.selected_gxp_type == "GLP"
    assert glp_workspace.summary.primary_standard == "GLP-WHO"
    assert glp_workspace.summary.current_state == "awaiting_certificate_decision"
    assert glp_workspace.summary.current_certificate_number == "GCN-GLP-009"
    assert [item.reference_code for item in glp_workspace.history if item.source_type == "case"] == ["KT-GLP-2026"]


def test_search_facilities_and_workspace_preserve_production_line_context_and_certificate_scope(tmp_path):
    database_path = tmp_path / "catalog-line-grain.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_line_grain_catalog(session)

    app = create_app(database_url)
    search_route = next(route for route in app.routes if getattr(route, "path", "") == "/search/facilities")
    workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/sites/{site_id}/workspace")

    with Session(engine) as session:
        search_payload = search_route.endpoint(
            q=None,
            gxp_type="GMP",
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=80,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        workspace_payload = workspace_route.endpoint(
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="A",
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert search_payload.total_count == 3
    assert [row.context_code for row in search_payload.items] == ["1.1A", "1.1B", "1.1C"]
    assert [row.line_code for row in search_payload.items] == ["A", "B", "C"]
    assert [row.result_grain for row in search_payload.items] == ["production_line", "production_line", "production_line"]
    assert search_payload.items[0].gxp_type == "GMP"
    assert search_payload.items[0].certificate_scope_summary == "Dây chuyền viên nén A"
    assert search_payload.items[0].certificate_scope_summary != search_payload.items[0].current_state
    assert search_payload.items[1].certificate_scope_summary == "Dây chuyền thuốc bột B"
    assert search_payload.items[2].certificate_scope_summary is None

    assert workspace_payload.summary.context_code == "1.1A"
    assert workspace_payload.summary.selected_line_code == "A"
    assert workspace_payload.summary.context_grain == "production_line"
    assert workspace_payload.summary.company_legal_address == "123 Trụ sở chính"
    assert workspace_payload.summary.current_certificate_issue_date == date(2026, 6, 1)
    assert workspace_payload.summary.current_certificate_expiry == date(2027, 6, 1)
    assert workspace_payload.summary.current_certificate_standard == "WHO-GMP"
    assert workspace_payload.summary.current_certificate_status == "active"
    assert workspace_payload.summary.certificate_scope_summary == "Dây chuyền viên nén A"
    assert workspace_payload.summary.primary_standard == "WHO-GMP"
    assert [item.reference_code for item in workspace_payload.history if item.source_type == "case"] == ["KT-GMP-A"]
    assert any(item.source_type == "change_request" for item in workspace_payload.history)


def test_search_facilities_suppresses_facility_context_when_same_site_gxp_has_authoritative_lines(tmp_path):
    database_path = tmp_path / "catalog-search-null-suppression.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty suppress", short_name="SUP")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Cơ sở suppress", province_name="Hà Nội", legacy_site_id=12, legacy_gmp_site_code="1.2")
        session.add(site)
        session.flush()
        session.add_all(
            [
                Case(site_id=site.id, gxp_type="GMP", scope_code=None, state=CaseState.PLANNED, opened_year=2026),
                Case(site_id=site.id, gxp_type="GMP", scope_code="A", state=CaseState.UNDER_ASSESSMENT, opened_year=2026),
                Case(site_id=site.id, gxp_type="GMP", scope_code="B", state=CaseState.INSPECTION_IN_PROGRESS, opened_year=2026),
            ]
        )
        session.commit()
        site_id = site.id

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
        )
        workspace = service.get_facility_workspace(session, site_id=site_id, gxp_type="GMP", line_code="A")

    assert payload["total_count"] == 2
    assert [row["context_code"] for row in payload["items"]] == ["1.2A", "1.2B"]
    assert [row["line_code"] for row in payload["items"]] == ["A", "B"]
    assert all(row["result_grain"] == "production_line" for row in payload["items"])
    assert {row["result_key"] for row in payload["items"]} == {f"{site_id}:GMP:A", f"{site_id}:GMP:B"}
    assert workspace["summary"]["selected_line_code"] == "A"


def test_search_facilities_keeps_facility_context_when_site_gxp_has_no_authoritative_lines(tmp_path):
    database_path = tmp_path / "catalog-search-facility-only.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty facility", short_name="FAC")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Cơ sở facility", province_name="Đà Nẵng", legacy_site_id=54, legacy_gmp_site_code="5.4")
        session.add(site)
        session.flush()
        session.add(Case(site_id=site.id, gxp_type="GMP", scope_code=None, state=CaseState.PLANNED, opened_year=2026))
        session.commit()
        site_id = site.id

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
        )
        workspace = service.get_facility_workspace(session, site_id=site_id, gxp_type="GMP", line_code=None)

    assert payload["total_count"] == 1
    assert [row["context_code"] for row in payload["items"]] == ["5.4"]
    assert payload["items"][0]["line_code"] is None
    assert payload["items"][0]["result_grain"] == "facility"
    assert workspace["summary"]["selected_line_code"] is None


def test_search_facilities_suppresses_facility_row_when_line_case_uses_facility_wide_current_certificate(tmp_path):
    database_path = tmp_path / "catalog-search-facility-cert-fallback.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty cert fallback", short_name="CFB")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Cơ sở cert fallback", province_name="Hà Nội", legacy_site_id=88, legacy_gmp_site_code="8.8")
        session.add(site)
        session.flush()
        case_a = Case(
            site_id=site.id,
            gxp_type="GMP",
            scope_code="A",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
            legacy_inspection_code="KT-88-A",
            opened_year=2026,
        )
        session.add(case_a)
        session.flush()
        certificate = Certificate(site_id=site.id, case_id=None, certificate_type="GMP", line_code=None, latest_flag=True)
        session.add(certificate)
        session.flush()
        session.add(
            CertificateVersion(
                certificate_id=certificate.id,
                version_no=1,
                issue_date=date(2026, 5, 1),
                expiry_date=date(2027, 5, 1),
                certificate_number="GCN-FACILITY",
                is_latest_version=True,
            )
        )
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state="active",
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
        )

    assert payload["total_count"] == 1
    assert [row["context_code"] for row in payload["items"]] == ["8.8A"]
    assert payload["items"][0]["line_code"] == "A"
    assert payload["items"][0]["current_certificate_number"] == "GCN-FACILITY"


def test_search_facilities_suppresses_facility_row_when_certificate_has_line_and_facility_versions(tmp_path):
    database_path = tmp_path / "catalog-search-certificate-line-and-facility.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty cert line", short_name="CCL")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Cơ sở cert line", province_name="Hà Nội", legacy_site_id=99, legacy_gmp_site_code="9.9")
        session.add(site)
        session.flush()
        certificate_line = Certificate(site_id=site.id, case_id=None, certificate_type="GMP", line_code="A", latest_flag=True)
        certificate_facility = Certificate(site_id=site.id, case_id=None, certificate_type="GMP", line_code=None, latest_flag=True)
        session.add_all([certificate_line, certificate_facility])
        session.flush()
        session.add_all(
            [
                CertificateVersion(
                    certificate_id=certificate_line.id,
                    version_no=1,
                    issue_date=date(2026, 5, 1),
                    expiry_date=date(2027, 5, 1),
                    certificate_number="GCN-A",
                    is_latest_version=True,
                ),
                CertificateVersion(
                    certificate_id=certificate_facility.id,
                    version_no=1,
                    issue_date=date(2026, 4, 1),
                    expiry_date=date(2027, 4, 1),
                    certificate_number="GCN-FACILITY",
                    is_latest_version=True,
                ),
            ]
        )
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state="active",
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
        )

    assert payload["total_count"] == 1
    assert [row["context_code"] for row in payload["items"]] == ["9.9A"]
    assert payload["items"][0]["line_code"] == "A"
    assert payload["items"][0]["result_grain"] == "production_line"


def test_search_facilities_keeps_line_contexts_per_gxp_and_facility_context_for_other_gxp(tmp_path):
    database_path = tmp_path / "catalog-search-cross-gxp-null-suppression.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty cross gxp", short_name="XGP")
        session.add(company)
        session.flush()
        site = Site(
            company_id=company.id,
            site_name="Cơ sở cross gxp",
            province_name="Hải Phòng",
            legacy_site_id=71,
            legacy_gmp_site_code="7.1",
            legacy_glp_site_code="7.1",
        )
        session.add(site)
        session.flush()
        session.add_all(
            [
                Case(site_id=site.id, gxp_type="GMP", scope_code=None, state=CaseState.PLANNED, opened_year=2026),
                Case(site_id=site.id, gxp_type="GMP", scope_code="A", state=CaseState.UNDER_ASSESSMENT, opened_year=2026),
                Case(site_id=site.id, gxp_type="GLP", scope_code=None, state=CaseState.PLANNED, opened_year=2026),
            ]
        )
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.search_facilities(
            session,
            q=None,
            gxp_type=None,
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
        )

    assert payload["total_count"] == 2
    assert [row["context_code"] for row in payload["items"]] == ["7.1", "7.1A"]
    assert [row["gxp_type"] for row in payload["items"]] == ["GLP", "GMP"]
    assert [row["line_code"] for row in payload["items"]] == [None, "A"]


def test_search_facilities_applies_null_context_suppression_before_filters_and_paging(tmp_path):
    database_path = tmp_path / "catalog-search-filtered-null-suppression.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty filter suppress", short_name="FSUP")
        session.add(company)
        session.flush()
        site = Site(
            company_id=company.id,
            site_name="Nhà máy Filter",
            province_name="Hà Nội",
            legacy_site_id=120,
            legacy_gmp_site_code="1.2",
        )
        session.add(site)
        session.flush()
        session.add_all(
            [
                Case(
                    site_id=site.id,
                    gxp_type="GMP",
                    scope_code=None,
                    state=CaseState.PLANNED,
                    legacy_inspection_code="KT-NULL",
                    applicable_standard="WHO-GMP",
                    opened_year=2026,
                ),
                Case(
                    site_id=site.id,
                    gxp_type="GMP",
                    scope_code="A",
                    state=CaseState.INSPECTION_IN_PROGRESS,
                    legacy_inspection_code="KT-LINE-A",
                    applicable_standard="WHO-GMP",
                    opened_year=2026,
                ),
                Case(
                    site_id=site.id,
                    gxp_type="GMP",
                    scope_code="B",
                    state=CaseState.PLANNED,
                    legacy_inspection_code="KT-LINE-B",
                    applicable_standard="PIC/S-GMP",
                    opened_year=2026,
                ),
            ]
        )
        facility_certificate = Certificate(site_id=site.id, case_id=None, certificate_type="GMP", line_code=None, latest_flag=True)
        line_certificate = Certificate(site_id=site.id, case_id=None, certificate_type="GMP", line_code="A", latest_flag=True)
        session.add_all([facility_certificate, line_certificate])
        session.flush()
        facility_version = CertificateVersion(
            certificate_id=facility_certificate.id,
            version_no=1,
            issue_date=date.today() - timedelta(days=30),
            expiry_date=date.today() + timedelta(days=30),
            certificate_number="GCN-FILTER-FACILITY",
            is_latest_version=True,
        )
        line_version = CertificateVersion(
            certificate_id=line_certificate.id,
            version_no=1,
            issue_date=date.today() - timedelta(days=10),
            expiry_date=date.today() + timedelta(days=10),
            certificate_number="GCN-FILTER-A",
            is_latest_version=True,
        )
        session.add_all([facility_version, line_version])
        session.flush()
        session.add_all(
            [
                CertificateScope(
                    certificate_version_id=facility_version.id,
                    scope_key=None,
                    scope_text="Phạm vi dùng chung facility",
                    sort_order=1,
                ),
                CertificateScope(
                    certificate_version_id=line_version.id,
                    scope_key="A",
                    scope_text="Dây chuyền A filter",
                    sort_order=1,
                ),
            ]
        )
        session.commit()

    service = CatalogReadService()
    search_kwargs = dict(
        province=None,
        gxp_type="GMP",
        change_request_states=None,
        offset=0,
        limit=10,
    )
    with Session(engine) as session:
        unfiltered = service.search_facilities(
            session,
            q=None,
            facility_name=None,
            certificate_scope=None,
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            **search_kwargs,
        )
        by_name = service.search_facilities(
            session,
            q=None,
            facility_name="Filter",
            certificate_scope=None,
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            **search_kwargs,
        )
        by_q = service.search_facilities(
            session,
            q="GCN-FILTER",
            facility_name=None,
            certificate_scope=None,
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            **search_kwargs,
        )
        by_scope = service.search_facilities(
            session,
            q=None,
            facility_name=None,
            certificate_scope="facility",
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            **search_kwargs,
        )
        by_case_state = service.search_facilities(
            session,
            q=None,
            facility_name=None,
            certificate_scope=None,
            case_states=[CaseState.PLANNED.value, CaseState.INSPECTION_IN_PROGRESS.value],
            certificate_state=None,
            certificate_expiring_within_days=None,
            **search_kwargs,
        )
        by_active_certificate = service.search_facilities(
            session,
            q=None,
            facility_name=None,
            certificate_scope=None,
            case_states=None,
            certificate_state="active",
            certificate_expiring_within_days=None,
            **search_kwargs,
        )
        by_expiring_certificate = service.search_facilities(
            session,
            q=None,
            facility_name=None,
            certificate_scope=None,
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=90,
            **search_kwargs,
        )
        first_page = service.search_facilities(
            session,
            q=None,
            facility_name=None,
            certificate_scope=None,
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            province=None,
            gxp_type="GMP",
            change_request_states=None,
            offset=0,
            limit=1,
        )
        second_page = service.search_facilities(
            session,
            q=None,
            facility_name=None,
            certificate_scope=None,
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            province=None,
            gxp_type="GMP",
            change_request_states=None,
            offset=1,
            limit=1,
        )

    expected_contexts = ["1.2A", "1.2B"]
    for payload in [unfiltered, by_name, by_q, by_scope, by_case_state, by_active_certificate, by_expiring_certificate]:
        assert payload["total_count"] == 2
        assert [row["context_code"] for row in payload["items"]] == expected_contexts
        assert all(row["line_code"] in {"A", "B"} for row in payload["items"])

    assert first_page["total_count"] == 2
    assert second_page["total_count"] == 2
    assert [row["context_code"] for row in first_page["items"]] == ["1.2A"]
    assert [row["context_code"] for row in second_page["items"]] == ["1.2B"]
    assert {row["result_key"] for row in first_page["items"]}.isdisjoint({row["result_key"] for row in second_page["items"]})


def test_gxp_certificate_workspace_reads_history_and_detail_with_line_safe_filtering(tmp_path):
    database_path = tmp_path / "catalog-gxp-workspace.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.list_site_gxp_certificates(
            session,
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="A",
        )
        active_detail = service.get_gxp_certificate_detail(session, certificate_id=seeded["gxp_certificate_ids"]["a_new"])
        superseded_detail = service.get_gxp_certificate_detail(session, certificate_id=seeded["gxp_certificate_ids"]["a_old"])
        expired_detail = service.get_gxp_certificate_detail(session, certificate_id=seeded["gxp_certificate_ids"]["facility"])

    assert [item["certificate_number"] for item in payload["items"]] == ["195/GCN-QLD", "533/GCN-QLD", "ADMIN-001"]
    assert [item["status"] for item in payload["items"]] == ["active", "superseded", "expired"]
    assert [item["context_match_kind"] for item in payload["items"]] == ["exact_line", "exact_line", "facility_wide"]
    assert all(item["line_code"] in {"A", None} for item in payload["items"])
    assert all(item["certificate_number"] != "B-001" for item in payload["items"])

    assert active_detail["certificate_number"] == "195/GCN-QLD"
    assert active_detail["line_code"] == "A"
    assert active_detail["scope_summary"] == "Thuốc không vô trùng"
    assert active_detail["issuing_authority"] == "Cục Quản lý Dược Việt Nam"
    assert active_detail["status"] == "active"
    assert active_detail["source_description"] == "Đợt kiểm tra GMP ngày 10-01-2025"
    assert active_detail["limitation_text"] is None

    assert superseded_detail["certificate_number"] == "533/GCN-QLD"
    assert superseded_detail["status"] == "superseded"
    assert superseded_detail["expiry_date"] == date(2027, 9, 14)

    assert expired_detail["certificate_number"] == "ADMIN-001"
    assert expired_detail["status"] == "expired"
    assert expired_detail["source_description"] == "Cấp hành chính không gắn đợt kiểm tra"


def test_business_eligibility_workspace_reads_history_detail_and_linked_gxp_basis(tmp_path):
    database_path = tmp_path / "catalog-dkkd-workspace.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.list_site_business_eligibility_certificates(session, site_id=seeded["site_id"])
        detail = service.get_business_eligibility_detail(
            session,
            business_eligibility_certificate_id=seeded["eligibility_certificate_ids"]["current"],
        )

    assert [item["certificate_number"] for item in payload["items"]] == ["1201/ĐKKDD-BYT", "703/ĐKKDD-BYT"]
    assert payload["items"][0]["issuance_sequence_text"] == "5"
    assert payload["items"][0]["current_status_text"] == "Chưa cấp chứng chỉ"

    assert detail["certificate_number"] == "1201/ĐKKDD-BYT"
    assert detail["decision_reference"] == "QĐ-1201"
    assert detail["issuance_sequence_text"] == "5"
    assert detail["professional_responsible_person_name"] == "Nguyễn Khắc Minh"
    assert detail["quality_assurance_person_name"] == "Võ Việt Hùng"
    assert detail["professional_license_number"] == "2241/BD-CCHND"
    assert detail["current_status_text"] == "Chưa cấp chứng chỉ"
    assert detail["replaces_certificate_number"] == "703/ĐKKDD-BYT"
    assert detail["replaced_by_certificate_number"] is None
    assert detail["linked_gxp_certificates"] == [
        {
            "certificate_id": seeded["gxp_certificate_ids"]["a_new"],
            "certificate_type": "GMP",
            "line_code": "A",
            "certificate_number": "195/GCN-QLD",
            "issue_date": date(2025, 4, 17),
            "link_role": "source_certificate",
        }
    ]


def test_case_workspace_reads_owner_correct_sections_and_direct_links_only(tmp_path):
    database_path = tmp_path / "catalog-case-workspace.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    app = create_app(database_url)
    case_workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/workspace")

    with Session(engine) as session:
        payload = case_workspace_route.endpoint(
            case_id=seeded["case_ids"]["a"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert payload.case_summary.legacy_inspection_code == "KT-GMP-A-2025"
    assert payload.case_summary.gxp_type == "GMP"
    assert payload.case_summary.scope_code == "A"
    assert payload.application.dossier_code == "HS-GMP-A"
    assert payload.application.assigned_specialist == "Hà Hoàng Phương"
    assert payload.application.assigned_specialist_source == "company_master"
    assert payload.inspection.decision_reference == "QĐ-KT-4201"
    assert payload.inspection.planning_sheet_name == "KH-KT-4201"
    assert payload.inspection.bbkt_reference == "BBKT-4201"
    assert payload.inspection.team_display_text == "Đoàn kiểm tra GMP dây chuyền A"
    assert payload.inspection.outcome_result == "Đạt WHO-GMP dây chuyền A"
    assert [cycle.round_no for cycle in payload.remediation.cycles] == [1, 2]
    assert payload.processing.assessment_result == "Đề xuất cấp chứng nhận GMP"
    assert [event.event_type for event in payload.processing.events] == [
        "application_submitted",
        "assessment_completed",
        "inspection_executed",
        "certificate_issued",
    ]
    assert [row.certificate_number for row in payload.linked_gxp_certificates] == ["195/GCN-QLD", "533/GCN-QLD"]
    assert all(row.case_id == seeded["case_ids"]["a"] for row in payload.linked_gxp_certificates)
    assert all(row.certificate_number != "ADMIN-001" for row in payload.linked_gxp_certificates)
    assert all(row.certificate_number != "B-001" for row in payload.linked_gxp_certificates)
    assert [row.certificate_number for row in payload.linked_business_eligibility_certificates] == ["1201/ĐKKDD-BYT"]
    basis_certificates = payload.linked_business_eligibility_certificates[0].linked_gxp_certificates
    assert len(basis_certificates) == 1
    assert basis_certificates[0].certificate_id == seeded["gxp_certificate_ids"]["a_new"]
    assert basis_certificates[0].certificate_type == "GMP"
    assert basis_certificates[0].line_code == "A"
    assert basis_certificates[0].certificate_number == "195/GCN-QLD"
    assert basis_certificates[0].issue_date == date(2025, 4, 17)
    assert basis_certificates[0].link_role == "source_certificate"
    document_items = {item.label: item for item in payload.documents.items}
    assert document_items["QĐ cấp CC"].status == "available"
    assert document_items["QĐ cấp CC"].original_filename == "8 qd cap cc GMP.docx"
    assert document_items["Quyết định kiểm tra"].status == "missing"
    assert document_items["Đánh giá CAPA 1"].status == "available"
    assert document_items["Đánh giá CAPA 2"].status == "missing"


def test_case_workspace_ignores_legacy_processing_free_text_without_structured_owner_mapping(tmp_path):
    database_path = tmp_path / "catalog-case-processing-free-text.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    snapshot = {
        "db.cty": [
            {"ID": "1", "TÊN CÔNG TY": "Công ty UAT", "COMPANY NAME": "UAT Co", "TÊN VIẾT TẮT": "UAT"},
        ],
        "db.cso": [
            {
                "ID": "2",
                "ID Cty": "1",
                "TÊN CƠ SỞ": "Cơ sở UAT",
                "SITE NAME": "UAT Site",
                "ĐỊA CHỈ CƠ SỞ": "Địa chỉ cơ sở",
                "SITE ADDRESS": "Site address",
                "TỈNH/TP": "Hồ Chí Minh",
            },
        ],
        "db.ktra": [
            {
                "ID": "4201",
                "ID CƠ SỞ": "2",
                "LOẠI KT": "GMP",
                "MÃ DC": "A",
                "LOẠI KIỂM TRA": "Tái đánh giá",
                "TIẾN ĐỘ XỬ LÝ": "Chờ trình lãnh đạo ký quyết định",
                "Ngày nộp": "",
                "Ngày thẩm định": "",
                "Kết quả": "",
                "Q. định": "",
                "B. bản": "",
                "Ngày K.tra": "",
            },
        ],
        "db.cc": [],
        "db.dkkd": [],
        "db.Tdoi": [],
        "db.Tdoi2": [],
    }

    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()

    app = create_app(database_url)
    case_workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/workspace")

    with Session(engine) as session:
        case = session.scalar(select(Case).where(Case.legacy_inspection_id == 4201))
        payload = case_workspace_route.endpoint(
            case_id=case.id,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert payload.processing.assessed_on is None
    assert payload.processing.assessor_name is None
    assert payload.processing.assessment_result is None
    assert payload.processing.notes is None
    assert payload.processing.events == []
    assert payload.case_summary.state == "application_received"


def test_facility_workspace_exposes_fail_closed_action_readiness_from_backend_contract(tmp_path):
    database_path = tmp_path / "catalog-facility-action-readiness.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    app = create_app(database_url)
    facility_workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/sites/{site_id}/workspace")

    with Session(engine) as session:
        payload = facility_workspace_route.endpoint(
            site_id=seeded["site_id"],
            gxp_type="GMP",
            line_code="A",
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    action_readiness = {item.action_key: item for item in payload.action_readiness}
    assert list(action_readiness) == [
        "create_company",
        "create_site",
        "create_production_line",
        "create_inspection_case",
        "create_reassessment_case",
        "create_change_request",
    ]
    assert all(item.readiness_status == "missing_contract" for item in action_readiness.values())
    assert action_readiness["create_company"].detail == "Chưa có canonical backend write contract để tạo công ty mới."
    assert action_readiness["create_inspection_case"].detail.endswith("để mở hồ sơ kiểm tra mới cho ngữ cảnh GMP.")
    assert action_readiness["create_change_request"].detail == (
        "Change request hiện mới có canonical read model; chưa có authenticated write contract để tạo mới."
    )
    assert all(item.required_permissions == [] for item in action_readiness.values())


def test_change_request_workspace_reads_authoritative_change_sections_and_document_checklist(tmp_path):
    database_path = tmp_path / "catalog-change-request-workspace.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    app = create_app(database_url)
    change_workspace_route = next(
        route for route in app.routes if getattr(route, "path", "") == "/change-requests/{change_request_id}/workspace"
    )

    with Session(engine) as session:
        payload = change_workspace_route.endpoint(
            change_request_id=seeded["change_request_ids"]["primary"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert payload.legacy_change_request_id == 9101
    assert payload.facility_name == "Cơ sở chứng nhận"
    assert payload.company_name == "Công ty chứng nhận"
    assert payload.scope_label == "Đổi địa chỉ"
    assert payload.description == "Điều chỉnh địa chỉ kho bảo quản"
    assert payload.requester_name == "Phòng QA"
    assert payload.state == "under_review"
    assert payload.handled_by_name == "Hà Hoàng Phương"
    assert payload.result_label == "Đang thẩm tra hồ sơ thay đổi"
    assert len(payload.details) == 1
    assert payload.details[0].classification_label == "Đổi địa chỉ"
    assert payload.details[0].old_value == "Địa chỉ cũ"
    assert payload.details[0].new_value == "Địa chỉ mới"
    document_items = {item.label: item for item in payload.documents.items}
    assert document_items["Đổi tên, địa chỉ"].status == "available"
    assert document_items["Đổi tên, địa chỉ"].original_filename == "doi-ten-dia-chi.docx"
    assert document_items["CV đồng ý thay đổi"].status == "missing"


def test_case_and_change_request_workspace_load_document_checklists_from_clean_git_export(tmp_path, monkeypatch):
    database_path = tmp_path / "catalog-clean-export-workspace.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    export_root = _extract_git_archive(tmp_path / "clean-export")
    assert_required_phase5_runtime_artifacts_exist(export_root / "artifacts")
    assert not export_root.joinpath("artifacts", "phase5", "template_seed.db").exists()
    monkeypatch.setenv("GXP_ARTIFACTS_ROOT", export_root.joinpath("artifacts").as_posix())

    app = create_app(database_url)
    case_workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/workspace")
    change_workspace_route = next(
        route for route in app.routes if getattr(route, "path", "") == "/change-requests/{change_request_id}/workspace"
    )

    with Session(engine) as session:
        case_payload = case_workspace_route.endpoint(
            case_id=seeded["case_ids"]["a"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        change_payload = change_workspace_route.endpoint(
            change_request_id=seeded["change_request_ids"]["primary"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    case_document_items = {item.label: item for item in case_payload.documents.items}
    change_document_items = {item.label: item for item in change_payload.documents.items}
    assert case_document_items["QĐ cấp CC"].status == "available"
    assert change_document_items["Đổi tên, địa chỉ"].status == "available"
    assert all(item.parent_scope != "change_request" for item in case_payload.documents.items if item.label == "QĐ cấp CC")
    assert all(item.parent_scope == "change_request" for item in change_payload.documents.items if item.label == "Đổi tên, địa chỉ")


def test_imported_change_request_workspace_handles_effective_without_explicit_approval_fields(tmp_path):
    database_path = tmp_path / "catalog-imported-change-request-189.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    snapshot = {
        "db.cty": [
            {"ID": "1", "TÊN CÔNG TY": "Công ty UAT", "COMPANY NAME": "UAT Co", "TÊN VIẾT TẮT": "UAT"},
        ],
        "db.cso": [
            {
                "ID": "2",
                "ID Cty": "1",
                "TÊN CƠ SỞ": "Cơ sở UAT",
                "SITE NAME": "UAT Site",
                "ĐỊA CHỈ CƠ SỞ": "Địa chỉ cơ sở",
                "SITE ADDRESS": "Site address",
                "TỈNH/TP": "Hồ Chí Minh",
            },
        ],
        "db.ktra": [],
        "db.cc": [],
        "db.dkkd": [],
        "db.Tdoi": [
            {
                "ID": "189",
                "PHẠM VI": "",
                "MÔ TẢ": "Điều chỉnh cách ghi địa chỉ",
                "ID CƠ SỞ": "2",
                "Hồ sơ đề nghị": "237",
                "ĐƠN VỊ ĐỀ NGHỊ": "",
                "Ngày nộp": "2026-01-09 00:00:00+00:00",
                "Ngày xử lý": "",
                "Người xử lý": "",
                "Kết quả": "",
                "CV chấp nhận & ngày": "",
                "Ngày hiệu lực của TĐ": "2026-03-10 00:00:00+00:00",
                "GHI CHÚ": "",
            },
        ],
        "db.Tdoi2": [
            {
                "ID": "157",
                "ID Gốc": "189",
                "ID Phân loại": "",
                "PHÂN LOẠI": "Điều chỉnh cách ghi địa chỉ",
                "TÌNH TRẠNG CHẤP NHẬN": "",
                "THÔNG TIN CŨ": "Nº 22, road Nº 2, Viet Nam - Singapore II industrial zone",
                "THÔNG TIN MỚI": "No. 22, street no. 2, Viet Nam-Singapore industrial park II",
                "GHI CHÚ": "",
            },
        ],
    }

    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()

    app = create_app(database_url)
    change_workspace_route = next(
        route for route in app.routes if getattr(route, "path", "") == "/change-requests/{change_request_id}/workspace"
    )

    with Session(engine) as session:
        change_request = session.scalar(select(ChangeRequest).where(ChangeRequest.legacy_change_request_id == 189))
        payload = change_workspace_route.endpoint(
            change_request_id=change_request.id,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert payload.legacy_change_request_id == 189
    assert payload.scope_label is None
    assert payload.requester_name is None
    assert payload.handled_on is None
    assert payload.handled_by_name is None
    assert payload.result_label is None
    assert payload.approval_reference is None
    assert payload.effective_on == date(2026, 3, 10)
    assert len(payload.details) == 1
    assert payload.details[0].legacy_change_detail_id == 157
    assert payload.details[0].classification_label == "Điều chỉnh cách ghi địa chỉ"
    assert payload.details[0].new_value == "No. 22, street no. 2, Viet Nam-Singapore industrial park II"
    assert all(item.parent_scope == "change_request" for item in payload.documents.items)
    assert all(item.parent_id == change_request.id for item in payload.documents.items)


def test_change_request_workspace_allows_missing_approval_row(tmp_path):
    database_path = tmp_path / "catalog-change-request-no-approval.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)
        session.query(ChangeApproval).where(ChangeApproval.change_request_id == seeded["change_request_ids"]["primary"]).delete()
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.get_change_request_workspace(session, change_request_id=seeded["change_request_ids"]["primary"])

    assert payload["handled_on"] is None
    assert payload["handled_by_name"] is None
    assert payload["result_label"] is None
    assert payload["effective_on"] is None
    assert payload["approval_reference"] is None
    assert len(payload["details"]) == 1


def test_change_request_workspace_allows_missing_detail_rows_without_attaching_unrelated_details(tmp_path):
    database_path = tmp_path / "catalog-change-request-no-details.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)
        other_change_request = ChangeRequest(
            site_id=seeded["site_id"],
            legacy_change_request_id=9102,
            scope_label="Đổi kho",
            submitted_on=date(2026, 8, 8),
            state=ChangeRequestState.RECEIVED,
        )
        session.add(other_change_request)
        session.flush()
        session.add(
            ChangeRequestDetail(
                change_request_id=other_change_request.id,
                legacy_change_detail_id=777,
                classification_id=9,
                classification_label="Chi tiết không liên quan",
                approval_status="Không áp dụng",
                old_value="Old unrelated",
                new_value="New unrelated",
                note="Không được gắn sang request khác",
            )
        )
        session.query(ChangeRequestDetail).where(
            ChangeRequestDetail.change_request_id == seeded["change_request_ids"]["primary"]
        ).delete()
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.get_change_request_workspace(session, change_request_id=seeded["change_request_ids"]["primary"])

    assert payload["legacy_change_request_id"] == 9101
    assert payload["details"] == []

def test_case_workspace_document_checklist_keeps_multi_parent_document_inside_allowed_case_owner(tmp_path):
    database_path = tmp_path / "catalog-case-document-ownership.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)
        unrelated_change_request = ChangeRequest(
            site_id=seeded["site_id"],
            legacy_change_request_id=9102,
            scope_label="Thay đổi không liên quan",
            submitted_on=date(2026, 8, 9),
            state=ChangeRequestState.RECEIVED,
        )
        shared_document = Document(
            family_code="UNREGISTERED_SHARED_CASE",
            document_type_code="UNREGISTERED_SHARED_CASE",
            title="Tài liệu nhiều parent",
            case_id=seeded["case_ids"]["a"],
            change_request_id=unrelated_change_request.id,
        )
        session.add(unrelated_change_request)
        session.flush()
        shared_document.change_request_id = unrelated_change_request.id
        session.add(shared_document)
        session.flush()
        shared_variant = DocumentVariant(
            document_id=shared_document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(shared_variant)
        session.flush()
        session.add(
            DocumentVersion(
                document_variant_id=shared_variant.id,
                version_no=1,
                original_filename="shared-case.docx",
                is_current=True,
                issued_on=datetime(2026, 8, 10, tzinfo=timezone.utc),
            )
        )
        session.commit()

    app = create_app(database_url)
    case_workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/workspace")

    with Session(engine) as session:
        payload = case_workspace_route.endpoint(
            case_id=seeded["case_ids"]["a"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    shared_items = [item for item in payload.documents.items if item.family_code == "UNREGISTERED_SHARED_CASE"]
    assert len(shared_items) == 1
    assert shared_items[0].parent_scope == "case"
    assert shared_items[0].parent_id == seeded["case_ids"]["a"]
    assert shared_items[0].original_filename == "shared-case.docx"
    assert all(item.parent_scope != "change_request" for item in shared_items)


def test_change_request_workspace_document_checklist_keeps_multi_parent_document_inside_allowed_change_owner(tmp_path):
    database_path = tmp_path / "catalog-change-document-ownership.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)
        multi_parent_document = Document(
            family_code="UNREGISTERED_SHARED_CHANGE",
            document_type_code="UNREGISTERED_SHARED_CHANGE",
            title="Tài liệu thay đổi nhiều parent",
            case_id=seeded["case_ids"]["b"],
            change_request_id=seeded["change_request_ids"]["primary"],
        )
        session.add(multi_parent_document)
        session.flush()
        change_variant = DocumentVariant(
            document_id=multi_parent_document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add(change_variant)
        session.flush()
        session.add(
            DocumentVersion(
                document_variant_id=change_variant.id,
                version_no=1,
                original_filename="shared-change.docx",
                is_current=True,
                issued_on=datetime(2026, 8, 11, tzinfo=timezone.utc),
            )
        )
        session.commit()

    app = create_app(database_url)
    change_workspace_route = next(
        route for route in app.routes if getattr(route, "path", "") == "/change-requests/{change_request_id}/workspace"
    )

    with Session(engine) as session:
        payload = change_workspace_route.endpoint(
            change_request_id=seeded["change_request_ids"]["primary"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    shared_items = [item for item in payload.documents.items if item.family_code == "UNREGISTERED_SHARED_CHANGE"]
    assert len(shared_items) == 1
    assert shared_items[0].parent_scope == "change_request"
    assert shared_items[0].parent_id == seeded["change_request_ids"]["primary"]
    assert shared_items[0].original_filename == "shared-change.docx"
    assert all(item.parent_scope != "case" for item in shared_items)


def test_case_workspace_document_checklist_prefers_explicit_capa_owner_and_deduplicates_dynamic_families(tmp_path):
    database_path = tmp_path / "catalog-document-dedup.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)
        capa_round_1_id = session.scalars(
            select(CapaCycle)
            .where(CapaCycle.case_id == seeded["case_ids"]["a"])
            .where(CapaCycle.round_no == 1)
        ).one().id
        older_duplicate = Document(
            family_code="UNREGISTERED_DUPLICATE",
            document_type_code="UNREGISTERED_DUPLICATE",
            title="Tài liệu cũ",
            case_id=seeded["case_ids"]["a"],
        )
        newer_duplicate = Document(
            family_code="UNREGISTERED_DUPLICATE",
            document_type_code="UNREGISTERED_DUPLICATE",
            title="Tài liệu mới",
            case_id=seeded["case_ids"]["a"],
        )
        session.add_all([older_duplicate, newer_duplicate])
        session.flush()
        older_variant = DocumentVariant(
            document_id=older_duplicate.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        newer_variant = DocumentVariant(
            document_id=newer_duplicate.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
            is_active=True,
        )
        session.add_all([older_variant, newer_variant])
        session.flush()
        session.add_all(
            [
                DocumentVersion(
                    document_variant_id=older_variant.id,
                    version_no=1,
                    original_filename="duplicate-old.docx",
                    is_current=True,
                    issued_on=datetime(2026, 8, 1, tzinfo=timezone.utc),
                ),
                DocumentVersion(
                    document_variant_id=newer_variant.id,
                    version_no=1,
                    original_filename="duplicate-new.docx",
                    is_current=True,
                    issued_on=datetime(2026, 8, 12, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

    app = create_app(database_url)
    case_workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/workspace")

    with Session(engine) as session:
        payload = case_workspace_route.endpoint(
            case_id=seeded["case_ids"]["a"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    capa_items = [item for item in payload.documents.items if item.family_code == "INSPECTION_CAPA_LAN_1"]
    assert len(capa_items) == 1
    assert capa_items[0].parent_scope == "capa_cycle"
    assert capa_items[0].parent_id == capa_round_1_id

    duplicate_items = [item for item in payload.documents.items if item.family_code == "UNREGISTERED_DUPLICATE"]
    assert len(duplicate_items) == 1
    assert duplicate_items[0].parent_scope == "case"
    assert duplicate_items[0].parent_id == seeded["case_ids"]["a"]
    assert duplicate_items[0].original_filename == "duplicate-new.docx"


def test_document_checklist_response_keeps_storage_fields_hidden(tmp_path):
    database_path = tmp_path / "catalog-document-storage-hidden.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    app = create_app(database_url)
    case_workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/cases/{case_id}/workspace")
    change_workspace_route = next(
        route for route in app.routes if getattr(route, "path", "") == "/change-requests/{change_request_id}/workspace"
    )

    with Session(engine) as session:
        case_payload = case_workspace_route.endpoint(
            case_id=seeded["case_ids"]["a"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        change_payload = change_workspace_route.endpoint(
            change_request_id=seeded["change_request_ids"]["primary"],
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    forbidden_fields = {"storage_root", "storage_relative_path", "storage_binding_id", "checksum", "checksum_sha256"}
    for item in [*case_payload.documents.items, *change_payload.documents.items]:
        assert forbidden_fields.isdisjoint(item.model_dump().keys())


def test_case_workspace_does_not_fabricate_business_eligibility_for_unlinked_case(tmp_path):
    database_path = tmp_path / "catalog-case-workspace-unlinked.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seeded = seed_certificate_workspace_catalog(session)

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.get_case_workspace(session, case_id=seeded["case_ids"]["b"])

    assert payload["linked_gxp_certificates"][0]["certificate_number"] == "B-001"
    assert payload["linked_business_eligibility_certificates"] == []


def test_search_facilities_supports_field_specific_name_scope_and_gmpbb_filters(tmp_path):
    database_path = tmp_path / "catalog-field-filters.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty GMPbb", short_name="GMPbb")
        session.add(company)
        session.flush()

        site_gmpbb = Site(
            company_id=company.id,
            site_name="Nhà máy Bao bì vô trùng",
            province_name="Bình Dương",
            legacy_site_id=210,
            legacy_gmp_site_code="9.1",
        )
        site_other = Site(
            company_id=company.id,
            site_name="Nhà máy viên nén",
            province_name="Đồng Nai",
            legacy_site_id=211,
            legacy_gmp_site_code="9.2",
        )
        session.add_all([site_gmpbb, site_other])
        session.flush()

        case_gmpbb = Case(
            site_id=site_gmpbb.id,
            gxp_type="GMPbb",
            scope_code="A",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
            legacy_inspection_code="KT-GMPBB-A",
            applicable_standard="GMP Bao bì",
            opened_year=2026,
        )
        case_other = Case(
            site_id=site_other.id,
            gxp_type="GMP",
            scope_code="A",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
            legacy_inspection_code="KT-GMP-A",
            applicable_standard="WHO-GMP",
            opened_year=2026,
        )
        session.add_all([case_gmpbb, case_other])
        session.flush()

        cert_gmpbb = Certificate(site_id=site_gmpbb.id, case_id=case_gmpbb.id, certificate_type="GMPbb", latest_flag=True)
        cert_other = Certificate(site_id=site_other.id, case_id=case_other.id, certificate_type="GMP", latest_flag=True)
        session.add_all([cert_gmpbb, cert_other])
        session.flush()

        version_gmpbb = CertificateVersion(
            certificate_id=cert_gmpbb.id,
            version_no=1,
            issue_date=date(2026, 5, 1),
            expiry_date=date(2027, 5, 1),
            certificate_number="GCN-GMPBB-001",
            is_latest_version=True,
        )
        version_other = CertificateVersion(
            certificate_id=cert_other.id,
            version_no=1,
            issue_date=date(2026, 6, 1),
            expiry_date=date(2027, 6, 1),
            certificate_number="GCN-GMP-001",
            is_latest_version=True,
        )
        session.add_all([version_gmpbb, version_other])
        session.flush()
        session.add_all(
            [
                CertificateScope(
                    certificate_version_id=version_gmpbb.id,
                    scope_key="A",
                    scope_text="Bao bì vô trùng cấp A",
                    sort_order=1,
                ),
                CertificateScope(
                    certificate_version_id=version_other.id,
                    scope_key="A",
                    scope_text="Viên nén không vô trùng",
                    sort_order=1,
                ),
            ]
        )
        session.commit()

    app = create_app(database_url)
    search_route = next(route for route in app.routes if getattr(route, "path", "") == "/search/facilities")

    with Session(engine) as session:
        gmpbb_search = search_route.endpoint(
            q=None,
            facility_name=None,
            certificate_scope=None,
            gxp_type="GMPbb",
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        facility_name_search = search_route.endpoint(
            q=None,
            facility_name="Bao bì",
            certificate_scope=None,
            gxp_type=None,
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        certificate_scope_search = search_route.endpoint(
            q=None,
            facility_name=None,
            certificate_scope="vô trùng cấp A",
            gxp_type=None,
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert gmpbb_search.total_count == 1
    assert gmpbb_search.items[0].gxp_type == "GMPbb"
    assert gmpbb_search.items[0].context_code == "9.1A"

    assert facility_name_search.total_count == 1
    assert [row.facility_name for row in facility_name_search.items] == ["Nhà máy Bao bì vô trùng"]

    assert certificate_scope_search.total_count == 1
    assert [row.certificate_scope_summary for row in certificate_scope_search.items] == ["Bao bì vô trùng cấp A"]
    assert [row.facility_name for row in certificate_scope_search.items] == ["Nhà máy Bao bì vô trùng"]


def test_imported_legacy_certificate_scope_flows_through_catalog_search(tmp_path):
    database_path = tmp_path / "catalog-imported-scope.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    snapshot = {
        "db.cty": [
            {"ID": "1", "TÊN CÔNG TY": "Công ty Scope", "COMPANY NAME": "Scope Co", "TÊN VIẾT TẮT": "SCOPE"},
        ],
        "db.cso": [
            {
                "ID": "10",
                "ID Cty": "1",
                "TÊN CƠ SỞ": "Nhà máy Scope",
                "SITE NAME": "Scope Plant",
                "ĐỊA CHỈ CƠ SỞ": "Hà Nội",
                "SITE ADDRESS": "Ha Noi",
                "TỈNH/TP": "Hà Nội",
                "MÃ CS GMP": "1.1",
            },
        ],
        "db.ktra": [
            {
                "ID": "100",
                "LOẠI KT": "GMP",
                "ID CƠ SỞ": "10",
                "MÃ DC": "A",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
                "LOẠI KIỂM TRA": "Định kỳ",
                "Ngày nộp": "2026-01-01 00:00:00+00:00",
                "Mã hồ sơ": "HS-A",
                "Ngày thẩm định": "2026-01-03 00:00:00+00:00",
                "Người thẩm định": "Auditor A",
                "Kết quả": "Đạt",
                "Ngày K.tra": "2026-01-10 00:00:00+00:00",
                "Q. định": "QD-A",
                "B. bản": "BB-A",
            },
            {
                "ID": "101",
                "LOẠI KT": "GMP",
                "ID CƠ SỞ": "10",
                "MÃ DC": "B",
                "TIÊU CHUẨN ÁP DỤNG": "EU-GMP",
                "LOẠI KIỂM TRA": "Định kỳ",
                "Ngày nộp": "2026-02-01 00:00:00+00:00",
                "Mã hồ sơ": "HS-B",
                "Ngày thẩm định": "2026-02-03 00:00:00+00:00",
                "Người thẩm định": "Auditor B",
                "Kết quả": "Đạt",
                "Ngày K.tra": "2026-02-10 00:00:00+00:00",
                "Q. định": "QD-B",
                "B. bản": "BB-B",
            },
        ],
        "db.cc": [
            {
                "ID": "200",
                "MỚI NHẤT": "o",
                "ID MỚI NHẤT": "",
                "LOẠI CC": "GMP",
                "ID ĐỢT KTRA": "100",
                "ID CƠ SỞ": "10",
                "MÃ DC": "A",
                "Mã số CC": "GCN-A",
                "Ngày cấp CC": "2026-03-01 00:00:00+00:00",
                "Hết hạn CC": "2028-03-01 00:00:00+00:00",
                "PHẠM VI CHỨNG NHẬN": "Dây chuyền viên nén A",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
            },
            {
                "ID": "201",
                "MỚI NHẤT": "o",
                "ID MỚI NHẤT": "",
                "LOẠI CC": "GMP",
                "ID ĐỢT KTRA": "",
                "ID CƠ SỞ": "10",
                "MÃ DC": "B",
                "Mã số CC": "GCN-B",
                "Ngày cấp CC": "2026-04-01 00:00:00+00:00",
                "Hết hạn CC": "2028-04-01 00:00:00+00:00",
                "PHẠM VI CHỨNG NHẬN": "Dây chuyền thuốc bột B",
                "TIÊU CHUẨN ÁP DỤNG": "EU-GMP",
            },
        ],
        "db.dkkd": [],
        "db.Tdoi": [],
        "db.Tdoi2": [],
    }

    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()

    app = create_app(database_url)
    search_route = next(route for route in app.routes if getattr(route, "path", "") == "/search/facilities")

    with Session(engine) as session:
        search_payload = search_route.endpoint(
            q=None,
            gxp_type="GMP",
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=80,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert search_payload.total_count == 2
    assert [row.context_code for row in search_payload.items] == ["1.1A", "1.1B"]
    assert [row.current_certificate_number for row in search_payload.items] == ["GCN-A", "GCN-B"]
    assert [row.certificate_scope_summary for row in search_payload.items] == ["Dây chuyền viên nén A", "Dây chuyền thuốc bột B"]
    assert [row.line_code for row in search_payload.items] == ["A", "B"]


def test_catalog_prefers_certificate_line_code_over_linked_case_scope_when_legacy_row_disagrees(tmp_path):
    database_path = tmp_path / "catalog-certificate-line-owner.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    snapshot = {
        "db.cty": [
            {"ID": "1", "TÊN CÔNG TY": "Công ty Lệch Mã", "COMPANY NAME": "Mismatch Co", "TÊN VIẾT TẮT": "MIS"},
        ],
        "db.cso": [
            {
                "ID": "10",
                "ID Cty": "1",
                "TÊN CƠ SỞ": "Nhà máy Mismatch",
                "SITE NAME": "Mismatch Plant",
                "ĐỊA CHỈ CƠ SỞ": "Hà Nội",
                "SITE ADDRESS": "Ha Noi",
                "TỈNH/TP": "Hà Nội",
                "MÃ CS GMP": "1.1",
            },
        ],
        "db.ktra": [
            {
                "ID": "100",
                "LOẠI KT": "GMP",
                "ID CƠ SỞ": "10",
                "MÃ DC": "B",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
                "LOẠI KIỂM TRA": "Định kỳ",
            },
        ],
        "db.cc": [
            {
                "ID": "200",
                "MỚI NHẤT": "o",
                "ID MỚI NHẤT": "",
                "LOẠI CC": "GMP",
                "ID ĐỢT KTRA": "100",
                "ID CƠ SỞ": "10",
                "MÃ DC": "A",
                "Mã số CC": "GCN-MISMATCH",
                "Ngày cấp CC": "2026-03-01 00:00:00+00:00",
                "Hết hạn CC": "2028-03-01 00:00:00+00:00",
                "PHẠM VI CHỨNG NHẬN": "Dây chuyền A từ certificate owner",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
            },
        ],
        "db.dkkd": [],
        "db.Tdoi": [],
        "db.Tdoi2": [],
    }

    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        search_payload = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=80,
        )

    assert search_payload["total_count"] == 2
    assert [row["context_code"] for row in search_payload["items"]] == ["1.1A", "1.1B"]
    assert search_payload["items"][0]["line_code"] == "A"
    assert search_payload["items"][0]["current_certificate_number"] == "GCN-MISMATCH"
    assert search_payload["items"][0]["certificate_scope_summary"] == "Dây chuyền A từ certificate owner"
    assert search_payload["items"][1]["line_code"] == "B"
    assert search_payload["items"][1]["current_certificate_number"] is None


def test_imported_general_info_fields_flow_into_facility_workspace_summary(tmp_path):
    database_path = tmp_path / "workspace-general-info.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    snapshot = {
        "db.cty": [
            {
                "ID": "1",
                "TÊN CÔNG TY": "Công ty General Info",
                "COMPANY NAME": "General Info Co",
                "TÊN VIẾT TẮT": "GEN",
                "ĐỊA CHỈ TRỤ SỞ": "123 Trụ sở chính",
            },
        ],
        "db.cso": [
            {
                "ID": "10",
                "ID Cty": "1",
                "TÊN CƠ SỞ": "Nhà máy General Info",
                "SITE NAME": "General Info Plant",
                "ĐỊA CHỈ CƠ SỞ": "KCN A",
                "SITE ADDRESS": "Industrial Park A",
                "TỈNH/TP": "Hà Nội",
                "MÃ CS GMP": "1.1",
                "Chuyên viên phụ trách": "Hà Hoàng Phương",
                "DOANH NGHIỆP NƯỚC NGOÀI": "Nhật Bản",
                "LIÊN HỆ": "QA: 0903 000 000",
                "NGƯỜI ĐỨNG ĐẦU CƠ SỞ": "Rajesh Kamat, Tổng Giám đốc",
                "NGƯỜI CHỊU TRÁCH NHIỆM CHUYÊN MÔN": "Dược sĩ A",
                "NGƯỜI PHỤ TRÁCH QA": "QA Lead B",
                "NGỪNG HOẠT ĐỘNG": "Cơ sở dừng hoạt động từ 31/12/2020",
            },
        ],
        "db.ktra": [
            {
                "ID": "100",
                "LOẠI KT": "GMP",
                "ID CƠ SỞ": "10",
                "MÃ DC": "A",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
                "LOẠI KIỂM TRA": "Định kỳ",
            },
        ],
        "db.cc": [
            {
                "ID": "200",
                "MỚI NHẤT": "o",
                "ID MỚI NHẤT": "",
                "LOẠI CC": "GMP",
                "ID ĐỢT KTRA": "100",
                "ID CƠ SỞ": "10",
                "MÃ DC": "A",
                "Mã số CC": "GCN-GEN-001",
                "Ngày cấp CC": "2026-03-01 00:00:00+00:00",
                "Hết hạn CC": "2028-03-01 00:00:00+00:00",
                "PHẠM VI CHỨNG NHẬN": "Dây chuyền viên nén A",
                "TIÊU CHUẨN ÁP DỤNG": "WHO-GMP",
            },
        ],
        "db.dkkd": [],
        "db.Tdoi": [],
        "db.Tdoi2": [],
    }

    with Session(engine) as session:
        import_snapshot(session, snapshot)
        session.commit()
        site_id = session.scalars(select(Site.id)).one()

    service = CatalogReadService()
    with Session(engine) as session:
        workspace_payload = service.get_facility_workspace(
            session,
            site_id=site_id,
            gxp_type="GMP",
            line_code="A",
        )

    assert workspace_payload["summary"]["company_name"] == "Công ty General Info"
    assert workspace_payload["summary"]["company_legal_address"] == "123 Trụ sở chính"
    assert workspace_payload["summary"]["company_leader"] == "Rajesh Kamat, Tổng Giám đốc"
    assert workspace_payload["summary"]["company_foreign_investment"] == "Nhật Bản"
    assert workspace_payload["summary"]["assigned_specialist"] == "Hà Hoàng Phương"
    assert workspace_payload["summary"]["contact_information"] == "QA: 0903 000 000"
    assert workspace_payload["summary"]["professional_responsible_person"] == "Dược sĩ A"
    assert workspace_payload["summary"]["quality_assurance_person"] == "QA Lead B"
    assert workspace_payload["summary"]["facility_current_status"] == "Cơ sở dừng hoạt động từ 31/12/2020"
    assert workspace_payload["summary"]["current_certificate_number"] == "GCN-GEN-001"


def test_search_context_query_preserves_postgresql_paging_semantics():
    service = CatalogReadService()
    filtered_sites_stmt = service._build_filtered_search_sites_stmt(
        q=None,
        gxp_type="GMP",
        province=None,
        case_states=None,
        change_request_states=None,
        certificate_state=None,
        certificate_expiring_within_days=None,
    )
    stmt = service._ordered_search_contexts_stmt(
        service._build_search_contexts_stmt(
            filtered_sites_stmt,
            gxp_type="GMP",
            case_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
        )
    ).offset(10).limit(20)
    compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    normalized = " ".join(compiled.split())

    assert "UNION ALL" in normalized
    assert "SELECT DISTINCT" in normalized
    assert "site_id" in normalized
    assert "legacy_site_id" in normalized
    assert "site_name" in normalized
    assert "gxp_type" in normalized
    assert "line_code" in normalized
    assert "search_contexts_non_null_peer.line_code IS NOT NULL" in normalized
    assert "search_contexts_filtered.line_code IS NULL" not in normalized
    assert "ORDER BY search_contexts.legacy_site_id IS NULL, search_contexts.legacy_site_id ASC, search_contexts.site_name ASC, search_contexts.gxp_type IS NULL, search_contexts.gxp_type ASC, search_contexts.line_code IS NULL, search_contexts.line_code ASC, search_contexts.site_id ASC" in normalized
    assert "LIMIT 20" in normalized
    assert "OFFSET 10" in normalized


def test_dashboard_metric_drilldowns_match_search_predicates(tmp_path):
    database_path = tmp_path / "dashboard-drilldown.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty Drilldown", short_name="CDD")
        session.add(company)
        session.flush()

        active_site = Site(company_id=company.id, site_name="Site active", legacy_site_id=1)
        waiting_site = Site(company_id=company.id, site_name="Site waiting", legacy_site_id=2)
        decision_site = Site(company_id=company.id, site_name="Site decision", legacy_site_id=3)
        active_cert_site = Site(company_id=company.id, site_name="Site cert", legacy_site_id=4)
        expiring_cert_site = Site(company_id=company.id, site_name="Site expiring", legacy_site_id=5)
        change_site = Site(company_id=company.id, site_name="Site change", legacy_site_id=6)
        session.add_all([active_site, waiting_site, decision_site, active_cert_site, expiring_cert_site, change_site])
        session.flush()

        session.add_all(
            [
                Case(site_id=active_site.id, gxp_type="GMP", state=CaseState.UNDER_ASSESSMENT, opened_year=2026),
                Case(site_id=waiting_site.id, gxp_type="GMP", state=CaseState.PLANNED, opened_year=2026),
                Case(
                    site_id=decision_site.id,
                    gxp_type="GLP",
                    state=CaseState.AWAITING_CERTIFICATE_DECISION,
                    opened_year=2026,
                ),
            ]
        )
        session.flush()

        active_cert = Certificate(site_id=active_cert_site.id, certificate_type="GMP", latest_flag=True)
        expiring_cert = Certificate(site_id=expiring_cert_site.id, certificate_type="GLP", latest_flag=True)
        session.add_all([active_cert, expiring_cert])
        session.flush()
        session.add_all(
            [
                CertificateVersion(
                    certificate_id=active_cert.id,
                    version_no=1,
                    issue_date=date(2026, 1, 1),
                    expiry_date=date(2027, 1, 1),
                    certificate_number="CERT-ACTIVE",
                    is_latest_version=True,
                ),
                CertificateVersion(
                    certificate_id=expiring_cert.id,
                    version_no=1,
                    issue_date=date(2026, 6, 1),
                    expiry_date=date.today() + timedelta(days=30),
                    certificate_number="CERT-EXPIRING",
                    is_latest_version=True,
                ),
            ]
        )
        session.add(
            ChangeRequest(
                site_id=change_site.id,
                legacy_change_request_id=7001,
                scope_label="Đổi người phụ trách",
                submitted_on=date.today(),
                state=ChangeRequestState.UNDER_REVIEW,
            )
        )
        session.commit()

    app = create_app(database_url)
    dashboard_route = next(route for route in app.routes if getattr(route, "path", "") == "/dashboard/summary")
    search_route = next(route for route in app.routes if getattr(route, "path", "") == "/search/facilities")

    with Session(engine) as session:
        dashboard_payload = dashboard_route.endpoint(
            queue_limit=8,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        active_cases = search_route.endpoint(
            q=None,
            gxp_type=None,
            province=None,
            case_state=ACTIVE_CASE_STATES,
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        waiting_inspection = search_route.endpoint(
            q=None,
            gxp_type=None,
            province=None,
            case_state=WAITING_INSPECTION_CASE_STATES,
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        waiting_certificate_decision = search_route.endpoint(
            q=None,
            gxp_type=None,
            province=None,
            case_state=["awaiting_certificate_decision"],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        active_certificates = search_route.endpoint(
            q=None,
            gxp_type=None,
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state="active",
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        expiring_certificates = search_route.endpoint(
            q=None,
            gxp_type=None,
            province=None,
            case_state=[],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=90,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        incomplete_changes = search_route.endpoint(
            q=None,
            gxp_type=None,
            province=None,
            case_state=[],
            change_request_state=["received", "under_review"],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert dashboard_payload.active_cases == active_cases.total_count
    assert dashboard_payload.waiting_inspection == waiting_inspection.total_count
    assert dashboard_payload.waiting_certificate_decision == waiting_certificate_decision.total_count
    assert dashboard_payload.active_certificates == active_certificates.total_count
    assert dashboard_payload.expiring_certificates_90_days == expiring_certificates.total_count
    assert dashboard_payload.incomplete_changes == incomplete_changes.total_count


def test_search_facilities_keeps_distinct_facility_rows_when_joins_match_multiple_records(tmp_path):
    database_path = tmp_path / "search-distinct-facilities.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty Join", short_name="JOIN")
        session.add(company)
        session.flush()
        site = Site(
            company_id=company.id,
            site_name="Cơ sở Join",
            province_name="Hà Nội",
            legacy_site_id=701,
            legacy_gmp_site_code="GMP-701",
        )
        session.add(site)
        session.flush()
        session.add_all(
            [
                Case(
                    site_id=site.id,
                    gxp_type="GMP",
                    state=CaseState.UNDER_ASSESSMENT,
                    legacy_inspection_code="KT-JOIN-1",
                    applicable_standard="WHO-GMP",
                    opened_year=2026,
                ),
                Case(
                    site_id=site.id,
                    gxp_type="GMP",
                    state=CaseState.INSPECTION_COMPLETED,
                    legacy_inspection_code="KT-JOIN-2",
                    applicable_standard="PIC/S-GMP",
                    opened_year=2026,
                ),
            ]
        )
        cert_1 = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
        cert_2 = Certificate(site_id=site.id, certificate_type="GMP", latest_flag=True)
        session.add_all([cert_1, cert_2])
        session.flush()
        session.add_all(
            [
                CertificateVersion(
                    certificate_id=cert_1.id,
                    version_no=1,
                    issue_date=date(2026, 1, 1),
                    expiry_date=date(2027, 1, 1),
                    certificate_number="JOIN-CERT-1",
                    is_latest_version=True,
                ),
                CertificateVersion(
                    certificate_id=cert_2.id,
                    version_no=1,
                    issue_date=date(2026, 2, 1),
                    expiry_date=date(2027, 2, 1),
                    certificate_number="JOIN-CERT-2",
                    is_latest_version=True,
                ),
            ]
        )
        session.commit()
        site_id = site.id

    service = CatalogReadService()
    with Session(engine) as session:
        rows = service.search_facilities(
            session,
            q="JOIN",
            gxp_type="GMP",
            province="Hà Nội",
            case_states=[],
            change_request_states=[],
            certificate_state="active",
            certificate_expiring_within_days=None,
            offset=0,
            limit=80,
        )

    assert rows["total_count"] == 1
    assert len(rows["items"]) == 1
    assert rows["items"][0]["site_id"] == site_id


def test_search_facilities_pages_context_grain_without_materializing_full_site_rows(tmp_path):
    database_path = tmp_path / "search-paging.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty Paging", short_name="PAGE")
        session.add(company)
        session.flush()

        site_one = Site(company_id=company.id, site_name="Nhà máy 10", legacy_site_id=10, legacy_gmp_site_code="10.1")
        site_two = Site(company_id=company.id, site_name="Nhà máy 20", legacy_site_id=20, legacy_gmp_site_code="20.1")
        site_three = Site(company_id=company.id, site_name="Nhà máy 30", legacy_site_id=30, legacy_gmp_site_code="30.1")
        site_four = Site(company_id=company.id, site_name="Nhà máy 40", legacy_site_id=40, legacy_gmp_site_code="40.1")
        session.add_all([site_one, site_two, site_three, site_four])
        session.flush()

        session.add_all(
            [
                Case(site_id=site_one.id, gxp_type="GMP", scope_code="A", state=CaseState.PLANNED, opened_year=2026),
                Case(site_id=site_one.id, gxp_type="GMP", scope_code="B", state=CaseState.PLANNED, opened_year=2026),
                Case(site_id=site_one.id, gxp_type="GMP", scope_code="C", state=CaseState.PLANNED, opened_year=2026),
                Case(site_id=site_two.id, gxp_type="GMP", scope_code="A", state=CaseState.PLANNED, opened_year=2026),
                Case(site_id=site_three.id, gxp_type="GMP", scope_code=None, state=CaseState.PLANNED, opened_year=2026),
            ]
        )
        certificate_only = Certificate(site_id=site_four.id, case_id=None, certificate_type="GMP", line_code="Z", latest_flag=True)
        session.add(certificate_only)
        session.flush()
        session.add(
            CertificateVersion(
                certificate_id=certificate_only.id,
                version_no=1,
                issue_date=date(2026, 4, 1),
                expiry_date=date(2028, 4, 1),
                certificate_number="GCN-Z",
                is_latest_version=True,
            )
        )
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        first_page = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=3,
        )
        second_page = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=3,
            limit=3,
        )

    expected_contexts = ["10.1A", "10.1B", "10.1C", "20.1A", "30.1", "40.1Z"]

    assert first_page["total_count"] == 6
    assert first_page["offset"] == 0
    assert first_page["limit"] == 3
    assert [row["context_code"] for row in first_page["items"]] == expected_contexts[:3]

    assert second_page["total_count"] == 6
    assert second_page["offset"] == 3
    assert second_page["limit"] == 3
    assert [row["context_code"] for row in second_page["items"]] == expected_contexts[3:]
    assert {row["result_key"] for row in first_page["items"]}.isdisjoint({row["result_key"] for row in second_page["items"]})
    assert [row["context_code"] for row in first_page["items"] + second_page["items"]] == expected_contexts
    assert second_page["items"][1]["result_grain"] == "facility"
    assert second_page["items"][2]["line_code"] == "Z"
    assert second_page["items"][2]["current_certificate_number"] == "GCN-Z"


def test_search_facilities_api_rejects_negative_offset_with_422(tmp_path):
    database_path = tmp_path / "search-negative-offset.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    app = create_app(database_url)
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/search/facilities",
        "raw_path": b"/search/facilities",
        "query_string": b"offset=-1",
        "headers": [
            (b"host", b"testserver"),
            (b"x-auth-user", b"reader01"),
            (b"x-auth-role", b"reader"),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "root_path": "",
        "app": app,
    }

    anyio.run(app, scope, receive, send)

    response_start = next(message for message in messages if message["type"] == "http.response.start")
    assert response_start["status"] == 422


def test_search_facilities_uses_inspection_outcome_or_executed_event_for_latest_inspection_signal(tmp_path):
    database_path = tmp_path / "search-latest-inspection.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty Inspection", short_name="INSP")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Nhà máy Inspection", legacy_site_id=77, legacy_gmp_site_code="77.1")
        session.add(site)
        session.flush()

        case_with_outcome = Case(
            site_id=site.id,
            gxp_type="GMP",
            scope_code="A",
            state=CaseState.INSPECTION_COMPLETED,
            legacy_inspection_code="KT-OUTCOME",
            opened_year=2026,
        )
        case_with_event_only = Case(
            site_id=site.id,
            gxp_type="GMP",
            scope_code="B",
            state=CaseState.INSPECTION_COMPLETED,
            legacy_inspection_code="KT-EVENT",
            opened_year=2026,
        )
        session.add_all([case_with_outcome, case_with_event_only])
        session.flush()

        session.add(
            InspectionOutcome(
                case_id=case_with_outcome.id,
                inspected_on=date(2026, 7, 10),
                inspected_to_on=date(2026, 7, 12),
            )
        )
        session.add(
            InspectionEvent(
                case_id=case_with_event_only.id,
                event_type=InspectionEventType.INSPECTION_EXECUTED,
                occurred_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
            )
        )
        session.commit()

    service = CatalogReadService()
    with Session(engine) as session:
        payload = service.search_facilities(
            session,
            q=None,
            gxp_type="GMP",
            province=None,
            case_states=None,
            change_request_states=None,
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=10,
        )

    assert [row["context_code"] for row in payload["items"]] == ["77.1A", "77.1B"]
    assert payload["items"][0]["last_inspection_on"] == date(2026, 7, 12)
    assert payload["items"][1]["last_inspection_on"] == date(2026, 8, 5)


def test_dashboard_metrics_count_matching_facilities_not_raw_records(tmp_path):
    database_path = tmp_path / "dashboard-facility-counts.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty Semantic", short_name="SEM")
        session.add(company)
        session.flush()

        multi_match_site = Site(company_id=company.id, site_name="Cơ sở nhiều bản ghi", legacy_site_id=11)
        other_site = Site(company_id=company.id, site_name="Cơ sở đối chứng", legacy_site_id=12)
        session.add_all([multi_match_site, other_site])
        session.flush()

        session.add_all(
            [
                Case(site_id=multi_match_site.id, gxp_type="GMP", state=CaseState.UNDER_ASSESSMENT, opened_year=2026),
                Case(site_id=multi_match_site.id, gxp_type="GLP", state=CaseState.INSPECTION_IN_PROGRESS, opened_year=2026),
                Case(site_id=multi_match_site.id, gxp_type="GMP", state=CaseState.AWAITING_CERTIFICATE_DECISION, opened_year=2026),
                Case(site_id=other_site.id, gxp_type="GMP", state=CaseState.CERTIFIED, opened_year=2026),
            ]
        )
        session.flush()

        active_cert_1 = Certificate(site_id=multi_match_site.id, certificate_type="GMP", latest_flag=True)
        active_cert_2 = Certificate(site_id=multi_match_site.id, certificate_type="GLP", latest_flag=True)
        expiring_cert = Certificate(site_id=multi_match_site.id, certificate_type="GMP", latest_flag=True)
        session.add_all([active_cert_1, active_cert_2, expiring_cert])
        session.flush()
        session.add_all(
            [
                CertificateVersion(
                    certificate_id=active_cert_1.id,
                    version_no=1,
                    issue_date=date(2026, 1, 1),
                    expiry_date=date(2027, 1, 1),
                    certificate_number="SEM-ACTIVE-1",
                    is_latest_version=True,
                ),
                CertificateVersion(
                    certificate_id=active_cert_2.id,
                    version_no=1,
                    issue_date=date(2026, 2, 1),
                    expiry_date=date(2027, 2, 1),
                    certificate_number="SEM-ACTIVE-2",
                    is_latest_version=True,
                ),
                CertificateVersion(
                    certificate_id=expiring_cert.id,
                    version_no=1,
                    issue_date=date(2026, 3, 1),
                    expiry_date=date(2026, 9, 20),
                    certificate_number="SEM-EXP-1",
                    is_latest_version=True,
                ),
            ]
        )
        session.add_all(
            [
                ChangeRequest(
                    site_id=multi_match_site.id,
                    legacy_change_request_id=8101,
                    scope_label="Thay đổi A",
                    submitted_on=date(2026, 8, 1),
                    state=ChangeRequestState.RECEIVED,
                ),
                ChangeRequest(
                    site_id=multi_match_site.id,
                    legacy_change_request_id=8102,
                    scope_label="Thay đổi B",
                    submitted_on=date(2026, 8, 2),
                    state=ChangeRequestState.UNDER_REVIEW,
                ),
            ]
        )
        session.commit()

    app = create_app(database_url)
    dashboard_route = next(route for route in app.routes if getattr(route, "path", "") == "/dashboard/summary")

    with Session(engine) as session:
        dashboard_payload = dashboard_route.endpoint(
            queue_limit=8,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert dashboard_payload.active_cases == 1
    assert dashboard_payload.waiting_inspection == 1
    assert dashboard_payload.waiting_certificate_decision == 1
    assert dashboard_payload.active_certificates == 1
    assert dashboard_payload.expiring_certificates_90_days == 1
    assert dashboard_payload.incomplete_changes == 1


def test_dashboard_summary_and_workspace_routes_return_business_read_models(tmp_path):
    database_path = tmp_path / "dashboard-workspace.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Công ty A", short_name="CTA")
        session.add(company)
        session.flush()
        site = Site(
            company_id=company.id,
            site_name="Nhà máy A",
            province_name="Hà Nội",
            legacy_site_id=101,
            legacy_gmp_site_code="GMP-101",
            site_address="KCN A",
        )
        session.add(site)
        session.flush()
        case = Case(
            site_id=site.id,
            gxp_type="GMP",
            state=CaseState.AWAITING_CERTIFICATE_DECISION,
            legacy_inspection_id=301,
            legacy_inspection_code="KT-2026-GMP",
            applicable_standard="WHO-GMP",
            inspection_type="Định kỳ",
            opened_year=2026,
        )
        session.add(case)
        session.commit()
        site_id = site.id

    app = create_app(database_url)
    dashboard_route = next(route for route in app.routes if getattr(route, "path", "") == "/dashboard/summary")
    search_route = next(route for route in app.routes if getattr(route, "path", "") == "/search/facilities")
    workspace_route = next(route for route in app.routes if getattr(route, "path", "") == "/sites/{site_id}/workspace")

    with Session(engine) as session:
        dashboard_payload = dashboard_route.endpoint(
            queue_limit=8,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        search_payload = search_route.endpoint(
            q="Nhà máy",
            gxp_type="GMP",
            province="Hà Nội",
            case_state=["awaiting_certificate_decision"],
            change_request_state=[],
            certificate_state=None,
            certificate_expiring_within_days=None,
            offset=0,
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        workspace_payload = workspace_route.endpoint(
            site_id=site_id,
            gxp_type="GMP",
            line_code=None,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert dashboard_payload.total_facilities == 1
    assert dashboard_payload.waiting_certificate_decision == 1
    assert len(dashboard_payload.queue) == 1
    assert dashboard_payload.queue[0].facility_name == "Nhà máy A"

    assert search_payload.total_count == 1
    assert len(search_payload.items) == 1
    assert search_payload.items[0].facility_name == "Nhà máy A"
    assert search_payload.items[0].facility_code == "GMP-101"
    assert search_payload.items[0].current_state == "awaiting_certificate_decision"

    assert workspace_payload.summary.facility_name == "Nhà máy A"
    assert workspace_payload.summary.company_name == "Công ty A"
    assert len(workspace_payload.history) == 1
    assert workspace_payload.history[0].reference_code == "KT-2026-GMP"
