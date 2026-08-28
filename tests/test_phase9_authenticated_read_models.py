import ast
import anyio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
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
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.db.models.phase1 import (
    AppUser,
    AppUserRole,
    Case,
    Certificate,
    CertificateScope,
    CertificateVersion,
    ChangeRequest,
    Company,
    InspectionEvent,
    InspectionEventType,
    InspectionOutcome,
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


def seed_line_grain_catalog(session: Session):
    company = Company(legal_name="Công ty dây chuyền", short_name="LINE")
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
        is_latest_version=True,
    )
    version_b = CertificateVersion(
        certificate_id=certificate_b.id,
        version_no=1,
        issue_date=date(2026, 7, 15),
        expiry_date=date(2027, 7, 15),
        certificate_number="GCN-B",
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
    assert workspace_payload.summary.certificate_scope_summary == "Dây chuyền viên nén A"
    assert workspace_payload.summary.primary_standard == "WHO-GMP"
    assert [item.reference_code for item in workspace_payload.history if item.source_type == "case"] == ["KT-GMP-A"]
    assert any(item.source_type == "change_request" for item in workspace_payload.history)


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
