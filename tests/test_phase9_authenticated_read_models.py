import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import (
    authenticate_google_iap_request,
    build_authenticated_user,
    parse_role_map,
    require_role,
    resolve_mapped_role,
)
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.db.models.phase1 import (
    AppUser,
    AppUserRole,
    Case,
    Certificate,
    CertificateVersion,
    ChangeRequest,
    Company,
    InspectionEvent,
    InspectionEventType,
    RbacPermission,
    RbacRole,
    RbacRolePermission,
    Site,
)
from backend.app.main import create_app
from backend.app.read_models import CaseDetailRead, CaseRead, CompanyDetailRead, CompanyRead, SiteDetailRead, SiteRead

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
    assert "/dashboard/summary" in routes
    assert "/search/facilities" in routes
    assert "/sites/{site_id}/workspace" in routes


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
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        gmp_workspace = workspace_route.endpoint(
            site_id=seeded["site_id"],
            gxp_type="GMP",
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        glp_workspace = workspace_route.endpoint(
            site_id=seeded["site_id"],
            gxp_type="GLP",
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert len(gmp_search) == 1
    assert gmp_search[0].primary_standard == "WHO-GMP"
    assert gmp_search[0].last_inspection_code == "KT-GMP-2025"
    assert gmp_search[0].current_state == "inspection_completed"
    assert gmp_search[0].current_certificate_number == "GCN-GMP-001"

    assert len(glp_search) == 1
    assert glp_search[0].primary_standard == "GLP-WHO"
    assert glp_search[0].last_inspection_code == "KT-GLP-2026"
    assert glp_search[0].current_state == "awaiting_certificate_decision"
    assert glp_search[0].current_certificate_number == "GCN-GLP-009"

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
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert dashboard_payload.active_cases == len(active_cases)
    assert dashboard_payload.waiting_inspection == len(waiting_inspection)
    assert dashboard_payload.waiting_certificate_decision == len(waiting_certificate_decision)
    assert dashboard_payload.active_certificates == len(active_certificates)
    assert dashboard_payload.expiring_certificates_90_days == len(expiring_certificates)
    assert dashboard_payload.incomplete_changes == len(incomplete_changes)


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
            limit=50,
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )
        workspace_payload = workspace_route.endpoint(
            site_id=site_id,
            gxp_type="GMP",
            session=session,
            user=build_authenticated_user("reader01", "reader"),
        )

    assert dashboard_payload.total_facilities == 1
    assert dashboard_payload.waiting_certificate_decision == 1
    assert len(dashboard_payload.queue) == 1
    assert dashboard_payload.queue[0].facility_name == "Nhà máy A"

    assert len(search_payload) == 1
    assert search_payload[0].facility_name == "Nhà máy A"
    assert search_payload[0].facility_code == "GMP-101"
    assert search_payload[0].current_state == "awaiting_certificate_decision"

    assert workspace_payload.summary.facility_name == "Nhà máy A"
    assert workspace_payload.summary.company_name == "Công ty A"
    assert len(workspace_payload.history) == 1
    assert workspace_payload.history[0].reference_code == "KT-2026-GMP"
