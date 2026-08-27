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

ACTIVE_CASE_STATES = [
    CaseState.DRAFT,
    CaseState.APPLICATION_RECEIVED,
    CaseState.UNDER_ASSESSMENT,
    CaseState.PLANNED,
    CaseState.DECISION_ISSUED,
    CaseState.INSPECTION_IN_PROGRESS,
    CaseState.INSPECTION_COMPLETED,
    CaseState.AWAITING_CERTIFICATE_DECISION,
]

WAITING_INSPECTION_CASE_STATES = [
    CaseState.PLANNED,
    CaseState.DECISION_ISSUED,
    CaseState.INSPECTION_IN_PROGRESS,
]

OPEN_CHANGE_REQUEST_STATES = [
    ChangeRequestState.RECEIVED,
    ChangeRequestState.UNDER_REVIEW,
]


class CatalogReadService:
    @staticmethod
    def _preferred_site_code(site: Site, selected_gxp: str | None) -> str | None:
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

    @staticmethod
    def _select_latest_case(rows: list[Case]) -> Case | None:
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

    @staticmethod
    def _select_current_certificate(
        rows: list[tuple[Certificate, CertificateVersion]],
        selected_gxp: str | None,
    ) -> tuple[Certificate, CertificateVersion] | None:
        if not rows:
            return None
        if selected_gxp:
            rows = [row for row in rows if row[0].certificate_type == selected_gxp]
            if not rows:
                return None
        return max(
            rows,
            key=lambda item: (
                item[1].issue_date or date.min,
                item[1].expiry_date or date.max,
                item[0].updated_at,
            ),
        )

    @staticmethod
    def _build_case_exists_clause(
        *,
        gxp_type: str | None = None,
        case_states: list[str] | None = None,
    ):
        conditions = [Case.site_id == Site.id]
        if gxp_type:
            conditions.append(Case.gxp_type == gxp_type)
        if case_states:
            conditions.append(Case.state.in_(case_states))
        return select(Case.id).where(*conditions).exists()

    @staticmethod
    def _build_change_request_exists_clause(*, change_request_states: list[str] | None = None):
        conditions = [ChangeRequest.site_id == Site.id]
        if change_request_states:
            conditions.append(ChangeRequest.state.in_(change_request_states))
        return select(ChangeRequest.id).where(*conditions).exists()

    @staticmethod
    def _build_current_certificate_exists_clause(
        *,
        gxp_type: str | None = None,
        certificate_state: str | None = None,
        certificate_expiring_within_days: int | None = None,
    ):
        conditions = [Certificate.site_id == Site.id, Certificate.latest_flag.is_(True)]
        if gxp_type:
            conditions.append(Certificate.certificate_type == gxp_type)
        if certificate_state == "active":
            conditions.append(
                or_(CertificateVersion.expiry_date.is_(None), CertificateVersion.expiry_date >= date.today())
            )
        if certificate_expiring_within_days is not None:
            expiry_cutoff = date.today() + timedelta(days=certificate_expiring_within_days)
            conditions.extend(
                [
                    CertificateVersion.expiry_date.is_not(None),
                    CertificateVersion.expiry_date >= date.today(),
                    CertificateVersion.expiry_date <= expiry_cutoff,
                ]
            )
        return (
            select(Certificate.id)
            .select_from(Certificate)
            .join(
                CertificateVersion,
                and_(
                    CertificateVersion.certificate_id == Certificate.id,
                    CertificateVersion.is_latest_version.is_(True),
                ),
            )
            .where(*conditions)
            .correlate(Site)
            .exists()
        )

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
        total_facilities = session.scalar(select(func.count()).select_from(Site)) or 0
        total_cases = session.scalar(select(func.count()).select_from(Case)) or 0
        active_cases = session.scalar(
            select(func.count()).select_from(Site).where(
                self._build_case_exists_clause(case_states=[state.value for state in ACTIVE_CASE_STATES])
            )
        ) or 0
        waiting_inspection = session.scalar(
            select(func.count()).select_from(Site).where(
                self._build_case_exists_clause(case_states=[state.value for state in WAITING_INSPECTION_CASE_STATES])
            )
        ) or 0
        waiting_certificate_decision = session.scalar(
            select(func.count()).select_from(Site).where(
                self._build_case_exists_clause(case_states=[CaseState.AWAITING_CERTIFICATE_DECISION.value])
            )
        ) or 0
        active_certificates = session.scalar(
            select(func.count()).select_from(Site).where(
                self._build_current_certificate_exists_clause(certificate_state="active")
            )
        ) or 0
        expiring_certificates_90_days = session.scalar(
            select(func.count()).select_from(Site).where(
                self._build_current_certificate_exists_clause(certificate_expiring_within_days=90)
            )
        ) or 0
        incomplete_changes = session.scalar(
            select(func.count()).select_from(Site).where(
                self._build_change_request_exists_clause(
                    change_request_states=[state.value for state in OPEN_CHANGE_REQUEST_STATES]
                )
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
        case_states: list[str] | None,
        change_request_states: list[str] | None,
        certificate_state: str | None,
        certificate_expiring_within_days: int | None,
        limit: int,
    ):
        stmt = select(Site.id).join(Company, Company.id == Site.company_id)

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
            stmt = stmt.where(self._build_case_exists_clause(gxp_type=gxp_type))

        if province:
            stmt = stmt.where(Site.province_name.ilike(f"%{province}%"))

        if case_states:
            stmt = stmt.where(self._build_case_exists_clause(gxp_type=gxp_type, case_states=case_states))

        if change_request_states:
            stmt = stmt.where(self._build_change_request_exists_clause(change_request_states=change_request_states))

        if certificate_state == "active":
            stmt = stmt.where(
                self._build_current_certificate_exists_clause(
                    gxp_type=gxp_type,
                    certificate_state=certificate_state,
                )
            )

        if certificate_expiring_within_days is not None:
            stmt = stmt.where(
                self._build_current_certificate_exists_clause(
                    gxp_type=gxp_type,
                    certificate_expiring_within_days=certificate_expiring_within_days,
                )
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

        results = []
        for site_id in site_ids:
            site = sites[site_id]
            company = companies[site.company_id]
            site_cases = cases_by_site.get(site_id, [])
            scoped_cases = [row for row in site_cases if row.gxp_type == gxp_type] if gxp_type else site_cases
            latest = self._select_latest_case(scoped_cases)
            certificate_pair = self._select_current_certificate(certificate_by_site.get(site_id, []), gxp_type)
            gxp_types = sorted({item.gxp_type for item in site_cases if item.gxp_type})
            results.append(
                {
                    "site_id": site.id,
                    "legacy_site_id": site.legacy_site_id,
                    "facility_code": self._preferred_site_code(site, gxp_type),
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

    def get_facility_workspace(self, session: Session, *, site_id: str, gxp_type: str | None):
        site = self.get_site(session, site_id)
        company = self.get_company(session, site.company_id)
        site_cases = list(session.scalars(select(Case).where(Case.site_id == site_id)))
        scoped_cases = [row for row in site_cases if row.gxp_type == gxp_type] if gxp_type else site_cases
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
        if scoped_cases:
            latest_case = self._select_latest_case(scoped_cases)
        current_certificate = self._select_current_certificate(current_certificates, gxp_type)

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
            for row in scoped_cases
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
                "facility_code": self._preferred_site_code(site, gxp_type),
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "address": site.site_address,
                "province_name": site.province_name,
                "gxp_types": sorted({item.gxp_type for item in site_cases if item.gxp_type}),
                "selected_gxp_type": gxp_type,
                "current_state": None if latest_case is None else latest_case.state.value,
                "primary_standard": None if latest_case is None else latest_case.applicable_standard or latest_case.scope_code,
                "current_certificate_number": None if current_certificate is None else current_certificate[1].certificate_number,
                "current_certificate_expiry": None if current_certificate is None else current_certificate[1].expiry_date,
            },
            "history": history,
        }
