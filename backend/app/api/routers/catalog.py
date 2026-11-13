from __future__ import annotations

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from backend.app.db.models.phase1 import ProductionLine

from backend.app.auth import ALLOWED_READ_ROLES, AuthenticatedUser, get_authenticated_user, require_role, require_permissions
from backend.app.api.session import get_session_from_request_factory, commit_or_409
from backend.app.read_models import (
    BusinessEligibilityDetailRead,
    BusinessEligibilityVersionHistoryRead,
    BusinessEligibilityGxpSourceEvidenceRead,
    BusinessEligibilityListRead,
    CaseDetailRead,
    CaseWorkspaceRead,
    CaseRead,
    CaseReportPageRead,
    CertificateReportPageRead,
    ChangeRequestReportPageRead,
    ChangeRequestWorkspaceRead,
    CompanyDetailRead,
    CompanyMasterCreateRequest,
    CompanyMasterCreateRead,
    CompanyRead,
    DashboardSummaryRead,
    FacilitySearchPageRead,
    FacilitySearchResultRead,
    FacilityWorkspaceRead,
    GxpCertificateDetailRead,
    GxpCertificateVersionHistoryRead,
    GxpCertificateListRead,
    SiteDetailRead,
    SiteMasterCreateRequest,
    SiteMasterCreateRead,
    ProductionLineMasterCreateRequest,
    ProductionLineMasterRead,
    ProductionLineMasterCreateRead,
    SiteRead,
)
from backend.app.services import CatalogReadService, CaseWorkflowService


def _optional_string_query(value: str | None) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _build_facility_action_readiness(
    *,
    workflow_service: CaseWorkflowService,
    session: Session,
    site_id: str,
    selected_gxp_type: str | None,
    selected_line_code: str | None,
    selected_production_line_id: str | None,
    user: AuthenticatedUser,
) -> list[dict[str, object]]:
    can_create_masters = "case.edit" in user.permissions
    master_status = "available" if can_create_masters else "forbidden"
    master_permission = ["case.edit"]
    return [
        {
            "action_key": "create_company",
            "label": "Công ty mới",
            "readiness_status": master_status,
            "detail": (
                "Có thể tạo công ty bằng UUID mới; đọc GET /companies/{company_id} để xác minh khi mất phản hồi."
                if can_create_masters else "Không có quyền tạo công ty."
            ),
            "required_permissions": master_permission,
        },
        {
            "action_key": "create_site",
            "label": "Cơ sở mới",
            "readiness_status": master_status,
            "detail": (
                "Chọn Company UUID và tạo Site UUID mới; đọc GET /sites/{site_id} nếu mất phản hồi."
                if can_create_masters else "Không có quyền tạo cơ sở."
            ),
            "required_permissions": master_permission,
        },
        {
            "action_key": "create_production_line",
            "label": "Dây chuyền mới",
            "readiness_status": master_status,
            "detail": (
                "Tạo định danh vật lý UUID mới khi có bằng chứng nhận diện và ngày hiệu lực; không tự nối GxP hay dữ liệu legacy."
                if can_create_masters else "Không có quyền tạo dây chuyền sản xuất."
            ),
            "required_permissions": master_permission,
        },
        workflow_service.get_create_initial_case_action_readiness(
            session,
            site_id=site_id,
            gxp_type=selected_gxp_type,
            line_code=selected_line_code,
            production_line_id=selected_production_line_id,
            user=user,
        ),
        workflow_service.get_create_reassessment_case_action_readiness(
            session,
            site_id=site_id,
            gxp_type=selected_gxp_type,
            line_code=selected_line_code,
            production_line_id=selected_production_line_id,
            user=user,
        ),
        workflow_service.get_create_change_request_action_readiness(
            session,
            site_id=site_id,
            user=user,
        ),
    ]


