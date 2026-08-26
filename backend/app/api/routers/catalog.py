from __future__ import annotations

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from backend.app.auth import ALLOWED_READ_ROLES, AuthenticatedUser, get_authenticated_user, require_role
from backend.app.api.session import get_session_from_request_factory
from backend.app.read_models import (
    CaseDetailRead,
    CaseRead,
    CompanyDetailRead,
    CompanyRead,
    SiteDetailRead,
    SiteRead,
)
from backend.app.services import CatalogReadService

def register_catalog_routes(app, session_factory) -> None:
    dependency = Depends(get_session_from_request_factory(session_factory))
    service = CatalogReadService()

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
        return CaseDetailRead(
            id=row.id,
            legacy_inspection_id=row.legacy_inspection_id,
            legacy_inspection_code=row.legacy_inspection_code,
            site_id=row.site_id,
            gxp_type=row.gxp_type,
            scope_code=row.scope_code,
            applicable_standard=row.applicable_standard,
            inspection_type=row.inspection_type,
            state=row.state.value,
            opened_year=row.opened_year,
            row_version=row.row_version,
        )

    app.add_api_route("/companies", list_companies, methods=["GET"], response_model=list[CompanyRead], tags=["catalog"])
    app.add_api_route("/companies/{company_id}", get_company_detail, methods=["GET"], response_model=CompanyDetailRead, tags=["catalog"])
    app.add_api_route("/sites", list_sites, methods=["GET"], response_model=list[SiteRead], tags=["catalog"])
    app.add_api_route("/sites/{site_id}", get_site_detail, methods=["GET"], response_model=SiteDetailRead, tags=["catalog"])
    app.add_api_route("/cases", list_cases, methods=["GET"], response_model=list[CaseRead], tags=["catalog"])
    app.add_api_route("/cases/{case_id}", get_case_detail, methods=["GET"], response_model=CaseDetailRead, tags=["catalog"])
