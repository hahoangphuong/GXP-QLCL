from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, cast, func, or_, select, String
from sqlalchemy.orm import Session, aliased

from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityVersion,
    Case,
    Certificate,
    CertificateVersion,
    ChangeRequest,
    Company,
    InspectionEvent,
    Site,
)


class CatalogReadService:
    def list_companies(self, session: Session, *, q: str | None, limit: int):
        stmt = select(Company).order_by(Company.legacy_company_id).limit(limit)
        if q:
            stmt = stmt.where(Company.legal_name.ilike(f"%{q}%"))
        return list(session.scalars(stmt))

    def get_company(self, session: Session, company_id: str) -> Company:
        row = session.get(Company, company_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Company not found.")
        return row

    def list_sites(self, session: Session, *, q: str | None, limit: int):
        stmt = select(Site).order_by(Site.legacy_site_id).limit(limit)
        if q:
            stmt = stmt.where(Site.site_name.ilike(f"%{q}%"))
        return list(session.scalars(stmt))

    def get_site(self, session: Session, site_id: str) -> Site:
        row = session.get(Site, site_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Site not found.")
        return row

    def list_cases(self, session: Session, *, q: str | None, gxp_type: str | None, limit: int):
        stmt = select(Case).order_by(Case.legacy_inspection_id).limit(limit)
        if q:
            stmt = stmt.where(Case.legacy_inspection_code.ilike(f"%{q}%"))
        if gxp_type:
            stmt = stmt.where(Case.gxp_type == gxp_type)
        return list(session.scalars(stmt))

    def get_case(self, session: Session, case_id: str) -> Case:
        row = session.get(Case, case_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        return row

    def get_dashboard_summary(self, session: Session, *, queue_limit: int):
        today = date.today()
        expiry_cutoff = today + timedelta(days=90)
        current_certificate_version = (
            select(CertificateVersion.certificate_id, CertificateVersion.certificate_number, CertificateVersion.expiry_date)
            .where(CertificateVersion.is_latest_version.is_(True))
            .subquery()
        )

        total_facilities = session.scalar(select(func.count()).select_from(Site)) or 0
        total_cases = session.scalar(select(func.count()).select_from(Case)) or 0
        active_cases = session.scalar(
            select(func.count()).select_from(Case).where(
                Case.state.notin_([CaseState.CERTIFIED, CaseState.CLOSED, CaseState.CANCELLED])
            )
        ) or 0
        waiting_inspection = session.scalar(
            select(func.count()).select_from(Case).where(
                Case.state.in_(
                    [
                        CaseState.PLANNED,
                        CaseState.DECISION_ISSUED,
                        CaseState.INSPECTION_IN_PROGRESS,
                    ]
                )
            )
        ) or 0
        waiting_certificate_decision = session.scalar(
            select(func.count()).select_from(Case).where(Case.state == CaseState.AWAITING_CERTIFICATE_DECISION)
        ) or 0
        active_certificates = session.scalar(
            select(func.count())
            .select_from(Certificate)
            .join(current_certificate_version, current_certificate_version.c.certificate_id == Certificate.id)
            .where(
                Certificate.latest_flag.is_(True),
                or_(
                    current_certificate_version.c.expiry_date.is_(None),
                    current_certificate_version.c.expiry_date >= today,
                ),
            )
        ) or 0
        expiring_certificates_90_days = session.scalar(
            select(func.count())
            .select_from(Certificate)
            .join(current_certificate_version, current_certificate_version.c.certificate_id == Certificate.id)
            .where(
                Certificate.latest_flag.is_(True),
                current_certificate_version.c.expiry_date.is_not(None),
                current_certificate_version.c.expiry_date >= today,
                current_certificate_version.c.expiry_date <= expiry_cutoff,
            )
        ) or 0
        incomplete_changes = session.scalar(
            select(func.count()).select_from(ChangeRequest).where(
                ChangeRequest.state.in_([ChangeRequestState.RECEIVED, ChangeRequestState.UNDER_REVIEW])
            )
        ) or 0

        queue_rows = session.execute(
            select(Case, Site, Company)
            .join(Site, Site.id == Case.site_id)
            .join(Company, Company.id == Site.company_id)
            .where(Case.state.notin_([CaseState.CERTIFIED, CaseState.CLOSED, CaseState.CANCELLED]))
            .order_by(Case.opened_year.desc(), Case.legacy_inspection_id.desc(), Site.legacy_site_id.asc())
            .limit(queue_limit)
        ).all()

        queue = [
            {
                "case_id": case.id,
                "site_id": site.id,
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "gxp_type": case.gxp_type,
                "state": case.state.value,
                "reference_code": case.legacy_inspection_code,
                "opened_year": case.opened_year,
            }
            for case, site, company in queue_rows
        ]

        return {
            "total_facilities": total_facilities,
            "total_cases": total_cases,
            "active_cases": active_cases,
            "waiting_inspection": waiting_inspection,
            "waiting_certificate_decision": waiting_certificate_decision,
            "active_certificates": active_certificates,
            "expiring_certificates_90_days": expiring_certificates_90_days,
            "incomplete_changes": incomplete_changes,
            "queue": queue,
        }

    def search_facilities(
        self,
        session: Session,
        *,
        q: str | None,
        gxp_type: str | None,
        province: str | None,
        case_state: str | None,
        certificate_state: str | None,
        certificate_expiring_within_days: int | None,
        limit: int,
    ):
        stmt = select(Site.id).join(Company, Company.id == Site.company_id)
        current_certificate_base = (
            select(Certificate.id)
            .select_from(Certificate)
            .join(
                CertificateVersion,
                and_(
                    CertificateVersion.certificate_id == Certificate.id,
                    CertificateVersion.is_latest_version.is_(True),
                ),
            )
            .where(Certificate.site_id == Site.id, Certificate.latest_flag.is_(True))
            .correlate(Site)
        )

        if q:
            pattern = f"%{q}%"
            search_case = aliased(Case)
            search_certificate = aliased(Certificate)
            search_certificate_version = aliased(CertificateVersion)
            search_business_eligibility = aliased(BusinessEligibilityCertificate)
            search_business_eligibility_version = aliased(BusinessEligibilityVersion)
            stmt = (
                stmt.outerjoin(search_case, search_case.site_id == Site.id)
                .outerjoin(
                    search_certificate,
                    and_(search_certificate.site_id == Site.id, search_certificate.latest_flag.is_(True)),
                )
                .outerjoin(
                    search_certificate_version,
                    and_(
                        search_certificate_version.certificate_id == search_certificate.id,
                        search_certificate_version.is_latest_version.is_(True),
                    ),
                )
                .outerjoin(
                    search_business_eligibility,
                    search_business_eligibility.site_id == Site.id,
                )
                .outerjoin(
                    search_business_eligibility_version,
                    search_business_eligibility_version.business_eligibility_certificate_id
                    == search_business_eligibility.id,
                )
            )
            stmt = stmt.where(
                or_(
                    Site.site_name.ilike(pattern),
                    Site.short_name.ilike(pattern),
                    Site.site_address.ilike(pattern),
                    Site.province_name.ilike(pattern),
                    Site.legacy_gmp_site_code.ilike(pattern),
                    Site.legacy_glp_site_code.ilike(pattern),
                    Site.legacy_gmpbb_site_code.ilike(pattern),
                    cast(Site.legacy_site_id, String).ilike(pattern),
                    Company.legal_name.ilike(pattern),
                    Company.short_name.ilike(pattern),
                    Company.legal_address.ilike(pattern),
                    search_case.legacy_inspection_code.ilike(pattern),
                    search_case.applicable_standard.ilike(pattern),
                    search_case.scope_code.ilike(pattern),
                    search_certificate_version.certificate_number.ilike(pattern),
                    search_business_eligibility_version.certificate_number.ilike(pattern),
                )
            )

        if gxp_type:
            stmt = stmt.where(
                select(Case.id).where(Case.site_id == Site.id, Case.gxp_type == gxp_type).exists()
            )

        if province:
            stmt = stmt.where(Site.province_name.ilike(f"%{province}%"))

        if case_state:
            stmt = stmt.where(select(Case.id).where(Case.site_id == Site.id, Case.state == case_state).exists())

        if certificate_state == "active":
            stmt = stmt.where(
                current_certificate_base.where(
                    or_(CertificateVersion.expiry_date.is_(None), CertificateVersion.expiry_date >= date.today())
                ).exists()
            )

        if certificate_expiring_within_days is not None:
            expiry_cutoff = date.today() + timedelta(days=certificate_expiring_within_days)
            stmt = stmt.where(
                current_certificate_base.where(
                    CertificateVersion.expiry_date.is_not(None),
                    CertificateVersion.expiry_date >= date.today(),
                    CertificateVersion.expiry_date <= expiry_cutoff,
                ).exists()
            )

        site_ids = list(session.scalars(stmt.distinct().order_by(Site.legacy_site_id.asc(), Site.site_name.asc()).limit(limit)))
        if not site_ids:
            return []

        sites = {
            row.id: row
            for row in session.scalars(select(Site).where(Site.id.in_(site_ids)))
        }
        companies = {
            row.id: row
            for row in session.scalars(
                select(Company).where(Company.id.in_({sites[site_id].company_id for site_id in site_ids}))
            )
        }
        cases_by_site: dict[str, list[Case]] = defaultdict(list)
        for row in session.scalars(select(Case).where(Case.site_id.in_(site_ids))):
            cases_by_site[row.site_id].append(row)

        current_certificates = list(
            session.execute(
                select(Certificate, CertificateVersion)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(Certificate.site_id.in_(site_ids), Certificate.latest_flag.is_(True))
            ).all()
        )
        certificate_by_site: dict[str, list[tuple[Certificate, CertificateVersion]]] = defaultdict(list)
        for certificate, version in current_certificates:
            certificate_by_site[certificate.site_id].append((certificate, version))

        def preferred_site_code(site: Site, selected_gxp: str | None) -> str | None:
            if selected_gxp == "GMP":
                return site.legacy_gmp_site_code or site.legacy_glp_site_code or site.legacy_gmpbb_site_code or (
                    None if site.legacy_site_id is None else str(site.legacy_site_id)
                )
            if selected_gxp == "GLP":
                return site.legacy_glp_site_code or site.legacy_gmp_site_code or site.legacy_gmpbb_site_code or (
                    None if site.legacy_site_id is None else str(site.legacy_site_id)
                )
            if selected_gxp == "GMPbd":
                return site.legacy_gmpbb_site_code or site.legacy_gmp_site_code or site.legacy_glp_site_code or (
                    None if site.legacy_site_id is None else str(site.legacy_site_id)
                )
            return (
                site.legacy_gmp_site_code
                or site.legacy_glp_site_code
                or site.legacy_gmpbb_site_code
                or (None if site.legacy_site_id is None else str(site.legacy_site_id))
            )

        def latest_case(rows: list[Case]) -> Case | None:
            if not rows:
                return None
            return max(
                rows,
                key=lambda item: (
                    item.opened_year or 0,
                    item.legacy_inspection_id or 0,
                    item.updated_at,
                ),
            )

        def preferred_certificate(
            site_id: str,
            selected_gxp: str | None,
        ) -> tuple[Certificate, CertificateVersion] | None:
            rows = certificate_by_site.get(site_id, [])
            if not rows:
                return None
            matching_rows = [row for row in rows if selected_gxp and row[0].certificate_type == selected_gxp]
            pool = matching_rows or rows
            return max(
                pool,
                key=lambda item: (
                    item[1].issue_date or date.min,
                    item[1].expiry_date or date.max,
                ),
            )

        results = []
        for site_id in site_ids:
            site = sites[site_id]
            company = companies[site.company_id]
            site_cases = cases_by_site.get(site_id, [])
            latest = latest_case(site_cases)
            certificate_pair = preferred_certificate(site_id, gxp_type)
            gxp_types = sorted({item.gxp_type for item in site_cases if item.gxp_type})
            results.append(
                {
                    "site_id": site.id,
                    "legacy_site_id": site.legacy_site_id,
                    "facility_code": preferred_site_code(site, gxp_type),
                    "facility_name": site.site_name,
                    "company_name": company.legal_name,
                    "gxp_types": gxp_types,
                    "primary_standard": None if latest is None else latest.applicable_standard or latest.scope_code,
                    "province_name": site.province_name,
                    "last_inspection_code": None if latest is None else latest.legacy_inspection_code,
                    "current_state": None if latest is None else latest.state.value,
                    "current_certificate_number": None if certificate_pair is None else certificate_pair[1].certificate_number,
                    "current_certificate_expiry": None if certificate_pair is None else certificate_pair[1].expiry_date,
                }
            )
        return results

    def get_facility_workspace(self, session: Session, *, site_id: str):
        site = self.get_site(session, site_id)
        company = self.get_company(session, site.company_id)
        site_cases = list(session.scalars(select(Case).where(Case.site_id == site_id)))
        case_ids = [item.id for item in site_cases]
        event_dates = {}
        if case_ids:
            rows = session.execute(
                select(InspectionEvent.case_id, func.max(InspectionEvent.occurred_at))
                .where(InspectionEvent.case_id.in_(case_ids))
                .group_by(InspectionEvent.case_id)
            ).all()
            event_dates = {case_id: occurred_at.date() if occurred_at is not None else None for case_id, occurred_at in rows}
        change_requests = list(session.scalars(select(ChangeRequest).where(ChangeRequest.site_id == site_id)))
        current_certificates = list(
            session.execute(
                select(Certificate, CertificateVersion)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(Certificate.site_id == site_id, Certificate.latest_flag.is_(True))
            ).all()
        )

        latest_case = None
        if site_cases:
            latest_case = max(
                site_cases,
                key=lambda item: (
                    item.opened_year or 0,
                    item.legacy_inspection_id or 0,
                    item.updated_at,
                ),
            )
        current_certificate = None
        if current_certificates:
            current_certificate = max(
                current_certificates,
                key=lambda item: (
                    item[1].issue_date or date.min,
                    item[1].expiry_date or date.max,
                ),
            )

        history = [
            {
                "id": row.id,
                "source_type": "case",
                "reference_code": row.legacy_inspection_code,
                "event_type": row.inspection_type or "Đợt kiểm tra",
                "gxp_type": row.gxp_type,
                "standard": row.applicable_standard or row.scope_code,
                "occurred_on": event_dates.get(row.id),
                "state": row.state.value,
            }
            for row in site_cases
        ]
        history.extend(
            {
                "id": row.id,
                "source_type": "change_request",
                "reference_code": None if row.legacy_change_request_id is None else str(row.legacy_change_request_id),
                "event_type": "Thay đổi cơ sở",
                "gxp_type": None,
                "standard": row.scope_label,
                "occurred_on": row.submitted_on,
                "state": row.state.value,
            }
            for row in change_requests
        )
        history.sort(
            key=lambda item: (
                item["occurred_on"] is not None,
                item["occurred_on"] or date.min,
                item["reference_code"] or "",
            ),
            reverse=True,
        )

        return {
            "summary": {
                "site_id": site.id,
                "legacy_site_id": site.legacy_site_id,
                "facility_code": site.legacy_gmp_site_code
                or site.legacy_glp_site_code
                or site.legacy_gmpbb_site_code
                or (None if site.legacy_site_id is None else str(site.legacy_site_id)),
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "address": site.site_address,
                "province_name": site.province_name,
                "gxp_types": sorted({item.gxp_type for item in site_cases if item.gxp_type}),
                "current_state": None if latest_case is None else latest_case.state.value,
                "primary_standard": None if latest_case is None else latest_case.applicable_standard or latest_case.scope_code,
                "current_certificate_number": None if current_certificate is None else current_certificate[1].certificate_number,
                "current_certificate_expiry": None if current_certificate is None else current_certificate[1].expiry_date,
            },
            "history": history,
        }