def register_catalog_routes(app, session_factory) -> None:
    dependency = Depends(get_session_from_request_factory(session_factory))
    service = CatalogReadService()
    workflow_service = CaseWorkflowService()

    def create_company_master(
        payload: CompanyMasterCreateRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"case.edit"})
        result = workflow_service.create_company_master(
            session,
            company_id=str(payload.company_id),
            legal_name=payload.legal_name,
            legal_address=payload.legal_address,
            english_name=payload.english_name,
            short_name=payload.short_name,
            legal_address_en=payload.legal_address_en,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CompanyMasterCreateRead(**result)

    def create_site_master(
        company_id: str,
        payload: SiteMasterCreateRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"case.edit"})
        result = workflow_service.create_site_master(
            session,
            company_id=company_id,
            site_id=str(payload.site_id),
            site_name=payload.site_name,
            site_address=payload.site_address,
            site_name_en=payload.site_name_en,
            site_address_en=payload.site_address_en,
            province_name=payload.province_name,
            short_name=payload.short_name,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return SiteMasterCreateRead(**result)


    def create_production_line_master(
        site_id: str,
        payload: ProductionLineMasterCreateRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"case.edit"})
        result = workflow_service.create_production_line_master(
            session, site_id=site_id,
            production_line_id=str(payload.production_line_id),
            code=payload.code, effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            physical_identity_evidence_reference=payload.physical_identity_evidence_reference,
            reason=payload.reason, user=user,
        )
        commit_or_409(session)
        return ProductionLineMasterCreateRead(**result)

    def get_production_line_master(
        production_line_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        line = session.get(ProductionLine, production_line_id)
        if line is None:
            raise HTTPException(status_code=404, detail="ProductionLine not found.")
        return ProductionLineMasterRead(
            id=line.id, site_id=line.site_id, code=line.code,
            effective_from=line.effective_from, effective_to=line.effective_to,
            row_version=line.row_version,
        )

    def list_site_production_lines(
        site_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        # Site existence is verified even if the child collection is empty.
        service.get_site(session, site_id)
        from sqlalchemy import select
        rows = session.scalars(
            select(ProductionLine).where(ProductionLine.site_id == site_id)
            .order_by(ProductionLine.code, ProductionLine.id)
        ).all()
        return [
            ProductionLineMasterRead(
                id=row.id, site_id=row.site_id, code=row.code,
                effective_from=row.effective_from, effective_to=row.effective_to,
                row_version=row.row_version,
            )
            for row in rows
        ]

    def list_companies(
        q: str | None = Query(default=None),
        limit: int = Query(default=20, le=200),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        rows = service.list_companies(session, q=q, limit=limit)
        return [
            CompanyRead(
                id=row.id,
                legacy_company_id=row.legacy_company_id,
                legal_name=row.legal_name,
                short_name=row.short_name,
            )
            for row in rows
        ]

    def list_sites(
        q: str | None = Query(default=None),
        limit: int = Query(default=20, le=200),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        rows = service.list_sites(session, q=q, limit=limit)
        return [
            SiteRead(
                id=row.id,
                legacy_site_id=row.legacy_site_id,
                company_id=row.company_id,
                site_name=row.site_name,
                province_name=row.province_name,
            )
            for row in rows
        ]

    def list_cases(
        q: str | None = Query(default=None),
        gxp_type: str | None = Query(default=None),
        limit: int = Query(default=20, le=200),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        rows = service.list_cases(session, q=q, gxp_type=gxp_type, limit=limit)
        return [
            CaseRead(
                id=row.id,
                legacy_inspection_id=row.legacy_inspection_id,
                legacy_inspection_code=row.legacy_inspection_code,
                site_id=row.site_id,
                gxp_type=row.gxp_type,
                state=row.state.value,
            )
            for row in rows
        ]

    def get_company_detail(
        company_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        row = service.get_company(session, company_id)
        return CompanyDetailRead(
            id=row.id,
            legacy_company_id=row.legacy_company_id,
            legal_name=row.legal_name,
            english_name=row.english_name,
            short_name=row.short_name,
            legal_address=row.legal_address,
            legal_address_en=row.legal_address_en,
            is_inactive=row.is_inactive,
        )

    def get_site_detail(
        site_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        row = service.get_site(session, site_id)
        return SiteDetailRead(
            id=row.id,
            legacy_site_id=row.legacy_site_id,
            company_id=row.company_id,
            site_name=row.site_name,
            site_name_en=row.site_name_en,
            site_address=row.site_address,
            site_address_en=row.site_address_en,
            province_name=row.province_name,
            short_name=row.short_name,
        )

    def get_case_detail(
        case_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        row = service.get_case(session, case_id)
        line = None if row.production_line_id is None else session.get(ProductionLine, row.production_line_id)
        if row.production_line_id is not None and (line is None or line.site_id != row.site_id):
            raise HTTPException(status_code=409, detail="Case references an invalid canonical ProductionLine.")
        raw_scope_code = str(row.scope_code or "").strip() or None
        return CaseDetailRead(
            id=row.id,
            legacy_inspection_id=row.legacy_inspection_id,
            legacy_inspection_code=row.legacy_inspection_code,
            site_id=row.site_id,
            gxp_type=row.gxp_type,
            scope_code=row.scope_code,
            production_line_id=row.production_line_id,
            production_line_code=line.code if line is not None else raw_scope_code,
            production_line_identity_state="canonical" if line is not None else "legacy_unlinked" if raw_scope_code else "facility_wide",
            applicable_standard=row.applicable_standard,
            inspection_type=row.inspection_type,
            state=row.state.value,
            opened_year=row.opened_year,
            row_version=row.row_version,
        )

    def get_case_workspace(
        case_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return CaseWorkspaceRead(**service.get_case_workspace(session, case_id=case_id, user=user))

    def get_change_request_workspace(
        change_request_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return ChangeRequestWorkspaceRead(
            **service.get_change_request_workspace(session, change_request_id=change_request_id, user=user)
        )

    def get_dashboard_summary(
        queue_limit: int = Query(default=8, ge=1, le=20),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return DashboardSummaryRead(**service.get_dashboard_summary(session, queue_limit=queue_limit))

    def case_report(
        gxp_type: str | None = Query(default=None),
        state: str | None = Query(default=None),
        q: str | None = Query(default=None),
        opened_year: int | None = Query(default=None, ge=1900, le=9999),
        certificate_decision_status: str | None = Query(default=None),
        inspection_queue: bool = Query(default=False),
        export: bool = Query(default=False),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=200),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return CaseReportPageRead(**service.get_case_report(
            session, gxp_type=_optional_string_query(gxp_type), state=_optional_string_query(state),
            q=_optional_string_query(q), opened_year=opened_year, inspection_queue=inspection_queue,
            export=export, offset=offset, limit=limit,
            certificate_decision_status=_optional_string_query(certificate_decision_status),
        ))

    def certificate_report(
        gxp_type: str | None = Query(default=None),
        q: str | None = Query(default=None),
        number: str | None = Query(default=None),
        expiry_days: int | None = Query(default=None),
        export: bool = Query(default=False),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=200),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return CertificateReportPageRead(**service.get_certificate_report(
            session, gxp_type=_optional_string_query(gxp_type), q=_optional_string_query(q),
            expiry_days=expiry_days, export=export, offset=offset, limit=limit, number=_optional_string_query(number),
        ))

    def change_request_report(
        state: str | None = Query(default=None),
        q: str | None = Query(default=None),
        export: bool = Query(default=False),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=200),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return ChangeRequestReportPageRead(**service.get_change_request_report(
            session, state=_optional_string_query(state), q=_optional_string_query(q),
            export=export, offset=offset, limit=limit,
        ))

    def search_facilities(
        q: str | None = Query(default=None),
        facility_name: str | None = Query(default=None),
        site_id: str | None = Query(default=None),
        certificate_scope: str | None = Query(default=None),
        gxp_type: str | None = Query(default=None),
        province: str | None = Query(default=None),
        case_state: list[str] = Query(default=[]),
        change_request_state: list[str] = Query(default=[]),
        certificate_state: str | None = Query(default=None),
        certificate_expiring_within_days: int | None = Query(default=None, ge=1, le=365),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        payload = service.search_facilities(
            session,
            q=_optional_string_query(q),
            facility_name=_optional_string_query(facility_name),
            site_id=_optional_string_query(site_id),
            certificate_scope=_optional_string_query(certificate_scope),
            gxp_type=_optional_string_query(gxp_type),
            province=_optional_string_query(province),
            case_states=case_state,
            change_request_states=change_request_state,
            certificate_state=_optional_string_query(certificate_state),
            certificate_expiring_within_days=certificate_expiring_within_days,
            offset=offset,
            limit=limit,
        )
        return FacilitySearchPageRead(
            items=[FacilitySearchResultRead(**row) for row in payload["items"]],
            total_count=payload["total_count"],
            offset=payload["offset"],
            limit=payload["limit"],
        )

    def get_facility_workspace(
        site_id: str,
        gxp_type: str | None = Query(default=None),
        line_code: str | None = None,
        production_line_id: str | None = None,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        payload = service.get_facility_workspace(session, site_id=site_id, gxp_type=gxp_type, line_code=line_code, production_line_id=production_line_id)
        payload["action_readiness"] = _build_facility_action_readiness(
            workflow_service=workflow_service,
            session=session,
            site_id=site_id,
            selected_gxp_type=payload["summary"].get("selected_gxp_type"),
            selected_line_code=payload["summary"].get("selected_line_code"),
            selected_production_line_id=payload["summary"].get("selected_production_line_id"),
            user=user,
        )
        return FacilityWorkspaceRead(**payload)

    def list_site_gxp_certificates(
        site_id: str,
        gxp_type: str | None = Query(default=None),
        line_code: str | None = Query(default=None),
        production_line_id: str | None = None,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return GxpCertificateListRead(
            **service.list_site_gxp_certificates(
                session,
                site_id=site_id,
                gxp_type=_optional_string_query(gxp_type),
                line_code=_optional_string_query(line_code),
                production_line_id=production_line_id,
            )
        )

    def get_gxp_certificate_version_history(
        certificate_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return GxpCertificateVersionHistoryRead(
            **service.get_gxp_certificate_version_history(session, certificate_id=certificate_id)
        )

    def get_gxp_certificate_detail(
        certificate_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        payload = service.get_gxp_certificate_detail(session, certificate_id=certificate_id)
        payload["action_readiness"] = workflow_service.get_certificate_action_readiness(
            session,
            certificate_id=certificate_id,
            user=user,
        )
        return GxpCertificateDetailRead(**payload)

    def list_site_business_eligibility_certificates(
        site_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return BusinessEligibilityListRead(
            **service.list_site_business_eligibility_certificates(
                session,
                site_id=site_id,
                user=user,
            )
        )

    def get_business_eligibility_detail(
        business_eligibility_certificate_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return BusinessEligibilityDetailRead(
            **service.get_business_eligibility_detail(
                session,
                business_eligibility_certificate_id=business_eligibility_certificate_id,
                user=user,
            )
        )

    def get_business_eligibility_version_history(
        business_eligibility_certificate_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return BusinessEligibilityVersionHistoryRead(
            **service.get_business_eligibility_version_history(
                session,
                business_eligibility_certificate_id=business_eligibility_certificate_id,
            )
        )

    def get_business_eligibility_gxp_source_evidence(
        business_eligibility_certificate_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_role(user, ALLOWED_READ_ROLES)
        return BusinessEligibilityGxpSourceEvidenceRead(
            **service.get_business_eligibility_gxp_source_evidence(
                session,
                business_eligibility_certificate_id=business_eligibility_certificate_id,
            )
        )

    app.add_api_route("/sites/{site_id}/production-lines", create_production_line_master, methods=["POST"], response_model=ProductionLineMasterCreateRead, tags=["catalog"])
    app.add_api_route("/sites/{site_id}/production-lines", list_site_production_lines, methods=["GET"], response_model=list[ProductionLineMasterRead], tags=["catalog"])
    app.add_api_route("/production-lines/{production_line_id}", get_production_line_master, methods=["GET"], response_model=ProductionLineMasterRead, tags=["catalog"])
    app.add_api_route("/companies", create_company_master, methods=["POST"], response_model=CompanyMasterCreateRead, tags=["catalog"])
    app.add_api_route("/companies/{company_id}/sites", create_site_master, methods=["POST"], response_model=SiteMasterCreateRead, tags=["catalog"])
    app.add_api_route("/companies", list_companies, methods=["GET"], response_model=list[CompanyRead], tags=["catalog"])
    app.add_api_route("/companies/{company_id}", get_company_detail, methods=["GET"], response_model=CompanyDetailRead, tags=["catalog"])
    app.add_api_route("/sites", list_sites, methods=["GET"], response_model=list[SiteRead], tags=["catalog"])
    app.add_api_route("/sites/{site_id}", get_site_detail, methods=["GET"], response_model=SiteDetailRead, tags=["catalog"])
    app.add_api_route("/cases", list_cases, methods=["GET"], response_model=list[CaseRead], tags=["catalog"])
    app.add_api_route("/cases/{case_id}", get_case_detail, methods=["GET"], response_model=CaseDetailRead, tags=["catalog"])
    app.add_api_route("/cases/{case_id}/workspace", get_case_workspace, methods=["GET"], response_model=CaseWorkspaceRead, tags=["catalog"])
    app.add_api_route(
        "/change-requests/{change_request_id}/workspace",
        get_change_request_workspace,
        methods=["GET"],
        response_model=ChangeRequestWorkspaceRead,
        tags=["catalog"],
    )
    app.add_api_route("/dashboard/summary", get_dashboard_summary, methods=["GET"], response_model=DashboardSummaryRead, tags=["catalog"])
    app.add_api_route("/reports/cases", case_report, methods=["GET"], response_model=CaseReportPageRead, tags=["catalog"])
    app.add_api_route("/reports/certificates", certificate_report, methods=["GET"], response_model=CertificateReportPageRead, tags=["catalog"])
    app.add_api_route("/reports/change-requests", change_request_report, methods=["GET"], response_model=ChangeRequestReportPageRead, tags=["catalog"])
    app.add_api_route("/search/facilities", search_facilities, methods=["GET"], response_model=FacilitySearchPageRead, tags=["catalog"])
    app.add_api_route("/sites/{site_id}/workspace", get_facility_workspace, methods=["GET"], response_model=FacilityWorkspaceRead, tags=["catalog"])
    app.add_api_route("/sites/{site_id}/gxp-certificates", list_site_gxp_certificates, methods=["GET"], response_model=GxpCertificateListRead, tags=["catalog"])
    app.add_api_route("/certificates/{certificate_id}", get_gxp_certificate_detail, methods=["GET"], response_model=GxpCertificateDetailRead, tags=["catalog"])
    app.add_api_route(
        "/certificates/{certificate_id}/versions",
        get_gxp_certificate_version_history,
        methods=["GET"],
        response_model=GxpCertificateVersionHistoryRead,
        tags=["catalog"],
    )
    app.add_api_route(
        "/sites/{site_id}/business-eligibility-certificates",
        list_site_business_eligibility_certificates,
        methods=["GET"],
        response_model=BusinessEligibilityListRead,
        tags=["catalog"],
    )
    app.add_api_route(
        "/business-eligibility-certificates/{business_eligibility_certificate_id}",
        get_business_eligibility_detail,
        methods=["GET"],
        response_model=BusinessEligibilityDetailRead,
        tags=["catalog"],
    )
    app.add_api_route(
        "/business-eligibility-certificates/{business_eligibility_certificate_id}/versions",
        get_business_eligibility_version_history,
        methods=["GET"],
        response_model=BusinessEligibilityVersionHistoryRead,
        tags=["catalog"],
    )
    app.add_api_route(
        "/business-eligibility-certificates/{business_eligibility_certificate_id}/gxp-source-evidence",
        get_business_eligibility_gxp_source_evidence,
        methods=["GET"],
        response_model=BusinessEligibilityGxpSourceEvidenceRead,
        tags=["catalog"],
    )
