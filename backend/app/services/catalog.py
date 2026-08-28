from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, cast, func, or_, select, String, union_all
from sqlalchemy.orm import Session, aliased

from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityVersion,
    Case,
    Certificate,
    CertificateScope,
    CertificateVersion,
    ChangeRequest,
    Company,
    InspectionEvent,
    InspectionOutcome,
    Site,
)
from backend.app.db.enums import InspectionEventType

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


@dataclass(frozen=True)
class CertificateContextRow:
    certificate: Certificate
    version: CertificateVersion
    line_code: str | None
    scope_summary: str | None


class CatalogReadService:
    @staticmethod
    def _normalized_line_code_sql(column):
        return func.nullif(func.trim(column), "")

    @staticmethod
    def _normalize_line_code(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

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
        if selected_gxp == "GMPbb":
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
    def _build_context_code(site: Site, *, gxp_type: str | None, line_code: str | None) -> str | None:
        base_code = CatalogReadService._preferred_site_code(site, gxp_type)
        if base_code is None:
            return line_code
        return f"{base_code}{line_code}" if line_code else base_code

    @staticmethod
    def _build_result_key(site_id: str, *, gxp_type: str | None, line_code: str | None) -> str:
        return f"{site_id}:{gxp_type or ''}:{line_code or ''}"

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
    def _select_current_certificate_context(
        rows: list[CertificateContextRow],
        selected_gxp: str | None,
        line_code: str | None = None,
    ) -> CertificateContextRow | None:
        if not rows:
            return None
        if selected_gxp:
            rows = [row for row in rows if row.certificate.certificate_type == selected_gxp]
            if not rows:
                return None
        if line_code is not None:
            exact_matches = [row for row in rows if row.line_code == line_code]
            if exact_matches:
                rows = exact_matches
            else:
                facility_wide_matches = [row for row in rows if row.line_code is None]
                if not facility_wide_matches:
                    return None
                rows = facility_wide_matches
        return max(
            rows,
            key=lambda item: (
                item.version.issue_date or date.min,
                item.version.expiry_date or date.max,
                item.certificate.updated_at,
            ),
        )

    @staticmethod
    def _build_certificate_scope_summary(rows: list[CertificateScope]) -> str | None:
        parts = [
            row.scope_text.strip()
            for row in sorted(rows, key=lambda item: (item.sort_order, item.created_at, item.id))
            if row.scope_text and row.scope_text.strip()
        ]
        if not parts:
            return None
        return "\n".join(parts)

    @staticmethod
    def _derive_certificate_status(row: CertificateContextRow | None) -> str | None:
        if row is None:
            return None
        expiry = row.version.expiry_date
        if expiry is not None and expiry < date.today():
            return "expired"
        return "active"

    @staticmethod
    def _certificate_line_code(certificate: Certificate, linked_case: Case | None) -> str | None:
        direct_line_code = CatalogReadService._normalize_line_code(certificate.line_code)
        if direct_line_code is not None:
            return direct_line_code
        if linked_case is None:
            return None
        return CatalogReadService._normalize_line_code(linked_case.scope_code)

    @staticmethod
    def _build_site_contexts(
        *,
        site_cases: list[Case],
        certificate_rows: list[CertificateContextRow],
        requested_gxp: str | None,
    ) -> list[tuple[str | None, str | None, list[Case]]]:
        grouped_cases: dict[tuple[str | None, str | None], list[Case]] = defaultdict(list)
        for row in site_cases:
            grouped_cases[(row.gxp_type, CatalogReadService._normalize_line_code(row.scope_code))].append(row)

        discovered_gxp_types = sorted(
            {
                row.gxp_type
                for row in site_cases
                if row.gxp_type
            }
            | {
                row.certificate.certificate_type
                for row in certificate_rows
                if row.certificate.certificate_type
            }
        )
        if requested_gxp:
            discovered_gxp_types = [requested_gxp]
        if not discovered_gxp_types:
            discovered_gxp_types = [None]

        contexts: list[tuple[str | None, str | None, list[Case]]] = []
        for current_gxp in discovered_gxp_types:
            case_line_codes = {
                line_code
                for (group_gxp, line_code), cases in grouped_cases.items()
                if group_gxp == current_gxp and cases
            }
            certificate_line_codes = {
                row.line_code
                for row in certificate_rows
                if row.certificate.certificate_type == current_gxp and row.line_code is not None
            }
            all_line_codes = sorted(case_line_codes | certificate_line_codes, key=lambda item: item or "")
            if all_line_codes:
                for line_code in all_line_codes:
                    contexts.append((current_gxp, line_code, grouped_cases.get((current_gxp, line_code), [])))
            elif (current_gxp, None) in grouped_cases:
                contexts.append((current_gxp, None, grouped_cases[(current_gxp, None)]))
            else:
                contexts.append((current_gxp, None, []))
        return contexts

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
        certificate_scope: str | None = None,
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
            .outerjoin(CertificateScope, CertificateScope.certificate_version_id == CertificateVersion.id)
            .where(*conditions)
            .where(
                CertificateScope.scope_text.ilike(f"%{certificate_scope}%")
                if certificate_scope
                else True
            )
            .correlate(Site)
            .exists()
        )

    def _build_filtered_search_sites_stmt(
        self,
        *,
        q: str | None = None,
        facility_name: str | None = None,
        certificate_scope: str | None = None,
        gxp_type: str | None = None,
        province: str | None = None,
        case_states: list[str] | None = None,
        change_request_states: list[str] | None = None,
        certificate_state: str | None = None,
        certificate_expiring_within_days: int | None = None,
    ):
        stmt = select(
            Site.id.label("site_id"),
            Site.legacy_site_id.label("legacy_site_id"),
            Site.site_name.label("site_name"),
        ).join(Company, Company.id == Site.company_id)

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
                .outerjoin(search_business_eligibility, search_business_eligibility.site_id == Site.id)
                .outerjoin(
                    search_business_eligibility_version,
                    search_business_eligibility_version.business_eligibility_certificate_id == search_business_eligibility.id,
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

        if facility_name:
            stmt = stmt.where(Site.site_name.ilike(f"%{facility_name}%"))

        if gxp_type:
            stmt = stmt.where(
                or_(
                    self._build_case_exists_clause(gxp_type=gxp_type),
                    self._build_current_certificate_exists_clause(gxp_type=gxp_type),
                )
            )

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

        if certificate_scope:
            stmt = stmt.where(
                self._build_current_certificate_exists_clause(
                    gxp_type=gxp_type,
                    certificate_scope=certificate_scope,
                )
            )

        return stmt.distinct()

    def _build_context_case_exists_clause(self, contexts, *, case_states: list[str] | None):
        normalized_scope_code = self._normalized_line_code_sql(Case.scope_code)
        conditions = [
            Case.site_id == contexts.c.site_id,
            Case.gxp_type == contexts.c.gxp_type,
            or_(
                and_(contexts.c.line_code.is_(None), normalized_scope_code.is_(None)),
                normalized_scope_code == contexts.c.line_code,
            ),
        ]
        if case_states:
            conditions.append(Case.state.in_(case_states))
        return select(Case.id).where(*conditions).correlate(contexts).exists()

    def _build_context_certificate_exists_clause(
        self,
        contexts,
        *,
        certificate_state: str | None,
        certificate_expiring_within_days: int | None,
        certificate_scope: str | None,
    ):
        linked_case = aliased(Case)
        normalized_line_code = self._normalized_line_code_sql(func.coalesce(Certificate.line_code, linked_case.scope_code))
        conditions = [
            Certificate.site_id == contexts.c.site_id,
            Certificate.certificate_type == contexts.c.gxp_type,
            Certificate.latest_flag.is_(True),
            or_(
                and_(contexts.c.line_code.is_(None), normalized_line_code.is_(None)),
                and_(
                    contexts.c.line_code.is_not(None),
                    or_(normalized_line_code == contexts.c.line_code, normalized_line_code.is_(None)),
                ),
            ),
        ]
        if certificate_state == "active":
            conditions.append(or_(CertificateVersion.expiry_date.is_(None), CertificateVersion.expiry_date >= date.today()))
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
            .outerjoin(CertificateScope, CertificateScope.certificate_version_id == CertificateVersion.id)
            .outerjoin(linked_case, linked_case.id == Certificate.case_id)
            .where(*conditions)
            .where(
                CertificateScope.scope_text.ilike(f"%{certificate_scope}%")
                if certificate_scope
                else True
            )
            .correlate(contexts)
            .exists()
        )

    def _build_search_contexts_stmt(
        self,
        filtered_sites_stmt,
        *,
        gxp_type: str | None = None,
        case_states: list[str] | None = None,
        certificate_state: str | None = None,
        certificate_expiring_within_days: int | None = None,
        certificate_scope: str | None = None,
    ):
        filtered_sites = filtered_sites_stmt.subquery("filtered_sites")
        linked_case = aliased(Case)
        certificate_line_code = self._normalized_line_code_sql(func.coalesce(Certificate.line_code, linked_case.scope_code))

        case_contexts = (
            select(
                filtered_sites.c.site_id,
                filtered_sites.c.legacy_site_id,
                filtered_sites.c.site_name,
                Case.gxp_type.label("gxp_type"),
                self._normalized_line_code_sql(Case.scope_code).label("line_code"),
            )
            .join(Case, Case.site_id == filtered_sites.c.site_id)
        )
        if gxp_type:
            case_contexts = case_contexts.where(Case.gxp_type == gxp_type)

        certificate_contexts = (
            select(
                filtered_sites.c.site_id,
                filtered_sites.c.legacy_site_id,
                filtered_sites.c.site_name,
                Certificate.certificate_type.label("gxp_type"),
                certificate_line_code.label("line_code"),
            )
            .join(Certificate, Certificate.site_id == filtered_sites.c.site_id)
            .join(
                CertificateVersion,
                and_(
                    CertificateVersion.certificate_id == Certificate.id,
                    CertificateVersion.is_latest_version.is_(True),
                ),
            )
            .outerjoin(linked_case, linked_case.id == Certificate.case_id)
            .where(Certificate.latest_flag.is_(True))
        )
        if gxp_type:
            certificate_contexts = certificate_contexts.where(Certificate.certificate_type == gxp_type)

        context_selects = [case_contexts, certificate_contexts]
        if gxp_type is None:
            fallback_certificate_exists = (
                select(Certificate.id)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(Certificate.site_id == filtered_sites.c.site_id, Certificate.latest_flag.is_(True))
                .correlate(filtered_sites)
                .exists()
            )
            facility_fallback_contexts = select(
                filtered_sites.c.site_id,
                filtered_sites.c.legacy_site_id,
                filtered_sites.c.site_name,
                cast(None, String).label("gxp_type"),
                cast(None, String).label("line_code"),
            ).where(
                ~select(Case.id).where(Case.site_id == filtered_sites.c.site_id).correlate(filtered_sites).exists(),
                ~fallback_certificate_exists,
            )
            context_selects.append(facility_fallback_contexts)

        unioned_contexts = union_all(*context_selects).subquery("search_context_candidates")
        contexts_stmt = select(
            unioned_contexts.c.site_id,
            unioned_contexts.c.legacy_site_id,
            unioned_contexts.c.site_name,
            unioned_contexts.c.gxp_type,
            unioned_contexts.c.line_code,
        ).distinct()
        contexts = contexts_stmt.subquery("search_contexts_filtered")
        filtered_contexts_stmt = select(
            contexts.c.site_id,
            contexts.c.legacy_site_id,
            contexts.c.site_name,
            contexts.c.gxp_type,
            contexts.c.line_code,
        )
        if gxp_type:
            filtered_contexts_stmt = filtered_contexts_stmt.where(contexts.c.gxp_type == gxp_type)
        if case_states:
            filtered_contexts_stmt = filtered_contexts_stmt.where(
                self._build_context_case_exists_clause(contexts, case_states=case_states)
            )
        if certificate_state == "active" or certificate_expiring_within_days is not None:
            filtered_contexts_stmt = filtered_contexts_stmt.where(
                self._build_context_certificate_exists_clause(
                    contexts,
                    certificate_state=certificate_state,
                    certificate_expiring_within_days=certificate_expiring_within_days,
                    certificate_scope=None,
                )
            )
        if certificate_scope:
            filtered_contexts_stmt = filtered_contexts_stmt.where(
                self._build_context_certificate_exists_clause(
                    contexts,
                    certificate_state=None,
                    certificate_expiring_within_days=None,
                    certificate_scope=certificate_scope,
                )
            )
        return filtered_contexts_stmt

    @staticmethod
    def _ordered_search_contexts_stmt(contexts_stmt):
        contexts = contexts_stmt.subquery("search_contexts")
        return select(
            contexts.c.site_id,
            contexts.c.legacy_site_id,
            contexts.c.site_name,
            contexts.c.gxp_type,
            contexts.c.line_code,
        ).order_by(
            contexts.c.legacy_site_id.is_(None),
            contexts.c.legacy_site_id.asc(),
            contexts.c.site_name.asc(),
            contexts.c.gxp_type.is_(None),
            contexts.c.gxp_type.asc(),
            contexts.c.line_code.is_(None),
            contexts.c.line_code.asc(),
            contexts.c.site_id.asc(),
        )

    def _build_case_context_match_clause(self, page_contexts: list[tuple[str, str | None, str | None]]):
        normalized_scope_code = self._normalized_line_code_sql(Case.scope_code)
        conditions = []
        for site_id, current_gxp, line_code in page_contexts:
            row_conditions = [Case.site_id == site_id]
            if current_gxp is None:
                row_conditions.append(Case.gxp_type.is_(None))
            else:
                row_conditions.append(Case.gxp_type == current_gxp)
            if line_code is None:
                row_conditions.append(normalized_scope_code.is_(None))
            else:
                row_conditions.append(normalized_scope_code == line_code)
            conditions.append(and_(*row_conditions))
        if not conditions:
            return None
        return or_(*conditions)

    def _build_certificate_context_match_clause(self, page_contexts: list[tuple[str, str | None, str | None]], linked_case):
        normalized_line_code = self._normalized_line_code_sql(func.coalesce(Certificate.line_code, linked_case.scope_code))
        conditions = []
        for site_id, current_gxp, line_code in page_contexts:
            row_conditions = [Certificate.site_id == site_id]
            if current_gxp is None:
                row_conditions.append(Certificate.certificate_type.is_(None))
            else:
                row_conditions.append(Certificate.certificate_type == current_gxp)
            if line_code is None:
                row_conditions.append(normalized_line_code.is_(None))
            else:
                row_conditions.append(or_(normalized_line_code == line_code, normalized_line_code.is_(None)))
            conditions.append(and_(*row_conditions))
        if not conditions:
            return None
        return or_(*conditions)

    @staticmethod
    def _inspection_signal_for_case(
        case: Case,
        *,
        outcomes_by_case_id: dict[str, InspectionOutcome],
        inspection_event_dates_by_case_id: dict[str, date],
    ) -> date | None:
        outcome = outcomes_by_case_id.get(case.id)
        if outcome is not None:
            if outcome.inspected_to_on is not None:
                return outcome.inspected_to_on
            if outcome.inspected_on is not None:
                return outcome.inspected_on
        return inspection_event_dates_by_case_id.get(case.id)

    def _select_latest_inspection_on(
        self,
        rows: list[Case],
        *,
        outcomes_by_case_id: dict[str, InspectionOutcome],
        inspection_event_dates_by_case_id: dict[str, date],
    ) -> date | None:
        latest_value: tuple[date, int, int, date] | None = None
        for row in rows:
            inspected_on = self._inspection_signal_for_case(
                row,
                outcomes_by_case_id=outcomes_by_case_id,
                inspection_event_dates_by_case_id=inspection_event_dates_by_case_id,
            )
            if inspected_on is None:
                continue
            candidate = (
                inspected_on,
                row.opened_year or 0,
                row.legacy_inspection_id or 0,
                row.updated_at.date(),
            )
            if latest_value is None or candidate > latest_value:
                latest_value = candidate
        return None if latest_value is None else latest_value[0]

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
        q: str | None = None,
        facility_name: str | None = None,
        certificate_scope: str | None = None,
        gxp_type: str | None = None,
        province: str | None = None,
        case_states: list[str] | None = None,
        change_request_states: list[str] | None = None,
        certificate_state: str | None = None,
        certificate_expiring_within_days: int | None = None,
        offset: int,
        limit: int,
    ):
        filtered_sites_stmt = self._build_filtered_search_sites_stmt(
            q=q,
            facility_name=facility_name,
            certificate_scope=certificate_scope,
            gxp_type=gxp_type,
            province=province,
            case_states=case_states,
            change_request_states=change_request_states,
            certificate_state=certificate_state,
            certificate_expiring_within_days=certificate_expiring_within_days,
        )
        contexts_stmt = self._build_search_contexts_stmt(
            filtered_sites_stmt,
            gxp_type=gxp_type,
            case_states=case_states,
            certificate_state=certificate_state,
            certificate_expiring_within_days=certificate_expiring_within_days,
            certificate_scope=certificate_scope,
        )
        ordered_contexts_stmt = self._ordered_search_contexts_stmt(contexts_stmt)

        total_count = session.scalar(
            select(func.count()).select_from(contexts_stmt.subquery("search_context_count"))
        ) or 0
        if total_count == 0:
            return {
                "items": [],
                "total_count": 0,
                "offset": offset,
                "limit": limit,
            }

        page_context_rows = session.execute(ordered_contexts_stmt.offset(offset).limit(limit)).all()
        if not page_context_rows:
            return {
                "items": [],
                "total_count": total_count,
                "offset": offset,
                "limit": limit,
            }

        page_site_ids = sorted({row.site_id for row in page_context_rows})
        page_contexts = [(row.site_id, row.gxp_type, self._normalize_line_code(row.line_code)) for row in page_context_rows]

        sites = {
            row.id: row
            for row in session.scalars(select(Site).where(Site.id.in_(page_site_ids)))
        }
        companies = {
            row.id: row
            for row in session.scalars(
                select(Company).where(Company.id.in_({sites[site_id].company_id for site_id in page_site_ids}))
            )
        }
        site_gxp_rows = session.execute(
            union_all(
                select(Case.site_id.label("site_id"), Case.gxp_type.label("gxp_type")).where(Case.site_id.in_(page_site_ids)),
                select(Certificate.site_id.label("site_id"), Certificate.certificate_type.label("gxp_type")).where(
                    Certificate.site_id.in_(page_site_ids),
                    Certificate.latest_flag.is_(True),
                ),
            )
        ).all()
        gxp_types_by_site: dict[str, list[str]] = defaultdict(list)
        for site_id, current_gxp in site_gxp_rows:
            if current_gxp and current_gxp not in gxp_types_by_site[site_id]:
                gxp_types_by_site[site_id].append(current_gxp)

        cases_by_site: dict[str, list[Case]] = defaultdict(list)
        cases_by_id: dict[str, Case] = {}
        case_match_clause = self._build_case_context_match_clause(page_contexts)
        for row in session.scalars(select(Case).where(case_match_clause)):
            cases_by_site[row.site_id].append(row)
            cases_by_id[row.id] = row
        case_ids = list(cases_by_id)
        outcomes_by_case_id: dict[str, InspectionOutcome] = {}
        if case_ids:
            for outcome in session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id.in_(case_ids))):
                outcomes_by_case_id[outcome.case_id] = outcome
        inspection_event_dates_by_case_id: dict[str, date] = {}
        if case_ids:
            event_rows = session.execute(
                select(InspectionEvent.case_id, func.max(InspectionEvent.occurred_at))
                .where(
                    InspectionEvent.case_id.in_(case_ids),
                    InspectionEvent.event_type == InspectionEventType.INSPECTION_EXECUTED,
                )
                .group_by(InspectionEvent.case_id)
            ).all()
            inspection_event_dates_by_case_id = {
                case_id: occurred_at.date()
                for case_id, occurred_at in event_rows
                if occurred_at is not None
            }

        current_certificates = list(
            session.execute(
                select(Certificate, CertificateVersion)
                .outerjoin(Case, Case.id == Certificate.case_id)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(
                    Certificate.latest_flag.is_(True),
                    self._build_certificate_context_match_clause(page_contexts, Case),
                )
            ).all()
        )
        certificate_scope_rows_by_version: dict[str, list[CertificateScope]] = defaultdict(list)
        version_ids = [version.id for _, version in current_certificates]
        if version_ids:
            for scope in session.scalars(select(CertificateScope).where(CertificateScope.certificate_version_id.in_(version_ids))):
                certificate_scope_rows_by_version[scope.certificate_version_id].append(scope)

        certificate_by_site: dict[str, list[CertificateContextRow]] = defaultdict(list)
        for certificate, version in current_certificates:
            linked_case = None if certificate.case_id is None else cases_by_id.get(certificate.case_id)
            certificate_by_site[certificate.site_id].append(
                CertificateContextRow(
                    certificate=certificate,
                    version=version,
                    line_code=self._certificate_line_code(certificate, linked_case),
                    scope_summary=self._build_certificate_scope_summary(
                        certificate_scope_rows_by_version.get(version.id, [])
                    ),
                )
            )

        results = []
        for page_context in page_context_rows:
            site = sites[page_context.site_id]
            company = companies[site.company_id]
            row_gxp_type = page_context.gxp_type
            line_code = self._normalize_line_code(page_context.line_code)
            context_cases = [
                row
                for row in cases_by_site.get(page_context.site_id, [])
                if row.gxp_type == row_gxp_type and self._normalize_line_code(row.scope_code) == line_code
            ]
            latest = self._select_latest_case(context_cases)
            certificate_context = self._select_current_certificate_context(
                certificate_by_site.get(page_context.site_id, []),
                row_gxp_type,
                line_code=line_code,
            )
            results.append(
                {
                    "result_key": self._build_result_key(site.id, gxp_type=row_gxp_type, line_code=line_code),
                    "site_id": site.id,
                    "legacy_site_id": site.legacy_site_id,
                    "facility_code": self._preferred_site_code(site, row_gxp_type),
                    "context_code": self._build_context_code(site, gxp_type=row_gxp_type, line_code=line_code),
                    "result_grain": "production_line" if line_code else "facility",
                    "gxp_type": row_gxp_type,
                    "line_code": line_code,
                    "facility_name": site.site_name,
                    "company_name": company.legal_name,
                    "gxp_types": sorted(gxp_types_by_site.get(page_context.site_id, [])),
                    "certificate_scope_summary": None if certificate_context is None else certificate_context.scope_summary,
                    "province_name": site.province_name,
                    "last_inspection_on": self._select_latest_inspection_on(
                        context_cases,
                        outcomes_by_case_id=outcomes_by_case_id,
                        inspection_event_dates_by_case_id=inspection_event_dates_by_case_id,
                    ),
                    "current_state": None if latest is None else latest.state.value,
                    "current_certificate_number": None if certificate_context is None else certificate_context.version.certificate_number,
                    "current_certificate_expiry": None if certificate_context is None else certificate_context.version.expiry_date,
                }
            )
        return {
            "items": results,
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
        }

    def get_facility_workspace(self, session: Session, *, site_id: str, gxp_type: str | None, line_code: str | None):
        site = self.get_site(session, site_id)
        company = self.get_company(session, site.company_id)
        site_cases = list(session.scalars(select(Case).where(Case.site_id == site_id)))
        normalized_line_code = self._normalize_line_code(line_code)
        scoped_cases = [row for row in site_cases if row.gxp_type == gxp_type] if gxp_type else site_cases
        if normalized_line_code is not None:
            scoped_cases = [row for row in scoped_cases if self._normalize_line_code(row.scope_code) == normalized_line_code]
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
        certificate_scope_rows_by_version: dict[str, list[CertificateScope]] = defaultdict(list)
        version_ids = [version.id for _, version in current_certificates]
        if version_ids:
            for scope in session.scalars(select(CertificateScope).where(CertificateScope.certificate_version_id.in_(version_ids))):
                certificate_scope_rows_by_version[scope.certificate_version_id].append(scope)
        case_by_id = {row.id: row for row in site_cases}
        certificate_context_rows = [
            CertificateContextRow(
                certificate=certificate,
                version=version,
                line_code=self._certificate_line_code(
                    certificate,
                    None if certificate.case_id is None or certificate.case_id not in case_by_id else case_by_id[certificate.case_id],
                ),
                scope_summary=self._build_certificate_scope_summary(certificate_scope_rows_by_version.get(version.id, [])),
            )
            for certificate, version in current_certificates
        ]

        latest_case = None
        if scoped_cases:
            latest_case = self._select_latest_case(scoped_cases)
        current_certificate = self._select_current_certificate_context(
            certificate_context_rows,
            gxp_type,
            line_code=normalized_line_code,
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
                "context_key": self._build_result_key(site.id, gxp_type=gxp_type, line_code=normalized_line_code),
                "site_id": site.id,
                "legacy_site_id": site.legacy_site_id,
                "facility_code": self._preferred_site_code(site, gxp_type),
                "context_code": self._build_context_code(site, gxp_type=gxp_type, line_code=normalized_line_code),
                "context_grain": "production_line" if normalized_line_code else "facility",
                "selected_line_code": normalized_line_code,
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "company_legal_address": company.legal_address,
                "address": site.site_address,
                "province_name": site.province_name,
                "gxp_types": sorted(
                    {item.gxp_type for item in site_cases if item.gxp_type}
                    | {row.certificate.certificate_type for row in certificate_context_rows if row.certificate.certificate_type}
                ),
                "selected_gxp_type": gxp_type,
                "current_state": None if latest_case is None else latest_case.state.value,
                "primary_standard": None if latest_case is None else latest_case.applicable_standard or latest_case.scope_code,
                "current_certificate_number": None if current_certificate is None else current_certificate.version.certificate_number,
                "current_certificate_issue_date": None if current_certificate is None else current_certificate.version.issue_date,
                "current_certificate_expiry": None if current_certificate is None else current_certificate.version.expiry_date,
                "current_certificate_standard": None if current_certificate is None else current_certificate.version.applicable_standard,
                "current_certificate_status": self._derive_certificate_status(current_certificate),
                "certificate_scope_summary": None if current_certificate is None else current_certificate.scope_summary,
            },
            "history": history,
        }
