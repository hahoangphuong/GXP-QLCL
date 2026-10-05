from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from backend.app.audit_payload import normalize_and_redact_audit_payload
from backend.app.auth import AuthenticatedUser
from backend.app.db.enums import AuditActorType, CaseState, ChangeRequestState, InspectionEventType
from backend.app.db.models.phase1 import (
    AppUser,
    AuditEvent,
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion,
    CapaCycle,
    Case,
    CaseEvaluationScope,
    CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection,
    CaseEvaluationScopeUnkeyedEntry,
    CaseApplication,
    CaseAssessment,
    Certificate,
    CertificateScope,
    CertificateVersion,
    ChangeApproval,
    ChangeRequest,
    ChangeRequestAffectedArtifact,
    ChangeRequestDetail,
    ChangeRequestIssuedArtifact,
    Company,
    InspectionEvent,
    InspectionTeam,
    InspectionTeamMember,
    InspectionTeamParticipantCatalog,
    InspectorProfile,
    InspectionOutcome,
    InspectionPeriodSegment,
    InspectionPlan,
    InspectionApprovalSubmission,
    Person,
    ProductionLine,
    Site,
    EvaluationScopeTaxonomyNode,
    EvaluationScopeTaxonomyVersion,
)
from backend.app.domain.inspection_contracts import (
    InspectionContractViolation,
    validate_structured_team_member,
    validate_runtime_team_member,
    validate_unique_team_sort_orders,
    validate_time_requires_date,
    validate_ct_parent,
    validate_approval_completion,
)


ALLOWED_CASE_TRANSITIONS: dict[CaseState, set[CaseState]] = {
    CaseState.DRAFT: {CaseState.APPLICATION_RECEIVED, CaseState.CANCELLED},
    CaseState.APPLICATION_RECEIVED: {CaseState.UNDER_ASSESSMENT, CaseState.CANCELLED},
    CaseState.UNDER_ASSESSMENT: {CaseState.PLANNED, CaseState.CANCELLED},
    CaseState.PLANNED: {CaseState.DECISION_ISSUED, CaseState.CANCELLED},
    CaseState.DECISION_ISSUED: {CaseState.INSPECTION_IN_PROGRESS, CaseState.CANCELLED},
    CaseState.INSPECTION_IN_PROGRESS: {CaseState.INSPECTION_COMPLETED, CaseState.CANCELLED},
    CaseState.INSPECTION_COMPLETED: {CaseState.AWAITING_CERTIFICATE_DECISION, CaseState.CANCELLED},
    CaseState.AWAITING_CERTIFICATE_DECISION: {CaseState.CERTIFIED, CaseState.CANCELLED},
    CaseState.CERTIFIED: {CaseState.CLOSED},
    CaseState.CLOSED: set(),
    CaseState.CANCELLED: set(),
}


CAPA_BLOCKING_STATUSES = {"requested", "submitted"}
CAPA_ACCEPTED_STATUS = "accepted"
CAPA_REJECTED_STATUS = "rejected"
BUSINESS_ELIGIBILITY_LINK_ROLES = frozenset({"source_certificate", "replacement_certificate"})
SUPPORTED_CASE_GXP_TYPES = frozenset({"GMP", "GLP", "GMPbb"})
OPEN_CASE_STATES = frozenset(
    {
        CaseState.DRAFT,
        CaseState.APPLICATION_RECEIVED,
        CaseState.UNDER_ASSESSMENT,
        CaseState.PLANNED,
        CaseState.DECISION_ISSUED,
        CaseState.INSPECTION_IN_PROGRESS,
        CaseState.INSPECTION_COMPLETED,
        CaseState.AWAITING_CERTIFICATE_DECISION,
    }
)
CREATE_INSPECTION_CASE_PERMISSION = "case.edit"
CHANGE_REQUEST_EDIT_PERMISSION = "change_request.edit"
CHANGE_REQUEST_APPROVE_PERMISSION = "change_request.approve"
CHANGE_REQUEST_EDITABLE_STATES = frozenset({ChangeRequestState.RECEIVED, ChangeRequestState.UNDER_REVIEW})
CHANGE_APPROVAL_EDITABLE_STATES = frozenset({ChangeRequestState.UNDER_REVIEW, ChangeRequestState.ACCEPTED})
ALLOWED_CHANGE_REQUEST_TRANSITIONS: dict[ChangeRequestState, set[ChangeRequestState]] = {
    ChangeRequestState.RECEIVED: {ChangeRequestState.UNDER_REVIEW},
    ChangeRequestState.UNDER_REVIEW: {ChangeRequestState.ACCEPTED, ChangeRequestState.REJECTED},
    ChangeRequestState.ACCEPTED: {ChangeRequestState.EFFECTIVE},
    ChangeRequestState.REJECTED: set(),
    ChangeRequestState.EFFECTIVE: set(),
    ChangeRequestState.SUPERSEDED: set(),
}
REASSESSMENT_INSPECTION_TYPE = "Tái"
TERMINAL_CASE_STATES = frozenset({CaseState.CLOSED, CaseState.CANCELLED})
BUSINESS_ELIGIBILITY_SUCCESSOR_COPY_FIELDS = (
    "certificate_number",
    "issued_on",
    "expires_on",
    "professional_responsible_person_name",
    "quality_assurance_person_name",
    "professional_qualification_text",
    "professional_license_number",
    "professional_license_issued_on",
    "professional_license_issuer",
    "responsible_license_issued_on",
    "responsible_license_issuer",
    "decision_reference",
    "issuance_sequence_text",
    "issuance_history_text",
    "business_activity_text",
    "handled_by_name",
    "application_dossier_reference",
    "notes",
)


def change_request_transition_permission(target_state: ChangeRequestState) -> str:
    return CHANGE_REQUEST_EDIT_PERMISSION if target_state == ChangeRequestState.UNDER_REVIEW else CHANGE_REQUEST_APPROVE_PERMISSION


def change_request_transition_eligibility_reason(
    *,
    current_state: ChangeRequestState,
    target_state: ChangeRequestState,
) -> str | None:
    if target_state == current_state:
        return "already_in_target_state"
    if target_state not in ALLOWED_CHANGE_REQUEST_TRANSITIONS.get(current_state, set()):
        return "transition_not_allowed"
    return None


def case_transition_eligibility_reason(
    *,
    current_state: CaseState,
    target_state: CaseState,
    latest_capa_status: str | None,
) -> str | None:
    """Own the CAPA-dependent transition rule for projection and mutation."""
    if target_state == current_state:
        return "already_in_target_state"
    if target_state not in ALLOWED_CASE_TRANSITIONS.get(current_state, set()):
        return "transition_not_allowed"
    if (
        (current_state == CaseState.INSPECTION_COMPLETED and target_state == CaseState.AWAITING_CERTIFICATE_DECISION)
        or (current_state == CaseState.AWAITING_CERTIFICATE_DECISION and target_state == CaseState.CERTIFIED)
    ) and latest_capa_status is not None and latest_capa_status != CAPA_ACCEPTED_STATUS:
        return "latest_capa_not_accepted"
    return None


def inspection_period_edit_readiness(*, outcome: InspectionOutcome | None, terminal_case: bool) -> dict[str, Any]:
    """A missing outcome is a new runtime aggregate; an existing NULL is legacy-unknown."""
    if terminal_case:
        return {"available": False, "reason_code": "terminal_case", "expected_version": None if outcome is None else outcome.row_version, "mode": None}
    if outcome is None:
        return {"available": True, "reason_code": None, "expected_version": None, "mode": "initialize"}
    if outcome.inspection_period_state != "KNOWN":
        return {"available": False, "reason_code": "legacy_period_state_unclassified" if outcome.inspection_period_state is None else "source_owned_period_state", "expected_version": outcome.row_version, "mode": None}
    return {"available": True, "reason_code": None, "expected_version": outcome.row_version, "mode": "replace"}


def inspection_team_edit_readiness(*, team: InspectionTeam | None, terminal_case: bool, round_trip_safe: bool, blocked_reason_code: str | None) -> dict[str, Any]:
    if terminal_case:
        return {"available": False, "reason_code": "terminal_case", "expected_version": None if team is None else team.row_version, "mode": None}
    if not round_trip_safe:
        return {"available": False, "reason_code": blocked_reason_code or "unresolved_member_identity", "expected_version": None if team is None else team.row_version, "mode": None}
    return {"available": True, "reason_code": None, "expected_version": None if team is None else team.row_version, "mode": "initialize" if team is None else "replace"}


def inspection_team_existing_identity_state(
    session: Session,
    *,
    members: list[InspectionTeamMember],
) -> dict[str, Any]:
    """Resolve persisted team identities for both readiness and runtime replacement."""
    if not members:
        return {
            "round_trip_safe": False,
            "blocked_reason_code": "unresolved_member_identity",
            "member_states": {},
        }

    profile_ids = {member.inspector_profile_id for member in members if member.inspector_profile_id}
    profiles_by_id = {
        profile.id: profile
        for profile in session.scalars(select(InspectorProfile).where(InspectorProfile.id.in_(profile_ids)))
    } if profile_ids else {}

    direct_person_ids = {member.person_id for member in members if member.person_id}
    person_ids = direct_person_ids | {profile.person_id for profile in profiles_by_id.values()}
    people_by_id = {
        person.id: person
        for person in session.scalars(select(Person).where(Person.id.in_(person_ids)))
    } if person_ids else {}
    inspector_owned_person_ids = set(
        session.scalars(
            select(InspectorProfile.person_id).where(InspectorProfile.person_id.in_(direct_person_ids))
        )
    ) if direct_person_ids else set()

    participant_ids = {member.participant_catalog_id for member in members if member.participant_catalog_id}
    participants_by_id = {
        participant.id: participant
        for participant in session.scalars(
            select(InspectionTeamParticipantCatalog).where(
                InspectionTeamParticipantCatalog.id.in_(participant_ids)
            )
        )
    } if participant_ids else {}

    member_states: dict[str, dict[str, Any]] = {}
    all_resolved = True
    contains_legacy_person = any(member.identity_kind == "LEGACY_PERSON" for member in members)

    for member in members:
        profile = profiles_by_id.get(member.inspector_profile_id) if member.inspector_profile_id else None
        person = (
            people_by_id.get(member.person_id)
            if member.person_id
            else (people_by_id.get(profile.person_id) if profile is not None else None)
        )
        participant = (
            participants_by_id.get(member.participant_catalog_id)
            if member.participant_catalog_id
            else None
        )

        identity_resolved = False
        canonical_display_name = None

        if member.identity_kind == "ORGANIZATION_REPRESENTATIVE":
            identity_resolved = bool(
                member.participant_catalog_id
                and member.inspector_profile_id is None
                and member.person_id is None
                and participant is not None
                and participant.is_active
                and participant.participant_kind == "ORGANIZATION_REPRESENTATIVE"
            )
            canonical_display_name = None if participant is None else participant.display_name
        elif member.identity_kind in {None, "INSPECTOR_PROFILE"}:
            profile_selected = member.inspector_profile_id is not None
            person_selected = member.person_id is not None
            valid_shape = (
                member.participant_catalog_id is None
                and profile_selected != person_selected
                and (
                    member.identity_kind is None
                    or (member.identity_kind == "INSPECTOR_PROFILE" and profile_selected)
                )
            )
            if profile_selected:
                identity_resolved = bool(
                    valid_shape
                    and profile is not None
                    and profile.is_active
                    and person is not None
                )
            else:
                identity_resolved = bool(
                    valid_shape
                    and person is not None
                    and member.person_id not in inspector_owned_person_ids
                )
            canonical_display_name = (
                None if person is None else (person.display_name or person.full_name)
            )

        if not identity_resolved:
            all_resolved = False
        member_states[member.id] = {
            "identity_status": "resolved" if identity_resolved else "unresolved",
            "display_name": canonical_display_name,
        }

    return {
        "round_trip_safe": all_resolved,
        "blocked_reason_code": (
            None
            if all_resolved
            else "contains_legacy_person"
            if contains_legacy_person
            else "unresolved_member_identity"
        ),
        "member_states": member_states,
    }


class CaseWorkflowService:
    @staticmethod
    def _provided_fields(fields_set: set[str] | None, defaults: set[str]) -> set[str]:
        """Keep direct service callers compatible while HTTP preserves omission."""
        return defaults if fields_set is None else fields_set

    @staticmethod
    def _assign_provided(row: Any, values: dict[str, Any], provided: set[str]) -> None:
        for field_name, value in values.items():
            if field_name in provided:
                setattr(row, field_name, value)

    @staticmethod
    def _normalize_line_code(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    def _assert_expected_version(self, entity, expected_version: int | None, *, label: str) -> None:
        if expected_version is None:
            return
        current_version = getattr(entity, "row_version", None)
        if current_version is None:
            raise HTTPException(status_code=500, detail=f"{label} does not expose row_version.")
        if current_version != expected_version:
            raise HTTPException(
                status_code=409,
                detail=f"Stale {label} update. Expected version {expected_version}, current version is {current_version}.",
            )

    def get_certificate_action_readiness(
        self,
        session: Session,
        *,
        certificate_id: str,
        user: AuthenticatedUser,
    ) -> list[dict[str, Any]]:
        """Describe the contextual rules still enforced by certificate mutations."""
        certificate = self._get_certificate(session, certificate_id)
        self._certificate_line_identity(session, certificate)
        version = self._load_latest_certificate_version(session, certificate.id)
        edit_permission = "certificate.edit"
        promote_permission = "certificate.approve"
        edit_reason = None if edit_permission in user.permissions else "missing_permission"
        promote_reason = None if promote_permission in user.permissions else "missing_permission"
        if promote_reason is None:
            promote_reason = self._get_certificate_promotion_blocker(session, certificate=certificate, version=version)

        return [
            {
                "action_key": "edit_latest_version",
                "label": "Cập nhật chứng nhận",
                "available": edit_reason is None,
                "reason_code": edit_reason,
                "required_permissions": [edit_permission],
                "expected_version": certificate.row_version,
            },
            {
                "action_key": "promote_current",
                "label": "Đặt làm chứng nhận hiện hành",
                "available": promote_reason is None,
                "reason_code": promote_reason,
                "required_permissions": [promote_permission],
                "expected_version": certificate.row_version,
            },
        ]

    def get_case_certificate_issue_readiness(
        self,
        session: Session,
        *,
        case_id: str,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        case = self._get_case(session, case_id)
        permission = "certificate.issue"
        reason = None if permission in user.permissions else "missing_permission"
        if reason is None:
            if case.state not in {CaseState.AWAITING_CERTIFICATE_DECISION, CaseState.CERTIFIED}:
                reason = "case_state_not_eligible"
            else:
                latest_capa = self._latest_case_capa_cycle(session, case.id)
                if latest_capa is not None and latest_capa.status != CAPA_ACCEPTED_STATUS:
                    reason = "latest_capa_not_accepted"
        return {
            "action_key": "issue_certificate",
            "label": "Cấp chứng nhận GxP",
            "available": reason is None,
            "reason_code": reason,
            "required_permissions": [permission],
            "certificate_type": case.gxp_type,
            "issuance_basis": "inspection_case",
        }

    def get_business_eligibility_issue_readiness(
        self,
        session: Session,
        *,
        site_id: str,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        self._get_site(session, site_id)
        permission = "certificate.issue"
        reason = None if permission in user.permissions else "missing_permission"
        return {
            "action_key": "issue_business_eligibility",
            "label": "Cấp GCN đủ điều kiện",
            "available": reason is None,
            "reason_code": reason,
            "required_permissions": [permission],
        }

    def _business_eligibility_current_rows(
        self,
        session: Session,
        *,
        site_id: str,
    ) -> list[BusinessEligibilityCertificate]:
        return list(
            session.scalars(
                select(BusinessEligibilityCertificate)
                .where(
                    BusinessEligibilityCertificate.site_id == site_id,
                    BusinessEligibilityCertificate.latest_flag.is_(True),
                )
                .order_by(BusinessEligibilityCertificate.id.asc())
            )
        )

    def _get_business_eligibility_promotion_blocker(
        self,
        session: Session,
        *,
        certificate: BusinessEligibilityCertificate,
        version: BusinessEligibilityVersion,
    ) -> str | None:
        if not version.certificate_number or version.issued_on is None:
            return "certificate_data_incomplete"

        for link in session.scalars(
            select(BusinessEligibilityCertificateLink).where(
                BusinessEligibilityCertificateLink.business_eligibility_version_id == version.id
            )
        ):
            linked_certificate = session.get(Certificate, link.certificate_id)
            if linked_certificate is None:
                return "invalid_linked_certificate"
            try:
                if linked_certificate.site_id != certificate.site_id:
                    return "invalid_linked_certificate"
                self._certificate_line_identity(session, linked_certificate)
            except HTTPException:
                return "invalid_linked_certificate"

        current_rows = self._business_eligibility_current_rows(session, site_id=certificate.site_id)
        if len(current_rows) > 1:
            return "multiple_current_records"
        if len(current_rows) == 1 and current_rows[0].id == certificate.id:
            return "already_current"
        if current_rows and current_rows[0].id != certificate.id:
            try:
                current_version = self._load_latest_business_eligibility_version(session, current_rows[0].id)
            except HTTPException:
                return "current_record_incomplete"
            if current_version.issued_on is None:
                return "current_record_incomplete"
            if version.issued_on < current_version.issued_on:
                return "candidate_issue_date_precedes_current"
        return None

    def get_business_eligibility_action_readiness(
        self,
        session: Session,
        *,
        business_eligibility_certificate_id: str,
        user: AuthenticatedUser,
    ) -> list[dict[str, Any]]:
        certificate = self._get_business_eligibility(session, business_eligibility_certificate_id)
        version = self._load_latest_business_eligibility_version(session, certificate.id)
        edit_permission = "certificate.edit"
        promote_permission = "certificate.approve"
        edit_reason = None if edit_permission in user.permissions else "missing_permission"
        promote_reason = None if promote_permission in user.permissions else "missing_permission"
        if promote_reason is None:
            promote_reason = self._get_business_eligibility_promotion_blocker(
                session,
                certificate=certificate,
                version=version,
            )
        return [
            {
                "action_key": "edit_latest_version",
                "label": "Cập nhật GCN đủ điều kiện",
                "available": edit_reason is None,
                "reason_code": edit_reason,
                "required_permissions": [edit_permission],
                "expected_version": certificate.row_version,
            },
            {
                "action_key": "promote_current",
                "label": "Đặt làm GCN đủ điều kiện hiện hành",
                "available": promote_reason is None,
                "reason_code": promote_reason,
                "required_permissions": [promote_permission],
                "expected_version": certificate.row_version,
            },
        ]

    def _get_certificate_promotion_blocker(
        self,
        session: Session,
        *,
        certificate: Certificate,
        version: CertificateVersion,
    ) -> str | None:
        self._certificate_line_identity(session, certificate)
        if certificate.case_id is not None:
            case = self._get_case(session, certificate.case_id)
            if case.state not in {CaseState.AWAITING_CERTIFICATE_DECISION, CaseState.CERTIFIED}:
                return "case_state_not_eligible"
            latest_capa = self._latest_case_capa_cycle(session, case.id)
            if latest_capa is not None and latest_capa.status != CAPA_ACCEPTED_STATUS:
                return "latest_capa_not_accepted"
        if not version.certificate_number or version.issue_date is None or version.expiry_date is None:
            return "certificate_data_incomplete"
        current_peers = list(session.scalars(
            select(Certificate).where(
                self._certificate_context_clause(session, certificate),
                Certificate.latest_flag.is_(True),
            ).order_by(Certificate.id)
        ))
        for current in current_peers:
            self._certificate_line_identity(session, current)
            if current.id == certificate.id:
                continue
            current_version = self._load_latest_certificate_version(session, current.id)
            if current_version.issue_date is not None and version.issue_date < current_version.issue_date:
                return "candidate_issue_date_precedes_current"
        return None

    def _diff_fields(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
        changed: dict[str, dict[str, Any]] = {}
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                changed[key] = {"old": before.get(key), "new": after.get(key)}
        return changed

    def _normalize_audit_value(self, value: Any) -> Any:
        return normalize_and_redact_audit_payload(value)

    def _snapshot_fields(self, row: Any, field_names: list[str]) -> dict[str, Any]:
        return {
            field_name: self._normalize_audit_value(getattr(row, field_name))
            for field_name in field_names
        }

    def _team_member_payload(self, member: InspectionTeamMember) -> dict[str, Any]:
        return {
            "inspector_profile_id": member.inspector_profile_id,
            "person_id": member.person_id,
            "role_code": member.role_code,
            "role_label": member.role_label,
            "sort_order": member.sort_order,
            "identity_kind": member.identity_kind,
            "participant_catalog_id": member.participant_catalog_id,
            "display_name": member.display_name,
            "legacy_source_token": member.legacy_source_token,
        }

    def _get_site(self, session: Session, site_id: str) -> Site:
        row = session.get(Site, site_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Site not found.")
        return row

    def _lock_site(self, session: Session, site_id: str) -> Site:
        row = session.scalars(select(Site).where(Site.id == site_id).with_for_update()).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Site not found.")
        return row

    def _get_case(self, session: Session, case_id: str) -> Case:
        row = session.get(Case, case_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        return row

    @staticmethod
    def _validate_certificate_linked_case(session: Session, certificate: Certificate) -> Case | None:
        if certificate.case_id is None:
            return None
        linked_case = session.get(Case, certificate.case_id)
        if linked_case is None or linked_case.site_id != certificate.site_id or linked_case.gxp_type != certificate.certificate_type:
            raise HTTPException(status_code=409, detail="Certificate references an invalid linked Case.")
        return linked_case

    @staticmethod
    def _certificate_valid_linked_case_sql():
        return or_(
            Certificate.case_id.is_(None),
            select(Case.id)
            .where(
                Case.id == Certificate.case_id,
                Case.site_id == Certificate.site_id,
                Case.gxp_type == Certificate.certificate_type,
            )
            .correlate(Certificate)
            .exists(),
        )

    @classmethod
    def _certificate_effective_line_code(cls, session: Session, certificate: Certificate) -> str | None:
        """Return the direct-first compatibility line for a legacy certificate."""
        linked_case = cls._validate_certificate_linked_case(session, certificate)
        direct_line_code = cls._normalize_line_code(certificate.line_code)
        if direct_line_code is not None:
            return direct_line_code
        if linked_case is None:
            return None
        return cls._normalize_line_code(linked_case.scope_code)

    @staticmethod
    def _certificate_effective_line_sql():
        """SQL equivalent of the valid linked-Case compatibility fallback."""
        direct_line_code = func.nullif(func.trim(Certificate.line_code), "")
        linked_case_line_code = (
            select(func.nullif(func.trim(Case.scope_code), ""))
            .where(
                Case.id == Certificate.case_id,
                Case.site_id == Certificate.site_id,
                Case.gxp_type == Certificate.certificate_type,
            )
            .correlate(Certificate)
            .scalar_subquery()
        )
        return func.coalesce(direct_line_code, linked_case_line_code)

    @classmethod
    def _certificate_line_identity(cls, session: Session, certificate: Certificate) -> dict[str, str | None]:
        cls._validate_certificate_linked_case(session, certificate)
        if certificate.production_line_id is not None:
            line = session.get(ProductionLine, certificate.production_line_id)
            if line is None or line.site_id != certificate.site_id:
                raise HTTPException(status_code=409, detail="Certificate references an invalid canonical ProductionLine.")
            return {"production_line_id": line.id, "production_line_code": line.code, "production_line_identity_state": "canonical"}
        line_code = cls._certificate_effective_line_code(session, certificate)
        return {"production_line_id": None, "production_line_code": line_code, "production_line_identity_state": "legacy_unlinked" if line_code else "facility_wide"}

    def _certificate_context_clause(self, session: Session, certificate: Certificate):
        """Select current peers only within one canonical or legacy context."""
        base = [
            Certificate.site_id == certificate.site_id,
            Certificate.certificate_type == certificate.certificate_type,
            self._certificate_valid_linked_case_sql(),
        ]
        if certificate.production_line_id is not None:
            return and_(*base, Certificate.production_line_id == certificate.production_line_id)
        line_code = self._certificate_effective_line_code(session, certificate)
        normalized_db_line_code = self._certificate_effective_line_sql()
        if line_code is None:
            return and_(*base, Certificate.production_line_id.is_(None), normalized_db_line_code.is_(None))
        return and_(*base, Certificate.production_line_id.is_(None), normalized_db_line_code == line_code)

    def _assert_case_not_terminal(self, row: Case, *, operation: str) -> None:
        if row.state in TERMINAL_CASE_STATES:
            raise HTTPException(
                status_code=409,
                detail=f"Case {operation} is blocked for terminal state {row.state.value}.",
            )

    def _get_certificate(self, session: Session, certificate_id: str) -> Certificate:
        row = session.get(Certificate, certificate_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Certificate not found.")
        return row

    def _get_business_eligibility(self, session: Session, business_eligibility_certificate_id: str) -> BusinessEligibilityCertificate:
        row = session.get(BusinessEligibilityCertificate, business_eligibility_certificate_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Business eligibility certificate not found.")
        return row

    def _get_company(self, session: Session, company_id: str) -> Company:
        row = session.get(Company, company_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Company not found.")
        return row

    def _get_or_create_app_user(self, session: Session, user: AuthenticatedUser) -> AppUser:
        stmt = select(AppUser).where(AppUser.username == user.username)
        row = session.scalars(stmt).first()
        if row is not None:
            return row
        row = AppUser(username=user.username, display_name=user.username, is_active=True)
        session.add(row)
        session.flush()
        return row

    def _write_audit_event(
        self,
        session: Session,
        *,
        actor: AppUser,
        entity_type: str,
        entity_id: str,
        action: str,
        payload: dict[str, Any],
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        changes: dict[str, dict[str, Any]] | None = None,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> AuditEvent:
        normalized_before = None if before is None else self._normalize_audit_value(before)
        normalized_after = None if after is None else self._normalize_audit_value(after)
        if changes is None and normalized_before is not None and normalized_after is not None:
            changes = self._diff_fields(normalized_before, normalized_after)
        normalized_changes = None if changes is None else self._normalize_audit_value(changes)
        audit_event = AuditEvent(
            actor_type=AuditActorType.USER,
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            reason=reason,
            changed_fields_json=None if normalized_changes is None else json.dumps(normalized_changes, ensure_ascii=False, sort_keys=True),
            old_values_json=None if normalized_before is None else json.dumps(normalized_before, ensure_ascii=False, sort_keys=True),
            new_values_json=None if normalized_after is None else json.dumps(normalized_after, ensure_ascii=False, sort_keys=True),
            payload_redacted=json.dumps(self._normalize_audit_value(payload), ensure_ascii=False, sort_keys=True),
        )
        session.add(audit_event)
        session.flush()
        return audit_event

    def _write_inspection_event(
        self,
        session: Session,
        *,
        case_id: str,
        event_type: InspectionEventType | None,
        payload: dict[str, Any],
    ) -> InspectionEvent | None:
        if event_type is None:
            return None
        inspection_event = InspectionEvent(
            case_id=case_id,
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            payload=json.dumps(self._normalize_audit_value(payload), ensure_ascii=False),
        )
        session.add(inspection_event)
        session.flush()
        return inspection_event

    def _build_stage_payload(self, **kwargs: Any) -> dict[str, Any]:
        return {key: value for key, value in kwargs.items()}

    def _load_latest_certificate_version(self, session: Session, certificate_id: str) -> CertificateVersion:
        version = session.scalars(
            select(CertificateVersion)
            .where(CertificateVersion.certificate_id == certificate_id, CertificateVersion.is_latest_version.is_(True))
        ).first()
        if version is not None:
            return version
        version = session.scalars(
            select(CertificateVersion)
            .where(CertificateVersion.certificate_id == certificate_id)
            .order_by(CertificateVersion.version_no.desc())
        ).first()
        if version is None:
            raise HTTPException(status_code=409, detail="Certificate has no persisted version.")
        return version

    def _replace_certificate_scopes(
        self,
        session: Session,
        *,
        certificate_version_id: str,
        scopes: list[dict[str, Any]],
    ) -> list[CertificateScope]:
        existing = list(
            session.scalars(select(CertificateScope).where(CertificateScope.certificate_version_id == certificate_version_id))
        )
        for item in existing:
            session.delete(item)
        session.flush()

        created: list[CertificateScope] = []
        for payload in scopes:
            scope = CertificateScope(
                certificate_version_id=certificate_version_id,
                scope_key=payload.get("scope_key"),
                scope_text=payload["scope_text"],
                language_code=payload.get("language_code") or "vi",
                sort_order=int(payload.get("sort_order", 0)),
            )
            session.add(scope)
            created.append(scope)
        session.flush()
        return created

    def _serialize_certificate_scopes(self, scopes: list[CertificateScope]) -> list[dict[str, Any]]:
        return [
            {
                "id": scope.id,
                "scope_key": scope.scope_key,
                "scope_text": scope.scope_text,
                "language_code": scope.language_code,
                "sort_order": scope.sort_order,
            }
            for scope in sorted(scopes, key=lambda item: (item.sort_order, item.created_at, item.id))
        ]

    def _validate_certificate_case_link(
        self,
        *,
        site_id: str,
        case: Case | None,
        certificate_type: str,
        issuance_basis: str,
    ) -> None:
        if issuance_basis not in {"inspection_case", "administrative_no_inspection"}:
            raise HTTPException(status_code=422, detail="Unsupported certificate issuance basis.")
        if case is None and issuance_basis == "inspection_case":
            raise HTTPException(
                status_code=422,
                detail="inspection_case issuance requires a backing case_id.",
            )
        if case is not None and issuance_basis == "inspection_case" and certificate_type != case.gxp_type:
            raise HTTPException(
                status_code=422,
                detail="inspection_case certificate_type must match the backing case gxp_type.",
            )
        if case is not None and case.site_id != site_id:
            raise HTTPException(
                status_code=422,
                detail="Case/site mismatch: case does not belong to the requested site.",
            )

    def _assert_case_certificate_eligibility(
        self,
        session: Session,
        *,
        case: Case,
        allow_states: set[CaseState],
        blocked_detail: str,
    ) -> None:
        if case.state not in allow_states:
            allowed_values = ", ".join(sorted(item.value for item in allow_states))
            raise HTTPException(
                status_code=409,
                detail=f"Case must be in one of [{allowed_values}] before certificate workflow can continue.",
            )
        self._assert_latest_capa_accepted_if_present(session, case.id, blocked_detail=blocked_detail)

    def _assert_latest_capa_accepted_if_present(self, session: Session, case_id: str, *, blocked_detail: str) -> None:
        latest = self._latest_case_capa_cycle(session, case_id)
        if latest is not None and latest.status != CAPA_ACCEPTED_STATUS:
            raise HTTPException(status_code=409, detail=blocked_detail)

    def _load_latest_business_eligibility_version(
        self,
        session: Session,
        business_eligibility_certificate_id: str,
    ) -> BusinessEligibilityVersion:
        version = session.scalars(
            select(BusinessEligibilityVersion)
            .where(BusinessEligibilityVersion.business_eligibility_certificate_id == business_eligibility_certificate_id)
            .order_by(BusinessEligibilityVersion.version_no.desc())
        ).first()
        if version is None:
            raise HTTPException(status_code=409, detail="Business eligibility certificate has no persisted version.")
        return version

    def _replace_business_eligibility_links(
        self,
        session: Session,
        *,
        business_eligibility_version_id: str,
        linked_certificates: list[dict[str, Any]],
        site_id: str,
    ) -> list[BusinessEligibilityCertificateLink]:
        validated_links: list[tuple[str, str]] = []
        seen_certificate_ids: set[str] = set()
        for payload in linked_certificates:
            certificate_id = payload["certificate_id"]
            raw_link_role = payload.get("link_role")
            link_role = "source_certificate" if raw_link_role is None else raw_link_role
            if link_role not in BUSINESS_ELIGIBILITY_LINK_ROLES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported business eligibility link_role: {link_role}.",
                )
            if certificate_id in seen_certificate_ids:
                raise HTTPException(
                    status_code=422,
                    detail=f"Duplicate business eligibility linked certificate: {certificate_id}.",
                )
            seen_certificate_ids.add(certificate_id)
            certificate = session.get(Certificate, certificate_id)
            if certificate is None:
                raise HTTPException(status_code=404, detail=f"Linked certificate {certificate_id} was not found.")
            if certificate.site_id != site_id:
                raise HTTPException(status_code=409, detail="Business eligibility linked certificate belongs to a different site.")
            self._certificate_line_identity(session, certificate)
            validated_links.append((certificate_id, link_role))

        existing = list(
            session.scalars(
                select(BusinessEligibilityCertificateLink).where(
                    BusinessEligibilityCertificateLink.business_eligibility_version_id == business_eligibility_version_id
                )
            )
        )
        for item in existing:
            session.delete(item)
        session.flush()

        created: list[BusinessEligibilityCertificateLink] = []
        for certificate_id, link_role in validated_links:
            link = BusinessEligibilityCertificateLink(
                business_eligibility_version_id=business_eligibility_version_id,
                certificate_id=certificate_id,
                link_role=link_role,
            )
            session.add(link)
            created.append(link)
        session.flush()
        return created

    def _serialize_business_eligibility_links(
        self,
        links: list[BusinessEligibilityCertificateLink],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": link.id,
                "certificate_id": link.certificate_id,
                "link_role": link.link_role,
            }
            for link in sorted(links, key=lambda item: (item.created_at, item.id))
        ]

    def _validate_team_members(self, members: list[dict[str, Any]]) -> None:
        if not members:
            raise HTTPException(status_code=422, detail="Inspection team must include at least one member.")
        for index, item in enumerate(members):
            try:
                validate_runtime_team_member(
                    inspector_profile_id=item.get("inspector_profile_id"),
                    person_id=item.get("person_id"),
                    participant_catalog_id=item.get("participant_catalog_id"),
                    identity_kind=item.get("identity_kind"),
                    role_code=item.get("role_code"),
                    sort_order=int(item.get("sort_order", 0)),
                )
            except (InspectionContractViolation, TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Inspection team member at index {index}: {exc}",
                ) from exc
        try:
            validate_unique_team_sort_orders(int(item.get("sort_order", 0)) for item in members)
        except (InspectionContractViolation, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def _validate_team_member_identities(self, session: Session, members: list[dict[str, Any]]) -> None:
        profile_ids = {str(item["inspector_profile_id"]) for item in members if item.get("inspector_profile_id")}
        person_ids = {str(item["person_id"]) for item in members if item.get("person_id")}
        profiles = {
            str(profile.id): profile
            for profile in session.scalars(select(InspectorProfile).where(InspectorProfile.id.in_(profile_ids)))
        } if profile_ids else {}
        existing_people = set(session.scalars(select(Person.id).where(Person.id.in_(person_ids)))) if person_ids else set()
        inspector_owned_person_ids = set(
            session.scalars(
                select(InspectorProfile.person_id).where(InspectorProfile.person_id.in_(person_ids))
            )
        ) if person_ids else set()
        missing_profiles = sorted(profile_ids - set(profiles))
        inactive_profiles = sorted(profile_id for profile_id, profile in profiles.items() if not profile.is_active)
        missing_people = sorted(person_ids - existing_people)
        if missing_profiles or missing_people:
            invalid = ", ".join([
                *(f"inspector_profile:{item}" for item in missing_profiles),
                *(f"person:{item}" for item in missing_people),
            ])
            raise HTTPException(status_code=422, detail=f"Inspection team contains unknown identity: {invalid}.")
        if inactive_profiles:
            raise HTTPException(
                status_code=422,
                detail=f"Inspection team contains inactive_inspector_profile: {', '.join(inactive_profiles)}.",
            )
        if inspector_owned_person_ids:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Inspection team person identity is inspector_profile-owned: "
                    f"{', '.join(sorted(inspector_owned_person_ids))}."
                ),
            )
        catalog_ids = {str(item["participant_catalog_id"]) for item in members if item.get("participant_catalog_id")}
        catalogs = {str(item.id): item for item in session.scalars(select(InspectionTeamParticipantCatalog).where(InspectionTeamParticipantCatalog.id.in_(catalog_ids)))} if catalog_ids else {}
        missing_catalogs = sorted(catalog_ids - set(catalogs))
        inactive_catalogs = sorted(key for key, item in catalogs.items() if not item.is_active or item.participant_kind != "ORGANIZATION_REPRESENTATIVE")
        if missing_catalogs or inactive_catalogs:
            raise HTTPException(status_code=422, detail=f"Inspection team contains invalid participant catalog: {', '.join(missing_catalogs + inactive_catalogs)}.")

    def _team_member_display_name(self, session: Session, item: dict[str, Any]) -> str:
        kind = item.get("identity_kind")
        if kind == "ORGANIZATION_REPRESENTATIVE":
            catalog = session.get(InspectionTeamParticipantCatalog, item.get("participant_catalog_id"))
            if catalog is None or not catalog.is_active:
                raise HTTPException(status_code=422, detail="Inspection team participant catalog is unavailable.")
            return catalog.display_name
        profile_id = item.get("inspector_profile_id")
        person_id = item.get("person_id")
        if profile_id:
            profile = session.get(InspectorProfile, profile_id)
            person = None if profile is None else session.get(Person, profile.person_id)
        else:
            person = session.get(Person, person_id) if person_id else None
        if person is None:
            raise HTTPException(status_code=422, detail="Inspection team identity has no canonical display name.")
        return person.display_name or person.full_name

    def _get_capa_cycle(self, session: Session, capa_cycle_id: str) -> CapaCycle:
        row = session.get(CapaCycle, capa_cycle_id)
        if row is None:
            raise HTTPException(status_code=404, detail="CAPA cycle not found.")
        return row

    def _site_has_gxp_context(
        self,
        session: Session,
        *,
        site_id: str,
        gxp_type: str,
        line_code: str | None,
        production_line_id: str | None = None,
    ) -> bool:
        if production_line_id is not None:
            return session.scalars(
                select(Case.id).where(
                    Case.site_id == site_id,
                    Case.gxp_type == gxp_type,
                    Case.production_line_id == production_line_id,
                )
            ).first() is not None or session.scalars(
                select(Certificate.id).where(
                    Certificate.site_id == site_id,
                    Certificate.certificate_type == gxp_type,
                    Certificate.latest_flag.is_(True),
                    Certificate.production_line_id == production_line_id,
                    self._certificate_valid_linked_case_sql(),
                )
            ).first() is not None
        normalized_line_code = self._normalize_line_code(line_code)
        case_match = session.scalars(
            select(Case.id).where(
                Case.site_id == site_id,
                Case.gxp_type == gxp_type,
                Case.production_line_id.is_(None),
                func.nullif(func.trim(Case.scope_code), "") == normalized_line_code,
            )
        ).first()
        if case_match is not None:
            return True
        certificate_match = session.scalars(
            select(Certificate.id).where(
                Certificate.site_id == site_id,
                Certificate.certificate_type == gxp_type,
                Certificate.latest_flag.is_(True),
                Certificate.production_line_id.is_(None),
                self._certificate_valid_linked_case_sql(),
                self._certificate_effective_line_sql() == normalized_line_code,
            )
        ).first()
        return certificate_match is not None

    def _find_open_context_case(
        self,
        session: Session,
        *,
        site_id: str,
        gxp_type: str,
        line_code: str | None,
        production_line_id: str | None = None,
    ) -> Case | None:
        normalized_line_code = self._normalize_line_code(line_code)
        identity_clause = (
            Case.production_line_id == production_line_id
            if production_line_id is not None
            else and_(Case.production_line_id.is_(None), func.nullif(func.trim(Case.scope_code), "") == normalized_line_code)
        )
        return session.scalars(
            select(Case)
            .where(
                Case.site_id == site_id,
                Case.gxp_type == gxp_type,
                identity_clause,
                Case.state.in_(tuple(OPEN_CASE_STATES)),
            )
            .order_by(Case.created_at.desc(), Case.id.desc())
        ).first()

    def _validate_create_inspection_case_context(
        self,
        session: Session,
        *,
        site_id: str,
        gxp_type: str,
        line_code: str | None,
        production_line_id: str | None = None,
    ) -> tuple[str, str | None, ProductionLine | None]:
        normalized_gxp_type = str(gxp_type or "").strip()
        if normalized_gxp_type not in SUPPORTED_CASE_GXP_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported GxP context for reassessment creation.")
        normalized_line_code = self._normalize_line_code(line_code)
        line = None if production_line_id is None else session.get(ProductionLine, production_line_id)
        if production_line_id is not None:
            if line is None or line.site_id != site_id:
                raise HTTPException(status_code=422, detail="Selected ProductionLine does not belong to this site.")
            if normalized_line_code is not None and normalized_line_code != line.code:
                raise HTTPException(status_code=422, detail="line_code does not match the selected canonical ProductionLine.")
        elif normalized_line_code is not None:
            raise HTTPException(status_code=422, detail="Canonical ProductionLine identity has not been resolved for this legacy line context.")
        if not self._site_has_gxp_context(
            session,
            site_id=site_id,
            gxp_type=normalized_gxp_type,
            line_code=normalized_line_code,
            production_line_id=production_line_id,
        ):
            raise HTTPException(
                status_code=422,
                detail="Selected facility/GxP/line context is not an authoritative existing context for reassessment creation.",
            )
        return normalized_gxp_type, (None if line is None else line.code), line

    def get_create_reassessment_case_action_readiness(
        self,
        session: Session,
        *,
        site_id: str,
        gxp_type: str | None,
        line_code: str | None,
        production_line_id: str | None = None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        required_permissions = [CREATE_INSPECTION_CASE_PERMISSION]
        normalized_gxp_type = str(gxp_type or "").strip() or None
        normalized_line_code = self._normalize_line_code(line_code)
        if production_line_id is None and normalized_line_code is not None:
            return {"action_key": "create_reassessment_case", "label": "Tái đánh giá", "readiness_status": "unavailable", "detail": "Canonical ProductionLine identity has not been resolved for this legacy line context.", "required_permissions": required_permissions}
        if normalized_gxp_type is None:
            return {
                "action_key": "create_reassessment_case",
                "label": "Tái đánh giá",
                "readiness_status": "unavailable",
                "detail": "Chọn một ngữ cảnh GxP cụ thể trước khi tạo hồ sơ tái đánh giá.",
                "required_permissions": required_permissions,
            }
        if CREATE_INSPECTION_CASE_PERMISSION not in user.permissions:
            return {
                "action_key": "create_reassessment_case",
                "label": "Tái đánh giá",
                "readiness_status": "forbidden",
                "detail": "Tài khoản hiện tại không có quyền tạo hồ sơ tái đánh giá.",
                "required_permissions": required_permissions,
            }
        if normalized_gxp_type not in SUPPORTED_CASE_GXP_TYPES:
            return {
                "action_key": "create_reassessment_case",
                "label": "Tái đánh giá",
                "readiness_status": "unavailable",
                "detail": "Ngữ cảnh GxP đã chọn không hỗ trợ tạo hồ sơ tái đánh giá mới.",
                "required_permissions": required_permissions,
            }
        if production_line_id is not None:
            line = session.get(ProductionLine, production_line_id)
            if line is None or line.site_id != site_id:
                return {
                    "action_key": "create_reassessment_case",
                    "label": "Tái đánh giá",
                    "readiness_status": "unavailable",
                    "detail": "Selected ProductionLine does not belong to this site.",
                    "required_permissions": required_permissions,
                }
            if normalized_line_code is not None and normalized_line_code != line.code:
                return {
                    "action_key": "create_reassessment_case",
                    "label": "Tái đánh giá",
                    "readiness_status": "unavailable",
                    "detail": "line_code does not match the selected canonical ProductionLine.",
                    "required_permissions": required_permissions,
                }
        if not self._site_has_gxp_context(
            session,
            site_id=site_id,
            gxp_type=normalized_gxp_type,
            line_code=normalized_line_code,
            production_line_id=production_line_id,
        ):
            return {
                "action_key": "create_reassessment_case",
                "label": "Tái đánh giá",
                "readiness_status": "unavailable",
                "detail": "Ngữ cảnh cơ sở/GxP/dây chuyền đã chọn không khớp với context authoritative hiện có để tái đánh giá.",
                "required_permissions": required_permissions,
            }
        existing_case = self._find_open_context_case(
            session,
            site_id=site_id,
            gxp_type=normalized_gxp_type,
            line_code=normalized_line_code,
            production_line_id=production_line_id,
        )
        if existing_case is not None:
            return {
                "action_key": "create_reassessment_case",
                "label": "Tái đánh giá",
                "readiness_status": "conflict",
                "detail": "Đã có một hồ sơ tái đánh giá chưa kết thúc cho đúng cơ sở/GxP/dây chuyền này.",
                "required_permissions": required_permissions,
            }
        return {
            "action_key": "create_reassessment_case",
            "label": "Tái đánh giá",
            "readiness_status": "available",
            "detail": "Có thể tạo hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
            "required_permissions": required_permissions,
        }

    def _get_change_request(self, session: Session, change_request_id: str) -> ChangeRequest:
        row = session.get(ChangeRequest, change_request_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Change request not found.")
        return row

    @staticmethod
    def _serialize_change_request_mutation(
        row: ChangeRequest,
        *,
        audit_event_id: str,
        change_detail_id: str | None = None,
        change_approval_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "change_request_id": row.id,
            "row_version": row.row_version,
            "state": row.state.value,
            "audit_event_id": audit_event_id,
            "change_detail_id": change_detail_id,
            "change_approval_id": change_approval_id,
        }

    def get_create_change_request_action_readiness(
        self,
        session: Session,
        *,
        site_id: str,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        required_permissions = [CHANGE_REQUEST_EDIT_PERMISSION]
        if session.get(Site, site_id) is None:
            return {
                "action_key": "create_change_request",
                "label": "Thay đổi",
                "readiness_status": "unavailable",
                "detail": "Cơ sở không tồn tại.",
                "required_permissions": required_permissions,
            }
        if CHANGE_REQUEST_EDIT_PERMISSION not in user.permissions:
            return {
                "action_key": "create_change_request",
                "label": "Thay đổi",
                "readiness_status": "forbidden",
                "detail": "Tài khoản hiện tại không có quyền tạo yêu cầu thay đổi.",
                "required_permissions": required_permissions,
            }
        return {
            "action_key": "create_change_request",
            "label": "Thay đổi",
            "readiness_status": "available",
            "detail": "Có thể tạo yêu cầu thay đổi canonical cho cơ sở đang chọn.",
            "required_permissions": required_permissions,
        }

    def get_change_request_action_readiness(
        self,
        session: Session,
        *,
        change_request_id: str,
        user: AuthenticatedUser,
    ) -> list[dict[str, Any]]:
        row = self._get_change_request(session, change_request_id)
        actions: list[dict[str, Any]] = []
        can_edit = CHANGE_REQUEST_EDIT_PERMISSION in user.permissions
        can_approve = CHANGE_REQUEST_APPROVE_PERMISSION in user.permissions
        editable = row.state in CHANGE_REQUEST_EDITABLE_STATES
        approval_editable = row.state in CHANGE_APPROVAL_EDITABLE_STATES
        certificate_successor_permissions = [
            CHANGE_REQUEST_EDIT_PERMISSION,
            "certificate.issue",
        ]
        can_issue_certificate_successor = all(
            permission in user.permissions
            for permission in certificate_successor_permissions
        )
        actions.extend([
            {
                "action_key": "edit_change_request",
                "label": "Sửa đề nghị",
                "available": can_edit and editable,
                "reason_code": None if can_edit and editable else "missing_permission" if not can_edit else "state_not_editable",
                "required_permissions": [CHANGE_REQUEST_EDIT_PERMISSION],
                "expected_version": row.row_version,
                "target_state": None,
            },
            {
                "action_key": "add_change_detail",
                "label": "Thêm chi tiết",
                "available": can_edit and editable,
                "reason_code": None if can_edit and editable else "missing_permission" if not can_edit else "state_not_editable",
                "required_permissions": [CHANGE_REQUEST_EDIT_PERMISSION],
                "expected_version": row.row_version,
                "target_state": None,
            },
            {
                "action_key": "edit_change_detail",
                "label": "Sửa chi tiết",
                "available": can_edit and editable,
                "reason_code": None if can_edit and editable else "missing_permission" if not can_edit else "state_not_editable",
                "required_permissions": [CHANGE_REQUEST_EDIT_PERMISSION],
                "expected_version": row.row_version,
                "target_state": None,
            },
            {
                "action_key": "edit_change_approval",
                "label": "Cập nhật xử lý",
                "available": can_approve and approval_editable,
                "reason_code": None if can_approve and approval_editable else "missing_permission" if not can_approve else "state_not_editable",
                "required_permissions": [CHANGE_REQUEST_APPROVE_PERMISSION],
                "expected_version": row.row_version,
                "target_state": None,
            },
        ])
        site = self._get_site(session, row.site_id)
        certificate_source_links = list(
            session.scalars(
                select(ChangeRequestAffectedArtifact)
                .where(
                    ChangeRequestAffectedArtifact.change_request_id == row.id,
                    ChangeRequestAffectedArtifact.certificate_id.is_not(None),
                )
                .order_by(ChangeRequestAffectedArtifact.id.asc())
            )
        )
        for source_link in certificate_source_links:
            self._validate_change_request_artifact_target(
                session,
                site=site,
                certificate_id=source_link.certificate_id,
                business_eligibility_certificate_id=None,
            )
            available = editable and can_issue_certificate_successor
            actions.append(
                {
                    "action_key": f"issue_certificate_successor:{source_link.id}",
                    "label": "Tạo GCN điều chỉnh",
                    "available": available,
                    "reason_code": (
                        None
                        if available
                        else (
                            "missing_permission"
                            if not can_issue_certificate_successor
                            else "state_not_editable"
                        )
                    ),
                    "required_permissions": certificate_successor_permissions,
                    "expected_version": row.row_version,
                    "target_state": None,
                    "source_affected_artifact_id": source_link.id,
                }
            )

        business_eligibility_successor_permissions = [
            CHANGE_REQUEST_EDIT_PERMISSION,
            "certificate.issue",
        ]
        can_issue_business_eligibility_successor = all(
            permission in user.permissions
            for permission in business_eligibility_successor_permissions
        )
        business_eligibility_source_links = list(
            session.scalars(
                select(ChangeRequestAffectedArtifact)
                .where(
                    ChangeRequestAffectedArtifact.change_request_id == row.id,
                    ChangeRequestAffectedArtifact.business_eligibility_certificate_id.is_not(None),
                )
                .order_by(ChangeRequestAffectedArtifact.id.asc())
            )
        )
        for source_link in business_eligibility_source_links:
            self._validate_change_request_artifact_target(
                session,
                site=site,
                certificate_id=None,
                business_eligibility_certificate_id=source_link.business_eligibility_certificate_id,
            )
            available = editable and can_issue_business_eligibility_successor
            actions.append(
                {
                    "action_key": f"issue_business_eligibility_successor:{source_link.id}",
                    "label": "Tạo GCN ĐĐK điều chỉnh",
                    "available": available,
                    "reason_code": (
                        None
                        if available
                        else (
                            "missing_permission"
                            if not can_issue_business_eligibility_successor
                            else "state_not_editable"
                        )
                    ),
                    "required_permissions": business_eligibility_successor_permissions,
                    "expected_version": row.row_version,
                    "target_state": None,
                    "source_affected_artifact_id": source_link.id,
                }
            )

        issued_links = list(
            session.scalars(
                select(ChangeRequestIssuedArtifact)
                .where(ChangeRequestIssuedArtifact.change_request_id == row.id)
                .order_by(ChangeRequestIssuedArtifact.id.asc())
            )
        )
        for issued_link in issued_links:
            artifact_kind, artifact_id = self._validate_change_request_artifact_target(
                session,
                site=site,
                certificate_id=issued_link.certificate_id,
                business_eligibility_certificate_id=issued_link.business_eligibility_certificate_id,
            )
            if artifact_kind == "certificate":
                canonical_actions = self.get_certificate_action_readiness(
                    session,
                    certificate_id=artifact_id,
                    user=user,
                )
                edit_action = next(
                    item
                    for item in canonical_actions
                    if item["action_key"] == "edit_latest_version"
                )
                promote_action = next(
                    item
                    for item in canonical_actions
                    if item["action_key"] == "promote_current"
                )
                edit_action_key = f"edit_issued_certificate:{issued_link.id}"
                action_key = f"promote_issued_certificate:{issued_link.id}"
            else:
                canonical_actions = self.get_business_eligibility_action_readiness(
                    session,
                    business_eligibility_certificate_id=artifact_id,
                    user=user,
                )
                edit_action = next(
                    item
                    for item in canonical_actions
                    if item["action_key"] == "edit_latest_version"
                )
                promote_action = next(
                    item
                    for item in canonical_actions
                    if item["action_key"] == "promote_current"
                )
                edit_action_key = (
                    f"edit_issued_business_eligibility:{issued_link.id}"
                )
                action_key = (
                    f"promote_issued_business_eligibility:{issued_link.id}"
                )
            actions.append(
                {
                    "action_key": edit_action_key,
                    "label": edit_action["label"],
                    "available": edit_action["available"],
                    "reason_code": edit_action["reason_code"],
                    "required_permissions": edit_action["required_permissions"],
                    "expected_version": edit_action["expected_version"],
                    "target_state": None,
                    "source_affected_artifact_id": issued_link.source_affected_artifact_id,
                    "issued_artifact_link_id": issued_link.id,
                    "target_artifact_kind": artifact_kind,
                    "target_artifact_id": artifact_id,
                }
            )
            actions.append(
                {
                    "action_key": action_key,
                    "label": promote_action["label"],
                    "available": promote_action["available"],
                    "reason_code": promote_action["reason_code"],
                    "required_permissions": promote_action["required_permissions"],
                    "expected_version": promote_action["expected_version"],
                    "target_state": None,
                    "source_affected_artifact_id": issued_link.source_affected_artifact_id,
                    "issued_artifact_link_id": issued_link.id,
                    "target_artifact_kind": artifact_kind,
                    "target_artifact_id": artifact_id,
                }
            )

        for target_state in sorted(ALLOWED_CHANGE_REQUEST_TRANSITIONS.get(row.state, set()), key=lambda item: item.value):
            permission = change_request_transition_permission(target_state)
            permitted = permission in user.permissions
            actions.append({
                "action_key": f"transition_change_request:{target_state.value}",
                "label": f"Chuyển sang {target_state.value}",
                "available": permitted,
                "reason_code": None if permitted else "missing_permission",
                "required_permissions": [permission],
                "expected_version": row.row_version,
                "target_state": target_state.value,
            })
        return actions

    def _validate_change_request_artifact_target(
        self,
        session: Session,
        *,
        site: Site,
        certificate_id: str | None,
        business_eligibility_certificate_id: str | None,
    ) -> tuple[str, str]:
        if (certificate_id is None) == (business_eligibility_certificate_id is None):
            raise HTTPException(
                status_code=409,
                detail="Change request artifact link must reference exactly one canonical artifact.",
            )
        if certificate_id is not None:
            certificate = session.get(Certificate, certificate_id)
            if certificate is None or certificate.site_id != site.id:
                raise HTTPException(
                    status_code=409,
                    detail="Change request artifact references a certificate outside the owning site.",
                )
            self._certificate_line_identity(session, certificate)
            return "certificate", certificate.id

        business_eligibility = session.get(
            BusinessEligibilityCertificate,
            business_eligibility_certificate_id,
        )
        if (
            business_eligibility is None
            or business_eligibility.site_id != site.id
            or business_eligibility.company_id != site.company_id
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Change request artifact references a business eligibility "
                    "record outside the owning site/company."
                ),
            )
        return "business_eligibility_certificate", business_eligibility.id

    def _resolve_change_request_affected_artifact_snapshot(
        self,
        session: Session,
        *,
        site: Site,
    ) -> list[dict[str, str | None]]:
        affected: list[dict[str, str | None]] = []
        current_certificates = list(
            session.scalars(
                select(Certificate)
                .where(
                    Certificate.site_id == site.id,
                    Certificate.latest_flag.is_(True),
                )
                .order_by(Certificate.id.asc())
            )
        )
        for certificate in current_certificates:
            self._validate_change_request_artifact_target(
                session,
                site=site,
                certificate_id=certificate.id,
                business_eligibility_certificate_id=None,
            )
            current_context_rows = list(
                session.scalars(
                    select(Certificate)
                    .where(
                        self._certificate_context_clause(session, certificate),
                        Certificate.latest_flag.is_(True),
                    )
                    .order_by(Certificate.id.asc())
                )
            )
            if len(current_context_rows) > 1:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Change request creation is blocked because the site has "
                        "multiple current certificates for the same regulatory context."
                    ),
                )
            affected.append(
                {
                    "certificate_id": certificate.id,
                    "business_eligibility_certificate_id": None,
                }
            )

        current_business_eligibility = self._business_eligibility_current_rows(
            session,
            site_id=site.id,
        )
        if len(current_business_eligibility) > 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Change request creation is blocked because the site has "
                    "multiple current business eligibility records."
                ),
            )
        if current_business_eligibility:
            business_eligibility = current_business_eligibility[0]
            self._validate_change_request_artifact_target(
                session,
                site=site,
                certificate_id=None,
                business_eligibility_certificate_id=business_eligibility.id,
            )
            affected.append(
                {
                    "certificate_id": None,
                    "business_eligibility_certificate_id": business_eligibility.id,
                }
            )
        return affected

    @staticmethod
    def _serialize_change_request_artifact_link(
        link: ChangeRequestAffectedArtifact | ChangeRequestIssuedArtifact,
    ) -> dict[str, str | None]:
        return {
            "link_id": link.id,
            "artifact_kind": (
                "certificate"
                if link.certificate_id is not None
                else "business_eligibility_certificate"
            ),
            "artifact_id": (
                link.certificate_id
                if link.certificate_id is not None
                else link.business_eligibility_certificate_id
            ),
            "source_affected_artifact_id": (
                link.source_affected_artifact_id
                if isinstance(link, ChangeRequestIssuedArtifact)
                else None
            ),
        }

    def create_change_request(
        self,
        session: Session,
        *,
        site_id: str,
        scope_label: str | None,
        description: str | None,
        submitted_on: date | None,
        requester_name: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        site = session.get(Site, site_id)
        if site is None:
            raise HTTPException(status_code=404, detail="Site not found.")
        affected_snapshot = self._resolve_change_request_affected_artifact_snapshot(
            session,
            site=site,
        )
        actor = self._get_or_create_app_user(session, user)
        row = ChangeRequest(
            site_id=site.id,
            scope_label=scope_label,
            description=description,
            submitted_on=submitted_on,
            requester_name=requester_name,
            state=ChangeRequestState.RECEIVED,
        )
        session.add(row)
        session.flush()
        affected_links = [
            ChangeRequestAffectedArtifact(
                change_request_id=row.id,
                certificate_id=item["certificate_id"],
                business_eligibility_certificate_id=item["business_eligibility_certificate_id"],
            )
            for item in affected_snapshot
        ]
        session.add_all(affected_links)
        session.flush()
        after = {
            "site_id": row.site_id,
            "scope_label": row.scope_label,
            "description": row.description,
            "submitted_on": row.submitted_on,
            "requester_name": row.requester_name,
            "state": row.state.value,
            "affected_artifacts": [
                self._serialize_change_request_artifact_link(link)
                for link in affected_links
            ],
        }
        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_request",
            entity_id=row.id,
            action="change_request.create",
            payload=self._build_stage_payload(change_request_id=row.id, reason=reason),
            before=None,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_change_request_mutation(row, audit_event_id=audit.id)

    def issue_change_request_certificate_successor(
        self,
        session: Session,
        *,
        change_request_id: str,
        source_affected_artifact_id: str,
        expected_version: int,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_change_request(session, change_request_id)
        self._assert_expected_version(row, expected_version, label="change_request")
        if row.state not in CHANGE_REQUEST_EDITABLE_STATES:
            raise HTTPException(
                status_code=409,
                detail="Change request successors are read-only in the current state.",
            )
        source_link = session.get(
            ChangeRequestAffectedArtifact,
            source_affected_artifact_id,
        )
        if source_link is None:
            raise HTTPException(
                status_code=404,
                detail="Change request affected artifact link not found.",
            )
        if source_link.change_request_id != row.id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Affected artifact link belongs to a different change request."
                ),
            )
        if source_link.certificate_id is None:
            raise HTTPException(
                status_code=422,
                detail="Affected artifact does not reference a certificate.",
            )

        site = self._get_site(session, row.site_id)
        self._validate_change_request_artifact_target(
            session,
            site=site,
            certificate_id=source_link.certificate_id,
            business_eligibility_certificate_id=None,
        )
        source_certificate = self._get_certificate(
            session,
            source_link.certificate_id,
        )
        source_identity = self._certificate_line_identity(
            session,
            source_certificate,
        )
        source_version = self._load_latest_certificate_version(
            session,
            source_certificate.id,
        )
        source_scopes = list(
            session.scalars(
                select(CertificateScope)
                .where(
                    CertificateScope.certificate_version_id
                    == source_version.id
                )
                .order_by(
                    CertificateScope.sort_order.asc(),
                    CertificateScope.created_at.asc(),
                    CertificateScope.id.asc(),
                )
            )
        )
        scopes = [
            {
                "scope_key": scope.scope_key,
                "scope_text": scope.scope_text,
                "language_code": scope.language_code,
                "sort_order": scope.sort_order,
            }
            for scope in source_scopes
        ]

        successor, successor_version, created_scopes = (
            self._create_certificate_candidate(
                session,
                site=site,
                case=None,
                certificate_type=source_certificate.certificate_type,
                issuance_basis="administrative_no_inspection",
                production_line_id=source_identity["production_line_id"],
                line_code=source_identity["production_line_code"],
                certificate_number=None,
                issue_date=None,
                expiry_date=None,
                scopes=scopes,
                applicable_standard=source_version.applicable_standard,
                issuing_authority=source_version.issuing_authority,
            )
        )
        issued_link = ChangeRequestIssuedArtifact(
            change_request_id=row.id,
            source_affected_artifact_id=source_link.id,
            certificate_id=successor.id,
        )
        session.add(issued_link)
        row.row_version += 1
        actor = self._get_or_create_app_user(session, user)
        session.flush()

        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_request",
            entity_id=row.id,
            action="change_request.certificate_successor.issue",
            payload=self._build_stage_payload(
                change_request_id=row.id,
                source_affected_artifact_id=source_link.id,
                source_certificate_id=source_certificate.id,
                issued_artifact_link_id=issued_link.id,
                successor_certificate_id=successor.id,
                reason=reason,
            ),
            before=None,
            after={
                "source_affected_artifact_id": source_link.id,
                "source_certificate_id": source_certificate.id,
                "issued_artifact_link_id": issued_link.id,
                "successor_certificate_id": successor.id,
                "successor_latest_flag": successor.latest_flag,
                "successor_certificate_number": successor_version.certificate_number,
                "successor_issue_date": successor_version.issue_date,
                "successor_expiry_date": successor_version.expiry_date,
                "successor_applicable_standard": successor_version.applicable_standard,
                "successor_issuing_authority": successor_version.issuing_authority,
                "successor_scopes": self._serialize_certificate_scopes(
                    created_scopes
                ),
            },
            reason=reason,
        )
        session.flush()
        return {
            "change_request_id": row.id,
            "row_version": row.row_version,
            "state": row.state.value,
            "source_affected_artifact_id": source_link.id,
            "issued_artifact_link_id": issued_link.id,
            "certificate_id": successor.id,
            "audit_event_id": audit.id,
        }

    def issue_change_request_business_eligibility_successor(
        self,
        session: Session,
        *,
        change_request_id: str,
        source_affected_artifact_id: str,
        expected_version: int,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_change_request(session, change_request_id)
        self._assert_expected_version(row, expected_version, label="change_request")
        if row.state not in CHANGE_REQUEST_EDITABLE_STATES:
            raise HTTPException(
                status_code=409,
                detail="Change request successors are read-only in the current state.",
            )
        source_link = session.get(
            ChangeRequestAffectedArtifact,
            source_affected_artifact_id,
        )
        if source_link is None:
            raise HTTPException(
                status_code=404,
                detail="Change request affected artifact link not found.",
            )
        if source_link.change_request_id != row.id:
            raise HTTPException(
                status_code=409,
                detail="Affected artifact link belongs to a different change request.",
            )
        if source_link.business_eligibility_certificate_id is None:
            raise HTTPException(
                status_code=422,
                detail="Affected artifact does not reference a business eligibility certificate.",
            )

        site = self._get_site(session, row.site_id)
        self._validate_change_request_artifact_target(
            session,
            site=site,
            certificate_id=None,
            business_eligibility_certificate_id=source_link.business_eligibility_certificate_id,
        )
        source_certificate = self._get_business_eligibility(
            session,
            source_link.business_eligibility_certificate_id,
        )
        source_version = self._load_latest_business_eligibility_version(
            session,
            source_certificate.id,
        )
        source_links = list(
            session.scalars(
                select(BusinessEligibilityCertificateLink)
                .where(
                    BusinessEligibilityCertificateLink.business_eligibility_version_id
                    == source_version.id
                )
                .order_by(
                    BusinessEligibilityCertificateLink.created_at.asc(),
                    BusinessEligibilityCertificateLink.id.asc(),
                )
            )
        )
        linked_certificates = [
            {
                "certificate_id": link.certificate_id,
                "link_role": link.link_role,
            }
            for link in source_links
        ]
        version_values = {
            field_name: getattr(source_version, field_name)
            for field_name in BUSINESS_ELIGIBILITY_SUCCESSOR_COPY_FIELDS
        }
        version_values["current_status_text"] = None

        successor, successor_version, created_links = (
            self._create_business_eligibility_candidate(
                session,
                site=site,
                version_values=version_values,
                linked_certificates=linked_certificates,
            )
        )
        issued_link = ChangeRequestIssuedArtifact(
            change_request_id=row.id,
            source_affected_artifact_id=source_link.id,
            business_eligibility_certificate_id=successor.id,
        )
        session.add(issued_link)
        row.row_version += 1
        actor = self._get_or_create_app_user(session, user)
        session.flush()

        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_request",
            entity_id=row.id,
            action="change_request.business_eligibility_successor.issue",
            payload=self._build_stage_payload(
                change_request_id=row.id,
                source_affected_artifact_id=source_link.id,
                source_business_eligibility_certificate_id=source_certificate.id,
                issued_artifact_link_id=issued_link.id,
                successor_business_eligibility_certificate_id=successor.id,
                reason=reason,
            ),
            before=None,
            after={
                "source_affected_artifact_id": source_link.id,
                "source_business_eligibility_certificate_id": source_certificate.id,
                "issued_artifact_link_id": issued_link.id,
                "successor_business_eligibility_certificate_id": successor.id,
                "successor_latest_flag": successor.latest_flag,
                "successor_certificate_number": successor_version.certificate_number,
                "successor_issued_on": successor_version.issued_on,
                "successor_expires_on": successor_version.expires_on,
                "successor_current_status_text": successor_version.current_status_text,
                "successor_linked_certificates": self._serialize_business_eligibility_links(
                    created_links
                ),
            },
            reason=reason,
        )
        session.flush()
        return {
            "change_request_id": row.id,
            "row_version": row.row_version,
            "state": row.state.value,
            "source_affected_artifact_id": source_link.id,
            "issued_artifact_link_id": issued_link.id,
            "business_eligibility_certificate_id": successor.id,
            "audit_event_id": audit.id,
        }

    def update_change_request(
        self,
        session: Session,
        *,
        change_request_id: str,
        expected_version: int,
        scope_label: str | None,
        description: str | None,
        submitted_on: date | None,
        requester_name: str | None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        row = self._get_change_request(session, change_request_id)
        self._assert_expected_version(row, expected_version, label="change_request")
        if row.state not in CHANGE_REQUEST_EDITABLE_STATES:
            raise HTTPException(status_code=409, detail="Change request header is read-only in the current state.")
        provided = self._provided_fields(fields_set, {"scope_label", "description", "submitted_on", "requester_name"})
        before = {name: getattr(row, name) for name in ("scope_label", "description", "submitted_on", "requester_name")}
        self._assign_provided(row, {
            "scope_label": scope_label,
            "description": description,
            "submitted_on": submitted_on,
            "requester_name": requester_name,
        }, provided)
        actor = self._get_or_create_app_user(session, user)
        session.flush()
        after = {name: getattr(row, name) for name in ("scope_label", "description", "submitted_on", "requester_name")}
        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_request",
            entity_id=row.id,
            action="change_request.update",
            payload=self._build_stage_payload(change_request_id=row.id, reason=reason),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_change_request_mutation(row, audit_event_id=audit.id)

    def create_change_request_detail(
        self,
        session: Session,
        *,
        change_request_id: str,
        expected_version: int,
        classification_id: int | None,
        classification_label: str | None,
        approval_status: str | None,
        old_value: str | None,
        new_value: str | None,
        note: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_change_request(session, change_request_id)
        self._assert_expected_version(row, expected_version, label="change_request")
        if row.state not in CHANGE_REQUEST_EDITABLE_STATES:
            raise HTTPException(status_code=409, detail="Change request details are read-only in the current state.")
        detail = ChangeRequestDetail(
            change_request_id=row.id,
            classification_id=classification_id,
            classification_label=classification_label,
            approval_status=approval_status,
            old_value=old_value,
            new_value=new_value,
            note=note,
        )
        session.add(detail)
        session.flush()
        row.row_version += 1
        actor = self._get_or_create_app_user(session, user)
        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_request_detail",
            entity_id=detail.id,
            action="change_request_detail.create",
            payload=self._build_stage_payload(change_request_id=row.id, change_detail_id=detail.id, reason=reason),
            before=None,
            after={
                "classification_id": detail.classification_id,
                "classification_label": detail.classification_label,
                "approval_status": detail.approval_status,
                "old_value": detail.old_value,
                "new_value": detail.new_value,
                "note": detail.note,
            },
            reason=reason,
        )
        session.flush()
        return self._serialize_change_request_mutation(row, audit_event_id=audit.id, change_detail_id=detail.id)

    def update_change_request_detail(
        self,
        session: Session,
        *,
        change_detail_id: str,
        expected_version: int,
        classification_id: int | None,
        classification_label: str | None,
        approval_status: str | None,
        old_value: str | None,
        new_value: str | None,
        note: str | None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        detail = session.get(ChangeRequestDetail, change_detail_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Change request detail not found.")
        row = self._get_change_request(session, detail.change_request_id)
        self._assert_expected_version(row, expected_version, label="change_request")
        if row.state not in CHANGE_REQUEST_EDITABLE_STATES:
            raise HTTPException(status_code=409, detail="Change request details are read-only in the current state.")
        provided = self._provided_fields(fields_set, {"classification_id", "classification_label", "approval_status", "old_value", "new_value", "note"})
        before = {name: getattr(detail, name) for name in ("classification_id", "classification_label", "approval_status", "old_value", "new_value", "note")}
        self._assign_provided(detail, {
            "classification_id": classification_id,
            "classification_label": classification_label,
            "approval_status": approval_status,
            "old_value": old_value,
            "new_value": new_value,
            "note": note,
        }, provided)
        row.row_version += 1
        actor = self._get_or_create_app_user(session, user)
        session.flush()
        after = {name: getattr(detail, name) for name in ("classification_id", "classification_label", "approval_status", "old_value", "new_value", "note")}
        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_request_detail",
            entity_id=detail.id,
            action="change_request_detail.update",
            payload=self._build_stage_payload(change_request_id=row.id, change_detail_id=detail.id, reason=reason),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_change_request_mutation(row, audit_event_id=audit.id, change_detail_id=detail.id)

    def upsert_change_approval(
        self,
        session: Session,
        *,
        change_request_id: str,
        expected_version: int,
        handled_on: date | None,
        handled_by_name: str | None,
        result_label: str | None,
        effective_on: date | None,
        approval_reference: str | None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        row = self._get_change_request(session, change_request_id)
        self._assert_expected_version(row, expected_version, label="change_request")
        if row.state not in CHANGE_APPROVAL_EDITABLE_STATES:
            raise HTTPException(status_code=409, detail="Change approval is read-only in the current state.")
        approval = session.scalar(select(ChangeApproval).where(ChangeApproval.change_request_id == row.id))
        created = approval is None
        if approval is None:
            approval = ChangeApproval(change_request_id=row.id)
            session.add(approval)
            session.flush()
        provided = self._provided_fields(fields_set, {"handled_on", "handled_by_name", "result_label", "effective_on", "approval_reference"})
        before = None if created else {name: getattr(approval, name) for name in ("handled_on", "handled_by_name", "result_label", "effective_on", "approval_reference")}
        self._assign_provided(approval, {
            "handled_on": handled_on,
            "handled_by_name": handled_by_name,
            "result_label": result_label,
            "effective_on": effective_on,
            "approval_reference": approval_reference,
        }, provided)
        row.row_version += 1
        actor = self._get_or_create_app_user(session, user)
        session.flush()
        after = {name: getattr(approval, name) for name in ("handled_on", "handled_by_name", "result_label", "effective_on", "approval_reference")}
        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_approval",
            entity_id=approval.id,
            action="change_approval.create" if created else "change_approval.update",
            payload=self._build_stage_payload(change_request_id=row.id, change_approval_id=approval.id, reason=reason),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_change_request_mutation(row, audit_event_id=audit.id, change_approval_id=approval.id)

    def transition_change_request(
        self,
        session: Session,
        *,
        change_request_id: str,
        target_state: str,
        expected_version: int,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_change_request(session, change_request_id)
        self._assert_expected_version(row, expected_version, label="change_request")
        try:
            parsed_target = ChangeRequestState(target_state)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Unsupported change request state: {target_state}") from exc
        transition_reason = change_request_transition_eligibility_reason(current_state=row.state, target_state=parsed_target)
        if transition_reason == "already_in_target_state":
            raise HTTPException(status_code=409, detail="Change request is already in the requested state.")
        if transition_reason is not None:
            raise HTTPException(status_code=409, detail=f"Transition from {row.state.value} to {parsed_target.value} is not allowed.")
        previous = row.state
        row.state = parsed_target
        actor = self._get_or_create_app_user(session, user)
        session.flush()
        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="change_request",
            entity_id=row.id,
            action="change_request.transition",
            payload=self._build_stage_payload(
                change_request_id=row.id,
                previous_state=previous.value,
                target_state=parsed_target.value,
                reason=reason,
            ),
            before={"state": previous.value},
            after={"state": parsed_target.value},
            reason=reason,
        )
        session.flush()
        return self._serialize_change_request_mutation(row, audit_event_id=audit.id)

    def _serialize_capa_cycle(self, row: CapaCycle, *, audit_event_id: str | None = None) -> dict[str, Any]:
        return {
            "capa_cycle_id": row.id,
            "case_id": row.case_id,
            "row_version": row.row_version,
            "round_no": row.round_no,
            "requested_on": row.requested_on,
            "incoming_reference": row.incoming_reference,
            "submitted_on": row.submitted_on,
            "assessed_on": row.assessed_on,
            "assessor_user_id": row.assessor_user_id,
            "assessor_name": row.assessor_name,
            "result": row.result,
            "status": row.status,
            "notes": row.notes,
            "audit_event_id": audit_event_id,
        }

    def _list_case_capa_cycles(self, session: Session, case_id: str) -> list[CapaCycle]:
        return list(
            session.scalars(
                select(CapaCycle)
                .where(CapaCycle.case_id == case_id)
                .order_by(CapaCycle.round_no.asc(), CapaCycle.created_at.asc())
            )
        )

    def _latest_case_capa_cycle(self, session: Session, case_id: str) -> CapaCycle | None:
        return session.scalars(
            select(CapaCycle)
            .where(CapaCycle.case_id == case_id)
            .order_by(CapaCycle.round_no.desc(), CapaCycle.created_at.desc())
        ).first()

    def _next_capa_round_no(self, session: Session, case_id: str) -> int:
        latest = self._latest_case_capa_cycle(session, case_id)
        return 1 if latest is None else latest.round_no + 1

    def _assert_case_allows_capa_request(self, row: Case) -> None:
        if row.state != CaseState.INSPECTION_COMPLETED:
            raise HTTPException(
                status_code=409,
                detail="CAPA cycles can only be requested while the case remains in inspection_completed.",
            )

    def _assert_case_has_no_open_capa_cycle(self, session: Session, case_id: str) -> None:
        latest = self._latest_case_capa_cycle(session, case_id)
        if latest is None:
            return
        if latest.status not in {CAPA_REJECTED_STATUS}:
            raise HTTPException(
                status_code=409,
                detail="A new CAPA cycle cannot be created while the latest cycle is still open or already accepted.",
            )

    def _assert_case_can_advance_without_pending_capa(self, session: Session, case_id: str) -> None:
        case = self._get_case(session, case_id)
        self._assert_case_certificate_eligibility(
            session,
            case=case,
            allow_states={CaseState.INSPECTION_COMPLETED},
            blocked_detail="Case cannot advance to awaiting_certificate_decision while CAPA remains required or unaccepted.",
        )

    def _assert_latest_capa_cycle(self, session: Session, row: CapaCycle) -> None:
        latest = self._latest_case_capa_cycle(session, row.case_id)
        if latest is None or latest.id != row.id:
            raise HTTPException(status_code=409, detail="Only the latest CAPA cycle can be changed; earlier cycles are historical.")

    def transition_case(
        self,
        session: Session,
        *,
        case_id: str,
        target_state: str,
        expected_version: int | None = None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, str | None]:
        row = self._get_case(session, case_id)
        self._assert_expected_version(row, expected_version, label="case")
        try:
            parsed_target_state = CaseState(target_state)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Unsupported case state: {target_state}") from exc

        previous_state = row.state
        if parsed_target_state == previous_state:
            raise HTTPException(status_code=409, detail="Case is already in the requested state.")

        latest = self._latest_case_capa_cycle(session, row.id)
        transition_reason = case_transition_eligibility_reason(
            current_state=previous_state,
            target_state=parsed_target_state,
            latest_capa_status=None if latest is None else latest.status,
        )
        if transition_reason == "transition_not_allowed":
            raise HTTPException(status_code=409, detail=f"Transition from {previous_state.value} to {parsed_target_state.value} is not allowed.")
        if transition_reason == "latest_capa_not_accepted":
            raise HTTPException(status_code=409, detail="Case cannot transition while CAPA remains required or unaccepted.")

        actor = self._get_or_create_app_user(session, user)
        before = {"state": previous_state.value}
        row.state = parsed_target_state
        after = {"state": parsed_target_state.value}

        # A workflow transition is an audit fact, not evidence that any
        # underlying business milestone occurred. The owning mutation writes
        # its own InspectionEvent when and only when that fact is recorded.
        inspection_event = None
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="case",
            entity_id=row.id,
            action="case.transition",
            payload={
                "previous_state": previous_state.value,
                "current_state": parsed_target_state.value,
                "reason": reason,
                "inspection_event_id": None if inspection_event is None else inspection_event.id,
            },
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()

        return {
            "case_id": row.id,
            "previous_state": previous_state.value,
            "current_state": parsed_target_state.value,
            "row_version": row.row_version,
            "audit_event_id": audit_event.id,
            "inspection_event_id": None if inspection_event is None else inspection_event.id,
        }

    def create_inspection_case(
        self,
        session: Session,
        *,
        site_id: str,
        gxp_type: str,
        line_code: str | None,
        production_line_id: str | None = None,
        applicable_standard: str | None,
        reason: str | None,
        user: AuthenticatedUser,
        source_case_id: str | None = None,
    ) -> dict[str, Any]:
        locked_site = self._lock_site(session, site_id)
        normalized_gxp_type, normalized_line_code, line = self._validate_create_inspection_case_context(
            session,
            site_id=locked_site.id,
            gxp_type=gxp_type,
            line_code=line_code,
            production_line_id=production_line_id,
        )
        normalized_inspection_type = REASSESSMENT_INSPECTION_TYPE
        normalized_applicable_standard = str(applicable_standard or "").strip() or None
        existing_case = self._find_open_context_case(
            session,
            site_id=locked_site.id,
            gxp_type=normalized_gxp_type,
            line_code=normalized_line_code,
            production_line_id=production_line_id,
        )
        if existing_case is not None:
            raise HTTPException(
                status_code=409,
                detail="An open inspection case already exists for the selected facility/GxP/line context.",
            )
        actor = self._get_or_create_app_user(session, user)
        case = Case(
            site_id=locked_site.id,
            gxp_type=normalized_gxp_type,
            production_line_id=None if line is None else line.id,
            scope_code=normalized_line_code,
            applicable_standard=normalized_applicable_standard,
            inspection_type=normalized_inspection_type,
            state=CaseState.DRAFT,
            opened_year=None,
            legacy_inspection_id=None,
            legacy_inspection_code=None,
        )
        session.add(case)
        session.flush()
        if source_case_id:
            source_case = self._get_case(session, source_case_id)
            if source_case.production_line_id != case.production_line_id:
                raise HTTPException(
                    status_code=422,
                    detail="source_case_id does not match the selected canonical ProductionLine identity.",
                )
            if case.production_line_id is None and self._normalize_line_code(source_case.scope_code) is not None:
                raise HTTPException(
                    status_code=422,
                    detail="A facility-wide reassessment cannot use a legacy-unlinked source case.",
                )
            self._copy_evaluation_scope_for_reassessment(session, source_case_id=source_case_id, target_case=case)
        after = {
            "case_id": case.id,
            "site_id": case.site_id,
            "gxp_type": case.gxp_type,
            "line_code": case.scope_code,
            "production_line_id": case.production_line_id,
            "inspection_type": case.inspection_type,
            "applicable_standard": case.applicable_standard,
            "state": case.state.value,
            "row_version": case.row_version,
            "legacy_inspection_id": case.legacy_inspection_id,
            "legacy_inspection_code": case.legacy_inspection_code,
        }
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="case",
            entity_id=case.id,
            action="case.create_reassessment_case",
            payload={
                "site_id": case.site_id,
                "gxp_type": case.gxp_type,
                "line_code": case.scope_code,
                "inspection_type": case.inspection_type,
                "applicable_standard": case.applicable_standard,
                "state": case.state.value,
                "reason": reason,
            },
            before=None,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "case_id": case.id,
            "site_id": case.site_id,
            "gxp_type": case.gxp_type,
            "line_code": case.scope_code,
            "production_line_id": case.production_line_id,
            "inspection_type": case.inspection_type,
            "applicable_standard": case.applicable_standard,
            "state": case.state.value,
            "row_version": case.row_version,
            "legacy_inspection_id": case.legacy_inspection_id,
            "legacy_inspection_code": case.legacy_inspection_code,
            "audit_event_id": audit_event.id,
        }

    def _copy_evaluation_scope_for_reassessment(self, session: Session, *, source_case_id: str, target_case: Case) -> None:
        source_case = self._get_case(session, source_case_id)
        same_line_identity = (
            source_case.production_line_id == target_case.production_line_id
            if source_case.production_line_id is not None or target_case.production_line_id is not None
            else self._normalize_line_code(source_case.scope_code) == self._normalize_line_code(target_case.scope_code)
        )
        if (
            source_case.site_id != target_case.site_id
            or source_case.gxp_type != target_case.gxp_type
            or not same_line_identity
        ):
            raise HTTPException(status_code=422, detail="Selected source case does not match the reassessment facility/GxP/line context.")
        source_scope = session.scalar(select(CaseEvaluationScope).where(CaseEvaluationScope.case_id == source_case.id))
        if source_scope is None:
            return
        copied = CaseEvaluationScope(
            case_id=target_case.id,
            taxonomy_version_id=source_scope.taxonomy_version_id,
            source_classification=source_scope.source_classification,
            raw_legacy_value=source_scope.raw_legacy_value,
            rendered_prose=source_scope.rendered_prose,
            limitation_text=source_scope.limitation_text,
        )
        session.add(copied)
        session.flush()
        source_blocks = list(session.scalars(select(CaseEvaluationScopeBlock).where(CaseEvaluationScopeBlock.case_evaluation_scope_id == source_scope.id).order_by(CaseEvaluationScopeBlock.ordinal.asc())))
        for source_block in source_blocks:
            copied_block = CaseEvaluationScopeBlock(case_evaluation_scope_id=copied.id, ordinal=source_block.ordinal, name=source_block.name, note=source_block.note, raw_block_value=source_block.raw_block_value)
            session.add(copied_block)
            session.flush()
            for source_selection in session.scalars(select(CaseEvaluationScopeSelection).where(CaseEvaluationScopeSelection.block_id == source_block.id).order_by(CaseEvaluationScopeSelection.source_order.asc())):
                session.add(CaseEvaluationScopeSelection(block_id=copied_block.id, taxonomy_node_id=source_selection.taxonomy_node_id, source_order=source_selection.source_order, custom_description=source_selection.custom_description, node_key_snapshot=source_selection.node_key_snapshot, taxonomy_description_snapshot=source_selection.taxonomy_description_snapshot))
            for source_entry in session.scalars(select(CaseEvaluationScopeUnkeyedEntry).where(CaseEvaluationScopeUnkeyedEntry.block_id == source_block.id).order_by(CaseEvaluationScopeUnkeyedEntry.source_order.asc())):
                session.add(CaseEvaluationScopeUnkeyedEntry(block_id=copied_block.id, source_order=source_entry.source_order, text=source_entry.text))
        session.flush()

    def upsert_evaluation_scope(
        self,
        session: Session,
        *,
        case_id: str,
        expected_version: int,
        limitation_text: str | None,
        blocks: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        case = self._get_case(session, case_id)
        self._assert_case_not_terminal(case, operation="evaluation-scope edit")
        scope = session.scalar(select(CaseEvaluationScope).where(CaseEvaluationScope.case_id == case.id))
        if scope is None:
            raise HTTPException(status_code=409, detail="Case has no canonical evaluation scope to edit.")
        if scope.source_classification != "STRUCTURED_VALID" or scope.taxonomy_version_id is None:
            raise HTTPException(status_code=409, detail="Historical prose-only evaluation scope is read-only.")
        if session.get(EvaluationScopeTaxonomyVersion, scope.taxonomy_version_id) is None:
            raise HTTPException(status_code=409, detail="Evaluation scope taxonomy version is no longer available.")
        self._assert_expected_version(scope, expected_version, label="evaluation scope")
        if not blocks:
            raise HTTPException(status_code=422, detail="Evaluation scope requires at least one scope block.")
        if len(blocks) > 50:
            raise HTTPException(status_code=422, detail="Evaluation scope has too many blocks.")
        if len(limitation_text or "") > 10000:
            raise HTTPException(status_code=422, detail="Evaluation scope limitation is too long.")

        existing_block_ids = list(
            session.scalars(
                select(CaseEvaluationScopeBlock.id).where(
                    CaseEvaluationScopeBlock.case_evaluation_scope_id == scope.id
                )
            )
        )
        if existing_block_ids and session.scalar(
            select(func.count())
            .select_from(CaseEvaluationScopeUnkeyedEntry)
            .where(CaseEvaluationScopeUnkeyedEntry.block_id.in_(existing_block_ids))
        ):
            raise HTTPException(
                status_code=409,
                detail="Evaluation scope has imported unkeyed entries and remains read-only until their VBA mutation contract is proven.",
            )

        taxonomy_nodes = {
            row.id: row
            for row in session.scalars(
                select(EvaluationScopeTaxonomyNode).where(
                    EvaluationScopeTaxonomyNode.taxonomy_version_id == scope.taxonomy_version_id,
                    EvaluationScopeTaxonomyNode.gxp_type == case.gxp_type,
                )
            )
        }

        def validate_ancestor_chain(node: EvaluationScopeTaxonomyNode) -> None:
            # Tree state is presentation-only. Resolve ancestry from the persisted taxonomy so a
            # forged frontend parent/child relationship cannot change the aggregate's semantics.
            current = node
            visited: set[str] = set()
            while current.parent_node_id is not None:
                if current.id in visited:
                    raise HTTPException(status_code=422, detail="Evaluation scope taxonomy contains a parent cycle.")
                visited.add(current.id)
                parent = taxonomy_nodes.get(current.parent_node_id)
                if parent is None:
                    raise HTTPException(status_code=422, detail="Selected taxonomy node has no valid ancestor in the case taxonomy.")
                current = parent
        for ordinal, block in enumerate(blocks, start=1):
            if len(str(block.get("name") or "")) > 2000 or len(str(block.get("note") or "")) > 5000:
                raise HTTPException(status_code=422, detail="Evaluation scope block name or note is too long.")
            selections = block.get("selections", [])
            if not selections:
                raise HTTPException(status_code=422, detail=f"Evaluation scope block {ordinal} requires at least one selected node.")
            seen: set[str] = set()
            for selection in selections:
                node_id = str(selection.get("taxonomy_node_id") or "")
                if node_id in seen:
                    raise HTTPException(status_code=422, detail=f"Evaluation scope block {ordinal} contains a duplicate selected node.")
                seen.add(node_id)
                node = taxonomy_nodes.get(node_id)
                if node is None:
                    raise HTTPException(status_code=422, detail="Selected taxonomy node does not belong to the case GxP taxonomy version.")
                validate_ancestor_chain(node)
                if len(str(selection.get("custom_description") or "")) > 10000:
                    raise HTTPException(status_code=422, detail="Evaluation scope custom description is too long.")

        actor = self._get_or_create_app_user(session, user)
        before = {
            "row_version": scope.row_version,
            "block_count": len(existing_block_ids),
            "selection_count": session.scalar(
                select(func.count())
                .select_from(CaseEvaluationScopeSelection)
                .where(CaseEvaluationScopeSelection.block_id.in_(existing_block_ids))
            ) if existing_block_ids else 0,
        }
        if existing_block_ids:
            session.execute(delete(CaseEvaluationScopeSelection).where(CaseEvaluationScopeSelection.block_id.in_(existing_block_ids)))
            session.execute(delete(CaseEvaluationScopeBlock).where(CaseEvaluationScopeBlock.id.in_(existing_block_ids)))
        scope.limitation_text = str(limitation_text) if limitation_text is not None else None
        # VersionedMixin protects aggregate replacement; force a new version even when only children changed.
        scope.row_version += 1
        session.flush()
        selection_count = 0
        for ordinal, block_payload in enumerate(blocks, start=1):
            block = CaseEvaluationScopeBlock(
                case_evaluation_scope_id=scope.id,
                ordinal=ordinal,
                name=str(block_payload.get("name") or "") or None,
                note=str(block_payload.get("note") or "") or None,
                raw_block_value=None,
            )
            session.add(block)
            session.flush()
            for source_order, selection in enumerate(block_payload["selections"], start=1):
                node = taxonomy_nodes[str(selection["taxonomy_node_id"])]
                session.add(
                    CaseEvaluationScopeSelection(
                        block_id=block.id,
                        taxonomy_node_id=node.id,
                        source_order=source_order,
                        custom_description=str(selection.get("custom_description") or ""),
                        node_key_snapshot=node.node_key,
                        taxonomy_description_snapshot=node.description,
                    )
                )
                selection_count += 1
        session.flush()
        after = {"row_version": scope.row_version, "block_count": len(blocks), "selection_count": selection_count}
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="case_evaluation_scope",
            entity_id=scope.id,
            action="case.evaluation_scope.update",
            payload={"case_id": case.id, "old_row_version": before["row_version"], "new_row_version": scope.row_version, **after},
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return {"case_id": case.id, "evaluation_scope_id": scope.id, "row_version": scope.row_version, "audit_event_id": audit_event.id}

    def list_capa_cycles(
        self,
        session: Session,
        *,
        case_id: str,
    ) -> list[dict[str, Any]]:
        self._get_case(session, case_id)
        return [self._serialize_capa_cycle(row) for row in self._list_case_capa_cycles(session, case_id)]

    def create_capa_cycle(
        self,
        session: Session,
        *,
        case_id: str,
        expected_case_version: int | None = None,
        requested_on,
        incoming_reference: str | None = None,
        notes: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
        self._assert_case_not_terminal(row, operation="CAPA create")
        self._assert_expected_version(row, expected_case_version, label="case")
        self._assert_case_allows_capa_request(row)
        self._assert_case_has_no_open_capa_cycle(session, row.id)
        actor = self._get_or_create_app_user(session, user)
        capa_cycle = CapaCycle(
            case_id=row.id,
            round_no=self._next_capa_round_no(session, row.id),
            requested_on=requested_on,
            incoming_reference=incoming_reference,
            submitted_on=None,
            assessed_on=None,
            assessor_user_id=None,
            assessor_name=None,
            result=None,
            status="requested",
            notes=notes,
        )
        session.add(capa_cycle)
        session.flush()
        after = self._serialize_capa_cycle(capa_cycle)
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="capa_cycle",
            entity_id=capa_cycle.id,
            action="capa_cycle.create",
            payload={
                "case_id": row.id,
                "round_no": capa_cycle.round_no,
                "status": capa_cycle.status,
                "reason": reason,
            },
            before=None,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_capa_cycle(capa_cycle, audit_event_id=audit_event.id)

    def update_capa_cycle(
        self,
        session: Session,
        *,
        capa_cycle_id: str,
        expected_version: int,
        requested_on,
        incoming_reference: str | None = None,
        notes: str | None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        row = self._get_capa_cycle(session, capa_cycle_id)
        case = self._get_case(session, row.case_id)
        self._assert_case_not_terminal(case, operation="CAPA update")
        self._assert_latest_capa_cycle(session, row)
        self._assert_expected_version(row, expected_version, label="capa_cycle")
        if row.status not in {"requested", CAPA_REJECTED_STATUS}:
            raise HTTPException(
                status_code=409,
                detail="CAPA cycle can only be updated while requested or rejected.",
            )
        actor = self._get_or_create_app_user(session, user)
        provided = self._provided_fields(fields_set, {"requested_on", "incoming_reference", "notes"})
        before = self._snapshot_fields(row, ["requested_on", "incoming_reference", "notes", "status"])
        self._assign_provided(
            row,
            {"requested_on": requested_on, "incoming_reference": incoming_reference, "notes": notes},
            provided,
        )
        after = self._snapshot_fields(row, ["requested_on", "incoming_reference", "notes", "status"])
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="capa_cycle",
            entity_id=row.id,
            action="capa_cycle.update",
            payload={"reason": reason},
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_capa_cycle(row, audit_event_id=audit_event.id)

    def submit_capa_cycle(
        self,
        session: Session,
        *,
        capa_cycle_id: str,
        expected_version: int,
        submitted_on,
        notes: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_capa_cycle(session, capa_cycle_id)
        case = self._get_case(session, row.case_id)
        self._assert_case_not_terminal(case, operation="CAPA submit")
        self._assert_latest_capa_cycle(session, row)
        self._assert_expected_version(row, expected_version, label="capa_cycle")
        if row.status not in {"requested", CAPA_REJECTED_STATUS}:
            raise HTTPException(status_code=409, detail="CAPA cycle cannot be submitted from its current status.")
        actor = self._get_or_create_app_user(session, user)
        before = self._snapshot_fields(row, ["submitted_on", "status", "notes"])
        row.submitted_on = submitted_on
        row.notes = notes
        row.status = "submitted"
        after = self._snapshot_fields(row, ["submitted_on", "status", "notes"])
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="capa_cycle",
            entity_id=row.id,
            action="capa_cycle.submit",
            payload={"reason": reason},
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_capa_cycle(row, audit_event_id=audit_event.id)

    def assess_capa_cycle(
        self,
        session: Session,
        *,
        capa_cycle_id: str,
        expected_version: int,
        assessed_on,
        assessor_name: str | None,
        result: str,
        notes: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_capa_cycle(session, capa_cycle_id)
        case = self._get_case(session, row.case_id)
        self._assert_case_not_terminal(case, operation="CAPA assess")
        self._assert_latest_capa_cycle(session, row)
        self._assert_expected_version(row, expected_version, label="capa_cycle")
        normalized_result = (result or "").strip().lower()
        if normalized_result not in {CAPA_ACCEPTED_STATUS, CAPA_REJECTED_STATUS}:
            raise HTTPException(status_code=422, detail="CAPA assessment result must be accepted or rejected.")
        if row.status != "submitted":
            raise HTTPException(status_code=409, detail="Only submitted CAPA cycles can be assessed.")
        actor = self._get_or_create_app_user(session, user)
        resolved_assessor_name = actor.display_name or actor.username
        before = self._snapshot_fields(row, ["assessed_on", "assessor_user_id", "assessor_name", "result", "status", "notes"])
        row.assessed_on = assessed_on
        row.assessor_user_id = actor.id
        row.assessor_name = resolved_assessor_name
        row.result = normalized_result
        row.status = normalized_result
        row.notes = notes
        after = self._snapshot_fields(row, ["assessed_on", "assessor_user_id", "assessor_name", "result", "status", "notes"])
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="capa_cycle",
            entity_id=row.id,
            action="capa_cycle.assess",
            payload={
                "reason": reason,
                "assessor_name_input": assessor_name,
                "assessor_name_resolved": resolved_assessor_name,
                "assessor_user_id": actor.id,
            },
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_capa_cycle(row, audit_event_id=audit_event.id)

    def upsert_case_application(
        self,
        session: Session,
        *,
        case_id: str,
        expected_version: int | None = None,
        submitted_on,
        dossier_code: str | None,
        dossier_reference: str | None,
        applicant_name: str | None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        provided = self._provided_fields(
            fields_set,
            {"submitted_on", "dossier_code", "applicant_name"},
        )
        if (fields_set is not None and "dossier_reference" in provided) or (
            fields_set is None and dossier_reference is not None
        ):
            raise HTTPException(status_code=422, detail="dossier_reference is a read-only compatibility field.")
        row = self._get_case(session, case_id)
        self._assert_case_not_terminal(row, operation="application update")
        actor = self._get_or_create_app_user(session, user)
        stage = session.scalars(select(CaseApplication).where(CaseApplication.case_id == row.id)).first()
        if stage is None:
            stage = CaseApplication(case_id=row.id)
            session.add(stage)
            session.flush()
        self._assert_expected_version(stage, expected_version, label="case_application")
        before = self._snapshot_fields(
            stage,
            ["submitted_on", "dossier_code", "dossier_reference", "applicant_name"],
        )
        self._assign_provided(
            stage,
            {
                "submitted_on": submitted_on,
                "dossier_code": dossier_code,
                "applicant_name": applicant_name,
            },
            provided,
        )
        after = self._snapshot_fields(
            stage,
            ["submitted_on", "dossier_code", "dossier_reference", "applicant_name"],
        )
        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=(
                InspectionEventType.APPLICATION_SUBMITTED
                if "submitted_on" in provided and before["submitted_on"] is None and stage.submitted_on is not None
                else None
            ),
            payload=self._build_stage_payload(
                stage="case_application",
                submitted_on=None if submitted_on is None else submitted_on.isoformat(),
                dossier_code=dossier_code,
                applicant_name=applicant_name,
                reason=reason,
            ),
        )
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="case_application",
            entity_id=row.id,
            action="case_application.upsert",
            payload=self._build_stage_payload(
                submitted_on=None if submitted_on is None else submitted_on.isoformat(),
                dossier_code=dossier_code,
                dossier_reference=dossier_reference,
                applicant_name=applicant_name,
                reason=reason,
                inspection_event_id=None if inspection_event is None else inspection_event.id,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "case_id": row.id,
            "row_version": stage.row_version,
            "submitted_on": stage.submitted_on,
            "dossier_code": stage.dossier_code,
            "dossier_reference": stage.dossier_reference,
            "applicant_name": stage.applicant_name,
            "audit_event_id": audit_event.id,
            "inspection_event_id": None if inspection_event is None else inspection_event.id,
        }

    def upsert_case_assessment(
        self,
        session: Session,
        *,
        case_id: str,
        expected_version: int | None = None,
        assessed_on,
        assessor_name: str | None,
        assessment_result: str | None,
        notes: str | None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        provided = self._provided_fields(fields_set, {"assessed_on", "assessor_name", "assessment_result", "notes"})
        row = self._get_case(session, case_id)
        self._assert_case_not_terminal(row, operation="assessment update")
        actor = self._get_or_create_app_user(session, user)
        stage = session.scalars(select(CaseAssessment).where(CaseAssessment.case_id == row.id)).first()
        if stage is None:
            stage = CaseAssessment(case_id=row.id)
            session.add(stage)
            session.flush()
        self._assert_expected_version(stage, expected_version, label="case_assessment")
        before = self._snapshot_fields(
            stage,
            ["assessed_on", "assessor_name", "assessment_result", "notes"],
        )
        self._assign_provided(
            stage,
            {
                "assessed_on": assessed_on,
                "assessor_name": assessor_name,
                "assessment_result": assessment_result,
                "notes": notes,
            },
            provided,
        )
        after = self._snapshot_fields(
            stage,
            ["assessed_on", "assessor_name", "assessment_result", "notes"],
        )
        milestone_changed = any(
            before.get(field_name) != after.get(field_name)
            for field_name in ("assessed_on", "assessor_name", "assessment_result")
        )
        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=InspectionEventType.ASSESSMENT_COMPLETED if assessed_on is not None and milestone_changed else None,
            payload=self._build_stage_payload(
                stage="case_assessment",
                assessed_on=None if assessed_on is None else assessed_on.isoformat(),
                assessor_name=assessor_name,
                assessment_result=assessment_result,
                reason=reason,
            ),
        )
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="case_assessment",
            entity_id=row.id,
            action="case_assessment.upsert",
            payload=self._build_stage_payload(
                assessed_on=None if assessed_on is None else assessed_on.isoformat(),
                assessor_name=assessor_name,
                assessment_result=assessment_result,
                notes=notes,
                reason=reason,
                inspection_event_id=None if inspection_event is None else inspection_event.id,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "case_id": row.id,
            "row_version": stage.row_version,
            "assessed_on": stage.assessed_on,
            "assessor_name": stage.assessor_name,
            "assessment_result": stage.assessment_result,
            "notes": stage.notes,
            "audit_event_id": audit_event.id,
            "inspection_event_id": None if inspection_event is None else inspection_event.id,
        }

    def upsert_inspection_plan(
        self,
        session: Session,
        *,
        case_id: str,
        expected_version: int | None = None,
        plan_start_on,
        plan_end_on,
        planning_sheet_name: str | None,
        decision_document_hint: str | None,
        decision_reference: str | None = None,
        decision_date: date | None = None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        provided = self._provided_fields(
            fields_set,
            {"plan_start_on", "plan_end_on", "planning_sheet_name", "decision_document_hint", "decision_reference", "decision_date"},
        )
        if (fields_set is not None and "decision_document_hint" in provided) or (
            fields_set is None and decision_document_hint is not None
        ):
            raise HTTPException(status_code=422, detail="decision_document_hint is a read-only compatibility field.")
        row = self._get_case(session, case_id)
        self._assert_case_not_terminal(row, operation="inspection plan update")
        actor = self._get_or_create_app_user(session, user)
        stage = session.scalars(select(InspectionPlan).where(InspectionPlan.case_id == row.id)).first()
        if stage is None:
            stage = InspectionPlan(case_id=row.id)
            session.add(stage)
            session.flush()
        self._assert_expected_version(stage, expected_version, label="inspection_plan")
        before = self._snapshot_fields(
            stage,
            ["plan_start_on", "plan_end_on", "planning_sheet_name", "decision_reference", "decision_date"],
        )
        self._assign_provided(
            stage,
            {
                "plan_start_on": plan_start_on,
                "plan_end_on": plan_end_on,
                "planning_sheet_name": planning_sheet_name,
                "decision_reference": decision_reference,
                "decision_date": decision_date,
            },
            provided,
        )
        after = self._snapshot_fields(
            stage,
            ["plan_start_on", "plan_end_on", "planning_sheet_name", "decision_reference", "decision_date"],
        )
        has_stage_changes = before != after
        plan_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=InspectionEventType.PLAN_CREATED
            if (
                (before["plan_start_on"] is None and before["plan_end_on"] is None)
                and (stage.plan_start_on is not None or stage.plan_end_on is not None)
            )
            else None,
            payload=self._build_stage_payload(
                stage="inspection_plan",
                plan_start_on=None if plan_start_on is None else plan_start_on.isoformat(),
                plan_end_on=None if plan_end_on is None else plan_end_on.isoformat(),
                planning_sheet_name=planning_sheet_name,
                decision_reference=decision_reference,
                decision_date=None if decision_date is None else decision_date.isoformat(),
                reason=reason,
            ),
        )
        decision_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=InspectionEventType.DECISION_ISSUED
            if (
                before["decision_reference"] is None
                and before["decision_date"] is None
                and (stage.decision_reference is not None or stage.decision_date is not None)
            )
            else None,
            payload=self._build_stage_payload(
                stage="inspection_decision",
                decision_reference=stage.decision_reference,
                decision_date=None if stage.decision_date is None else stage.decision_date.isoformat(),
                reason=reason,
            ),
        )
        inspection_event = decision_event or plan_event
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="inspection_plan",
            entity_id=row.id,
            action="inspection_plan.upsert",
            payload=self._build_stage_payload(
                plan_start_on=None if plan_start_on is None else plan_start_on.isoformat(),
                plan_end_on=None if plan_end_on is None else plan_end_on.isoformat(),
                planning_sheet_name=planning_sheet_name,
                decision_reference=decision_reference,
                decision_date=None if decision_date is None else decision_date.isoformat(),
                reason=reason,
                inspection_event_id=None if inspection_event is None else inspection_event.id,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "case_id": row.id,
            "row_version": stage.row_version,
            "plan_start_on": stage.plan_start_on,
            "plan_end_on": stage.plan_end_on,
            "planning_sheet_name": stage.planning_sheet_name,
            "decision_document_hint": stage.decision_document_hint,
            "decision_reference": stage.decision_reference,
            "decision_date": stage.decision_date,
            "audit_event_id": audit_event.id,
            "inspection_event_id": None if inspection_event is None else inspection_event.id,
        }

    def upsert_inspection_outcome(
        self,
        session: Session,
        *,
        case_id: str,
        expected_version: int | None = None,
        inspected_on,
        inspected_to_on,
        decision_reference: str | None,
        bbkt_reference: str | None,
        outcome_result: str | None,
        minutes_recorded_on: date | None = None,
        minutes_recorded_time=None,
        compliance_due_on: date | None = None,
        reason: str | None,
        user: AuthenticatedUser,
        fields_set: set[str] | None = None,
    ) -> dict[str, Any]:
        provided = self._provided_fields(
            fields_set,
            {
                "inspected_on", "inspected_to_on", "decision_reference", "bbkt_reference",
                "outcome_result", "minutes_recorded_on", "minutes_recorded_time", "compliance_due_on",
            },
        )
        if (fields_set is not None and {"decision_reference", "bbkt_reference"} & provided) or (
            fields_set is None and (decision_reference is not None or bbkt_reference is not None)
        ):
            raise HTTPException(status_code=422, detail="decision_reference and bbkt_reference are read-only compatibility fields.")
        row = self._get_case(session, case_id)
        self._assert_case_not_terminal(row, operation="inspection outcome update")
        if "inspected_to_on" in provided and "inspected_on" in provided and inspected_on is None and inspected_to_on is not None:
            raise HTTPException(status_code=422, detail="Inspection outcome end date requires a start date.")
        if "inspected_on" in provided and "inspected_to_on" in provided and inspected_on is not None and inspected_to_on is not None and inspected_on > inspected_to_on:
            raise HTTPException(status_code=422, detail="Inspection outcome start date must not be after its end date.")
        actor = self._get_or_create_app_user(session, user)
        stage = session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id == row.id)).first()
        if stage is None:
            # This compatibility endpoint does not own a zero-segment source
            # meaning, so a metadata-only create remains unclassified.
            stage = InspectionOutcome(case_id=row.id, inspection_period_state=None)
            session.add(stage)
            session.flush()
        self._assert_expected_version(stage, expected_version, label="inspection_outcome")
        has_compatibility_period = "inspected_on" in provided or "inspected_to_on" in provided
        effective_start = inspected_on if "inspected_on" in provided else stage.inspected_on
        effective_end = inspected_to_on if "inspected_to_on" in provided else stage.inspected_to_on
        if effective_start is None and effective_end is not None:
            raise HTTPException(status_code=422, detail="Inspection outcome end date requires a start date.")
        if effective_start is not None and effective_end is not None and effective_start > effective_end:
            raise HTTPException(status_code=422, detail="Inspection outcome start date must not be after its end date.")
        canonical_end = effective_end or effective_start
        if has_compatibility_period and stage.inspection_period_state not in {None, "KNOWN"}:
            raise HTTPException(
                status_code=409,
                detail="Inspection outcome has a source-owned non-KNOWN period state and requires a state-aware mutation contract.",
            )
        period_segments = list(
            session.scalars(
                select(InspectionPeriodSegment)
                .where(InspectionPeriodSegment.inspection_outcome_id == stage.id)
                .order_by(InspectionPeriodSegment.ordinal)
            )
        )
        if has_compatibility_period and len(period_segments) > 1:
            raise HTTPException(
                status_code=409,
                detail="Inspection outcome has multiple canonical period segments and cannot be changed by the compatibility endpoint.",
            )
        if has_compatibility_period and len(period_segments) == 1 and period_segments[0].ordinal != 1:
            raise HTTPException(
                status_code=409,
                detail="Inspection outcome has an invalid canonical single-segment ordinal.",
            )
        before = self._snapshot_fields(
            stage,
            ["inspected_on", "inspected_to_on", "inspection_period_state", "outcome_result", "minutes_recorded_on", "minutes_recorded_time", "compliance_due_on"],
        )
        if has_compatibility_period:
            # The compatibility endpoint owns exactly one canonical segment.
            # A missing end date is the proven one-day representation.
            if effective_start is None:
                for segment in period_segments:
                    session.delete(segment)
                stage.inspected_on = None
                stage.inspected_to_on = None
                stage.inspection_period_state = "KNOWN"
            elif not period_segments:
                session.add(
                    InspectionPeriodSegment(
                        inspection_outcome_id=stage.id,
                        ordinal=1,
                        started_on=effective_start,
                        ended_on=canonical_end,
                    )
                )
            else:
                period_segments[0].started_on = effective_start
                period_segments[0].ended_on = canonical_end
            stage.inspected_on = effective_start
            stage.inspected_to_on = canonical_end
            stage.inspection_period_state = "KNOWN"
        self._assign_provided(
            stage,
            {
                "outcome_result": outcome_result,
                "minutes_recorded_on": minutes_recorded_on,
                "minutes_recorded_time": minutes_recorded_time,
                "compliance_due_on": compliance_due_on,
            },
            provided,
        )
        if stage.minutes_recorded_time is not None and stage.minutes_recorded_on is None:
            raise HTTPException(status_code=422, detail="Minutes time requires a minutes date.")
        after = self._snapshot_fields(
            stage,
            ["inspected_on", "inspected_to_on", "inspection_period_state", "outcome_result", "minutes_recorded_on", "minutes_recorded_time", "compliance_due_on"],
        )
        has_stage_changes = before != after
        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=(
                InspectionEventType.OUTCOME_RECORDED
                if "outcome_result" in provided and before["outcome_result"] is None and stage.outcome_result is not None
                else None
            ),
            payload=self._build_stage_payload(
                stage="inspection_outcome",
                inspected_on=None if stage.inspected_on is None else stage.inspected_on.isoformat(),
                inspected_to_on=None if canonical_end is None else canonical_end.isoformat(),
                outcome_result=stage.outcome_result,
                minutes_recorded_on=None if stage.minutes_recorded_on is None else stage.minutes_recorded_on.isoformat(),
                minutes_recorded_time=None if stage.minutes_recorded_time is None else stage.minutes_recorded_time.isoformat(),
                compliance_due_on=None if stage.compliance_due_on is None else stage.compliance_due_on.isoformat(),
                reason=reason,
            ),
        )
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="inspection_outcome",
            entity_id=row.id,
            action="inspection_outcome.upsert",
            payload=self._build_stage_payload(
                inspected_on=None if inspected_on is None else inspected_on.isoformat(),
                inspected_to_on=None if canonical_end is None else canonical_end.isoformat(),
                outcome_result=outcome_result,
                minutes_recorded_on=None if minutes_recorded_on is None else minutes_recorded_on.isoformat(),
                minutes_recorded_time=None if minutes_recorded_time is None else minutes_recorded_time.isoformat(),
                compliance_due_on=None if compliance_due_on is None else compliance_due_on.isoformat(),
                reason=reason,
                inspection_event_id=None if inspection_event is None else inspection_event.id,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "case_id": row.id,
            "row_version": stage.row_version,
            "inspected_on": stage.inspected_on,
            "inspected_to_on": stage.inspected_to_on,
            "inspection_period_state": stage.inspection_period_state,
            "decision_reference": stage.decision_reference,
            "bbkt_reference": stage.bbkt_reference,
            "outcome_result": stage.outcome_result,
            "final_evaluation": stage.final_evaluation,
            "minutes_recorded_on": stage.minutes_recorded_on,
            "minutes_recorded_time": stage.minutes_recorded_time,
            "compliance_due_on": stage.compliance_due_on,
            "audit_event_id": audit_event.id,
            "inspection_event_id": None if inspection_event is None else inspection_event.id,
        }

    def upsert_inspection_period_segments(
        self,
        session: Session,
        *,
        case_id: str,
        expected_version: int | None,
        segments: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        """Replace an explicitly user-entered, ordered actual visit sequence."""
        case = self._get_case(session, case_id)
        self._assert_case_not_terminal(case, operation="inspection period update")
        outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case.id))
        readiness = inspection_period_edit_readiness(outcome=outcome, terminal_case=False)
        if not readiness["available"]:
            raise HTTPException(
                status_code=409,
                detail="Inspection outcome period is source-owned or unclassified and cannot be replaced by runtime segments.",
            )
        if outcome is None:
            if expected_version is not None:
                raise HTTPException(status_code=409, detail="Inspection period initialization requires a null expected_version.")
            outcome = InspectionOutcome(case_id=case.id, inspection_period_state="KNOWN")
            session.add(outcome)
            session.flush()
        else:
            if expected_version is None:
                raise HTTPException(status_code=409, detail="Existing inspection outcome requires an expected_version.")
            self._assert_expected_version(outcome, expected_version, label="inspection_outcome")
        normalized = sorted(segments, key=lambda item: item["ordinal"])
        if not normalized:
            raise HTTPException(status_code=422, detail="Inspection period requires at least one ordered segment.")
        expected_ordinals = list(range(1, len(normalized) + 1))
        actual_ordinals = [item["ordinal"] for item in normalized]
        if actual_ordinals != expected_ordinals:
            raise HTTPException(status_code=422, detail="Inspection period segments must use contiguous ordinals starting at 1.")
        for item in normalized:
            if item["started_on"] > item["ended_on"]:
                raise HTTPException(status_code=422, detail="Inspection period segment start date must not be after end date.")
        existing = list(session.scalars(
            select(InspectionPeriodSegment)
            .where(InspectionPeriodSegment.inspection_outcome_id == outcome.id)
            .order_by(InspectionPeriodSegment.ordinal)
        ))
        before = {
            "inspection_period_state": outcome.inspection_period_state,
            "segments": [
                {"ordinal": item.ordinal, "started_on": item.started_on, "ended_on": item.ended_on}
                for item in existing
            ],
        }
        for item in existing:
            session.delete(item)
        for item in normalized:
            session.add(InspectionPeriodSegment(
                inspection_outcome_id=outcome.id,
                ordinal=item["ordinal"],
                started_on=item["started_on"],
                ended_on=item["ended_on"],
            ))
        if len(normalized) == 1:
            outcome.inspected_on = normalized[0]["started_on"]
            outcome.inspected_to_on = normalized[0]["ended_on"]
        else:
            # A multi-segment visit must never be represented as a fabricated envelope.
            outcome.inspected_on = None
            outcome.inspected_to_on = None
        outcome.inspection_period_state = "KNOWN"
        outcome.row_version += 1
        actor = self._get_or_create_app_user(session, user)
        session.flush()
        after = {
            "inspection_period_state": outcome.inspection_period_state,
            "segments": [
                {"ordinal": item.ordinal, "started_on": item.started_on, "ended_on": item.ended_on}
                for item in session.scalars(
                    select(InspectionPeriodSegment)
                    .where(InspectionPeriodSegment.inspection_outcome_id == outcome.id)
                    .order_by(InspectionPeriodSegment.ordinal)
                )
            ],
        }
        inspection_event = self._write_inspection_event(
            session,
            case_id=case.id,
            event_type=InspectionEventType.INSPECTION_EXECUTED if not before["segments"] else None,
            payload={"stage": "inspection_period", "segments": after["segments"], "reason": reason},
        )
        audit = self._write_audit_event(
            session,
            actor=actor,
            entity_type="inspection_outcome",
            entity_id=outcome.id,
            action="inspection_period_segments.replace",
            payload={"reason": reason, "inspection_event_id": None if inspection_event is None else inspection_event.id},
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return self._serialize_inspection_outcome(
            outcome,
            audit_event_id=audit.id,
            inspection_event_id=None if inspection_event is None else inspection_event.id,
        )

    def _serialize_approval_submission(self, row: InspectionApprovalSubmission) -> dict[str, Any]:
        return {
            "approval_submission_id": row.id, "case_id": row.case_id, "row_version": row.row_version,
            "stage": row.stage, "round_no": row.round_no, "reference": row.reference,
            "submitted_on": row.submitted_on, "submitted_time": row.submitted_time,
            "completed_on": row.completed_on, "completed_time": row.completed_time,
            "pct_submission_id": row.pct_submission_id,
        }

    def _serialize_inspection_outcome(self, row: InspectionOutcome, *, audit_event_id: str | None, inspection_event_id: str | None) -> dict[str, Any]:
        return {
            "case_id": row.case_id, "row_version": row.row_version, "inspected_on": row.inspected_on,
            "inspected_to_on": row.inspected_to_on, "inspection_period_state": row.inspection_period_state,
            "decision_reference": row.decision_reference, "bbkt_reference": row.bbkt_reference,
            "outcome_result": row.outcome_result, "final_evaluation": row.final_evaluation,
            "minutes_recorded_on": row.minutes_recorded_on, "minutes_recorded_time": row.minutes_recorded_time,
            "compliance_due_on": row.compliance_due_on, "audit_event_id": audit_event_id,
            "inspection_event_id": inspection_event_id,
        }

    def finalize_inspection_outcome(self, session: Session, *, case_id: str, expected_version: int, final_evaluation: str, reason: str | None, user: AuthenticatedUser) -> dict[str, Any]:
        row = self._get_case(session, case_id)
        self._assert_case_not_terminal(row, operation="inspection final evaluation")
        stage = session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id == row.id)).first()
        if stage is None:
            raise HTTPException(status_code=422, detail="Inspection outcome must exist before final evaluation.")
        self._assert_expected_version(stage, expected_version, label="inspection_outcome")
        if stage.final_evaluation is not None:
            if stage.final_evaluation == final_evaluation:
                return self._serialize_inspection_outcome(stage, audit_event_id=None, inspection_event_id=None)
            raise HTTPException(status_code=409, detail="Inspection final evaluation is immutable once set.")
        if not str(final_evaluation).strip():
            raise HTTPException(status_code=422, detail="Inspection final evaluation is required.")
        self._assert_latest_capa_accepted_if_present(session, row.id, blocked_detail="Latest CAPA cycle must be accepted before final evaluation.")
        before = self._snapshot_fields(stage, ["outcome_result", "final_evaluation"])
        stage.final_evaluation = final_evaluation
        actor = self._get_or_create_app_user(session, user)
        audit = self._write_audit_event(session, actor=actor, entity_type="inspection_outcome", entity_id=stage.id, action="inspection_outcome.finalize", payload=self._build_stage_payload(final_evaluation=final_evaluation, reason=reason), before=before, after=self._snapshot_fields(stage, ["outcome_result", "final_evaluation"]), reason=reason)
        session.flush()
        return self._serialize_inspection_outcome(stage, audit_event_id=audit.id, inspection_event_id=None)

    def create_approval_submission(self, session: Session, *, case_id: str, stage: str, reference: str | None, submitted_on: date | None, submitted_time, pct_submission_id: str | None, reason: str | None, user: AuthenticatedUser) -> dict[str, Any]:
        normalized_stage = str(stage or "").upper()
        if normalized_stage not in {"PCT", "CT"}:
            raise HTTPException(status_code=422, detail="Approval submission stage must be PCT or CT.")
        try:
            validate_time_requires_date(value_date=submitted_on, value_time=submitted_time, label="Approval submission")
        except InspectionContractViolation as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        row = session.scalars(select(Case).where(Case.id == case_id).with_for_update()).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        self._assert_case_not_terminal(row, operation="approval submission creation")
        if normalized_stage == "PCT" and pct_submission_id is not None:
            raise HTTPException(status_code=422, detail="PCT submission must not set pct_submission_id.")
        if normalized_stage == "CT":
            if pct_submission_id is None:
                raise HTTPException(status_code=422, detail="CT submission requires pct_submission_id.")
            parent = session.get(InspectionApprovalSubmission, pct_submission_id)
            if parent is None:
                raise HTTPException(status_code=404, detail="PCT approval submission not found.")
            try:
                validate_ct_parent(child_case_id=row.id, parent_case_id=parent.case_id, parent_stage=parent.stage, parent_completed_on=parent.completed_on)
            except InspectionContractViolation as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        rounds = list(session.scalars(select(InspectionApprovalSubmission.round_no).where(InspectionApprovalSubmission.case_id == row.id, InspectionApprovalSubmission.stage == normalized_stage)))
        round_no = 1 if not rounds else max(rounds) + 1
        submission = InspectionApprovalSubmission(case_id=row.id, stage=normalized_stage, round_no=round_no, reference=reference, submitted_on=submitted_on, submitted_time=submitted_time, pct_submission_id=pct_submission_id)
        session.add(submission)
        session.flush()
        actor = self._get_or_create_app_user(session, user)
        self._write_audit_event(session, actor=actor, entity_type="inspection_approval_submission", entity_id=submission.id, action="inspection_approval_submission.create", payload=self._serialize_approval_submission(submission), before={}, after=self._serialize_approval_submission(submission), reason=reason)
        session.flush()
        return self._serialize_approval_submission(submission)

    def complete_approval_submission(self, session: Session, *, approval_submission_id: str, expected_version: int, completed_on: date, completed_time, reason: str | None, user: AuthenticatedUser) -> dict[str, Any]:
        row = session.get(InspectionApprovalSubmission, approval_submission_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Approval submission not found.")
        self._assert_case_not_terminal(self._get_case(session, row.case_id), operation="approval submission completion")
        self._assert_expected_version(row, expected_version, label="approval_submission")
        try:
            validate_approval_completion(existing_completed_on=row.completed_on, existing_completed_time=row.completed_time, completed_on=completed_on, completed_time=completed_time)
        except InspectionContractViolation as exc:
            raise HTTPException(status_code=409 if row.completed_on is not None else 422, detail=str(exc)) from exc
        before = self._serialize_approval_submission(row)
        row.completed_on, row.completed_time = completed_on, completed_time
        actor = self._get_or_create_app_user(session, user)
        self._write_audit_event(session, actor=actor, entity_type="inspection_approval_submission", entity_id=row.id, action="inspection_approval_submission.complete", payload=self._build_stage_payload(completed_on=completed_on.isoformat(), completed_time=None if completed_time is None else completed_time.isoformat(), reason=reason), before=before, after=self._serialize_approval_submission(row), reason=reason)
        session.flush()
        return self._serialize_approval_submission(row)

    def upsert_inspection_team(
        self,
        session: Session,
        *,
        case_id: str,
        members: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
        expected_version: int | None = None,
        display_text: str | None = None,
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
        self._assert_case_not_terminal(row, operation="inspection team update")
        existing_team = session.scalar(select(InspectionTeam).where(InspectionTeam.case_id == row.id))
        existing_members = [] if existing_team is None else list(
            session.scalars(
                select(InspectionTeamMember)
                .where(InspectionTeamMember.team_id == existing_team.id)
                .order_by(InspectionTeamMember.sort_order.asc(), InspectionTeamMember.id.asc())
            )
        )
        if existing_team is not None:
            existing_identity_state = inspection_team_existing_identity_state(
                session,
                members=existing_members,
            )
            if not existing_identity_state["round_trip_safe"]:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Inspection team {existing_identity_state['blocked_reason_code']} "
                        "and cannot be replaced by normal runtime editing."
                    ),
                )
        if display_text is not None:
            raise HTTPException(status_code=422, detail="Inspection team display_text is a legacy snapshot and cannot be edited with members.")
        self._validate_team_members(members)
        self._validate_team_member_identities(session, members)
        actor = self._get_or_create_app_user(session, user)

        team = existing_team
        if team is None:
            if expected_version is not None:
                raise HTTPException(status_code=409, detail="Inspection team initialization requires a null expected_version.")
            team = InspectionTeam(case_id=row.id)
            session.add(team)
            session.flush()
        else:
            if expected_version is None:
                raise HTTPException(status_code=409, detail="Existing inspection team requires an expected_version.")
            self._assert_expected_version(team, expected_version, label="inspection_team")
        before = {
            "display_text": team.display_text,
            "members": [
                self._team_member_payload(member)
                for member in sorted(existing_members, key=lambda item: item.sort_order)
            ],
        }

        for member in existing_members:
            session.delete(member)
        session.flush()

        created_members: list[InspectionTeamMember] = []
        for item in members:
            member = InspectionTeamMember(
                team_id=team.id,
                inspector_profile_id=item.get("inspector_profile_id"),
                person_id=item.get("person_id"),
                role_code=str(item.get("role_code")),
                role_label=item.get("role_label"),
                sort_order=int(item.get("sort_order", 0)),
                identity_kind=item.get("identity_kind"),
                participant_catalog_id=item.get("participant_catalog_id"),
                # Display snapshots are owned by canonical identity/catalog,
                # never by a client-provided string.
                display_name=self._team_member_display_name(session, item),
            )
            session.add(member)
            created_members.append(member)
        # Replacing child rows does not dirty the versioned aggregate itself.
        # Advance its token so a later stale replace-all request fails closed.
        team.row_version += 1
        session.flush()
        after = {
            "display_text": team.display_text,
            "members": [
                self._team_member_payload(member)
                for member in sorted(created_members, key=lambda item: item.sort_order)
            ],
        }

        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="inspection_team",
            entity_id=team.id,
            action="inspection_team.upsert",
            payload=self._build_stage_payload(
                case_id=row.id,
                display_text=team.display_text,
                member_count=len(created_members),
                members=[
                    {
                        "id": member.id,
                        "inspector_profile_id": member.inspector_profile_id,
                        "person_id": member.person_id,
                        "role_code": member.role_code,
                        "role_label": member.role_label,
                        "sort_order": member.sort_order,
                    }
                    for member in created_members
                ],
                reason=reason,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()

        return {
            "case_id": row.id,
            "team_id": team.id,
            "row_version": team.row_version,
            "display_text": team.display_text,
            "members": [
                {
                    "id": member.id,
                    "inspector_profile_id": member.inspector_profile_id,
                    "person_id": member.person_id,
                    "role_code": member.role_code,
                    "role_label": member.role_label,
                    "sort_order": member.sort_order,
                }
                for member in sorted(created_members, key=lambda item: item.sort_order)
            ],
            "audit_event_id": audit_event.id,
        }

    def _create_certificate_candidate(
        self,
        session: Session,
        *,
        site: Site,
        case: Case | None,
        certificate_type: str,
        issuance_basis: str,
        production_line_id: str | None,
        line_code: str | None,
        certificate_number: str | None,
        issue_date,
        expiry_date,
        scopes: list[dict[str, Any]],
        applicable_standard: str | None = None,
        issuing_authority: str | None = None,
    ) -> tuple[Certificate, CertificateVersion, list[CertificateScope]]:
        certificate = Certificate(
            site_id=site.id,
            case_id=None if case is None else case.id,
            certificate_type=certificate_type,
            issuance_basis=issuance_basis,
            production_line_id=production_line_id,
            line_code=line_code,
            latest_flag=False,
            latest_legacy_certificate_id=None,
        )
        session.add(certificate)
        session.flush()

        version = CertificateVersion(
            certificate_id=certificate.id,
            version_no=1,
            issue_date=issue_date,
            expiry_date=expiry_date,
            certificate_number=certificate_number,
            applicable_standard=applicable_standard,
            issuing_authority=issuing_authority,
            is_latest_version=True,
        )
        session.add(version)
        session.flush()
        created_scopes = self._replace_certificate_scopes(
            session,
            certificate_version_id=version.id,
            scopes=scopes,
        )
        return certificate, version, created_scopes

    def issue_certificate(
        self,
        session: Session,
        *,
        site_id: str,
        case_id: str | None,
        certificate_type: str,
        issuance_basis: str,
        certificate_number: str | None,
        issue_date,
        expiry_date,
        scopes: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        site = self._get_site(session, site_id)
        case = None if case_id is None else self._get_case(session, case_id)
        self._validate_certificate_case_link(
            site_id=site.id,
            case=case,
            certificate_type=certificate_type,
            issuance_basis=issuance_basis,
        )
        if case is not None:
            self._assert_case_certificate_eligibility(
                session,
                case=case,
                allow_states={CaseState.AWAITING_CERTIFICATE_DECISION, CaseState.CERTIFIED},
                blocked_detail="Case-backed certificate issuance is blocked until the latest CAPA cycle is accepted.",
            )
        actor = self._get_or_create_app_user(session, user)

        certificate, version, created_scopes = self._create_certificate_candidate(
            session,
            site=site,
            case=case,
            certificate_type=certificate_type,
            issuance_basis=issuance_basis,
            production_line_id=None if case is None else case.production_line_id,
            line_code=None if case is None else (case.scope_code or None),
            certificate_number=certificate_number,
            issue_date=issue_date,
            expiry_date=expiry_date,
            scopes=scopes,
        )
        after = {
            "site_id": certificate.site_id,
            "case_id": certificate.case_id,
            "certificate_type": certificate.certificate_type,
            **self._certificate_line_identity(session, certificate),
            "issuance_basis": certificate.issuance_basis,
            "latest_flag": certificate.latest_flag,
            "certificate_number": version.certificate_number,
            "issue_date": self._normalize_audit_value(version.issue_date),
            "expiry_date": self._normalize_audit_value(version.expiry_date),
            "scopes": self._serialize_certificate_scopes(created_scopes),
        }
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="certificate",
            entity_id=certificate.id,
            action="certificate.issue",
            payload=self._build_stage_payload(
                site_id=site.id,
                case_id=None if case is None else case.id,
                certificate_type=certificate_type,
                issuance_basis=issuance_basis,
                latest_flag=False,
                certificate_number=certificate_number,
                issue_date=None if issue_date is None else issue_date.isoformat(),
                expiry_date=None if expiry_date is None else expiry_date.isoformat(),
                scopes=self._serialize_certificate_scopes(created_scopes),
                reason=reason,
                inspection_event_id=None,
            ),
            before=None,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "certificate_id": certificate.id,
            "row_version": certificate.row_version,
            "site_id": certificate.site_id,
            "case_id": certificate.case_id,
            "certificate_type": certificate.certificate_type,
            **self._certificate_line_identity(session, certificate),
            "issuance_basis": certificate.issuance_basis,
            "latest_flag": certificate.latest_flag,
            "latest_version_id": version.id,
            "latest_version_no": version.version_no,
            "certificate_number": version.certificate_number,
            "issue_date": version.issue_date,
            "expiry_date": version.expiry_date,
            "scopes": self._serialize_certificate_scopes(created_scopes),
            "audit_event_id": audit_event.id,
            "inspection_event_id": None,
        }

    def upsert_certificate_latest_version(
        self,
        session: Session,
        *,
        certificate_id: str,
        expected_version: int | None = None,
        certificate_number: str | None,
        issue_date,
        expiry_date,
        scopes: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        certificate = self._get_certificate(session, certificate_id)
        self._certificate_line_identity(session, certificate)
        self._assert_expected_version(certificate, expected_version, label="certificate")
        actor = self._get_or_create_app_user(session, user)
        version = self._load_latest_certificate_version(session, certificate.id)
        before = {
            "certificate_number": version.certificate_number,
            "issue_date": self._normalize_audit_value(version.issue_date),
            "expiry_date": self._normalize_audit_value(version.expiry_date),
            "scopes": self._serialize_certificate_scopes(
                list(session.scalars(select(CertificateScope).where(CertificateScope.certificate_version_id == version.id)))
            ),
        }
        version.certificate_number = certificate_number
        version.issue_date = issue_date
        version.expiry_date = expiry_date
        certificate.updated_at = datetime.now(timezone.utc)
        created_scopes = self._replace_certificate_scopes(
            session,
            certificate_version_id=version.id,
            scopes=scopes,
        )
        after = {
            "certificate_number": version.certificate_number,
            "issue_date": self._normalize_audit_value(version.issue_date),
            "expiry_date": self._normalize_audit_value(version.expiry_date),
            "scopes": self._serialize_certificate_scopes(created_scopes),
        }
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="certificate_version",
            entity_id=version.id,
            action="certificate.latest_version.upsert",
            payload=self._build_stage_payload(
                certificate_id=certificate.id,
                latest_version_no=version.version_no,
                certificate_number=certificate_number,
                issue_date=None if issue_date is None else issue_date.isoformat(),
                expiry_date=None if expiry_date is None else expiry_date.isoformat(),
                scopes=self._serialize_certificate_scopes(created_scopes),
                reason=reason,
                inspection_event_id=None,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "certificate_id": certificate.id,
            "row_version": certificate.row_version,
            "site_id": certificate.site_id,
            "case_id": certificate.case_id,
            "certificate_type": certificate.certificate_type,
            **self._certificate_line_identity(session, certificate),
            "issuance_basis": certificate.issuance_basis,
            "latest_flag": certificate.latest_flag,
            "latest_version_id": version.id,
            "latest_version_no": version.version_no,
            "certificate_number": version.certificate_number,
            "issue_date": version.issue_date,
            "expiry_date": version.expiry_date,
            "scopes": self._serialize_certificate_scopes(created_scopes),
            "audit_event_id": audit_event.id,
            "inspection_event_id": None,
        }

    def promote_certificate_current(
        self,
        session: Session,
        *,
        certificate_id: str,
        expected_version: int | None = None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        certificate = self._get_certificate(session, certificate_id)
        self._assert_expected_version(certificate, expected_version, label="certificate")
        candidate_version = self._load_latest_certificate_version(session, certificate.id)
        blocker = self._get_certificate_promotion_blocker(
            session,
            certificate=certificate,
            version=candidate_version,
        )
        if blocker is not None:
            details = {
                "case_state_not_eligible": "Current-certificate promotion is blocked until the case reaches certificate decision.",
                "latest_capa_not_accepted": "Current-certificate promotion is blocked until the latest CAPA cycle is accepted.",
                "certificate_data_incomplete": "Certificate promotion requires certificate number, issue date, and expiry date.",
                "candidate_issue_date_precedes_current": "Certificate promotion requires a candidate issue date that is not older than the current active certificate.",
            }
            raise HTTPException(status_code=409, detail=details[blocker])
        actor = self._get_or_create_app_user(session, user)
        current_peers = list(session.scalars(
            select(Certificate).where(
                self._certificate_context_clause(session, certificate),
                Certificate.latest_flag.is_(True),
            ).order_by(Certificate.id)
        ))
        for current in current_peers:
            self._certificate_line_identity(session, current)
        previous_current_id = None if not current_peers else current_peers[0].id
        before = {
            "latest_flag": certificate.latest_flag,
            "previous_current_certificate_id": previous_current_id,
        }
        for current in current_peers:
            if current.id != certificate.id:
                current.latest_flag = False
        certificate.latest_flag = True
        after = {
            "latest_flag": certificate.latest_flag,
            "previous_current_certificate_id": previous_current_id,
        }

        inspection_event = self._write_inspection_event(
            session,
            case_id=certificate.case_id,
            event_type=InspectionEventType.CERTIFICATE_ISSUED if certificate.case_id is not None else None,
            payload=self._build_stage_payload(
                certificate_id=certificate.id,
                previous_current_certificate_id=previous_current_id,
                issue_date=candidate_version.issue_date.isoformat(),
                reason=reason,
            ),
        ) if certificate.case_id is not None else None
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="certificate",
            entity_id=certificate.id,
            action="certificate.promote_current",
            payload=self._build_stage_payload(
                previous_current_certificate_id=previous_current_id,
                candidate_certificate_id=certificate.id,
                candidate_issue_date=candidate_version.issue_date.isoformat(),
                reason=reason,
                inspection_event_id=None if inspection_event is None else inspection_event.id,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        created_scopes = list(
            session.scalars(select(CertificateScope).where(CertificateScope.certificate_version_id == candidate_version.id))
        )
        session.flush()
        return {
            "certificate_id": certificate.id,
            "row_version": certificate.row_version,
            "site_id": certificate.site_id,
            "case_id": certificate.case_id,
            "certificate_type": certificate.certificate_type,
            **self._certificate_line_identity(session, certificate),
            "issuance_basis": certificate.issuance_basis,
            "latest_flag": certificate.latest_flag,
            "latest_version_id": candidate_version.id,
            "latest_version_no": candidate_version.version_no,
            "certificate_number": candidate_version.certificate_number,
            "issue_date": candidate_version.issue_date,
            "expiry_date": candidate_version.expiry_date,
            "scopes": self._serialize_certificate_scopes(created_scopes),
            "audit_event_id": audit_event.id,
            "inspection_event_id": None if inspection_event is None else inspection_event.id,
        }

    def _create_business_eligibility_candidate(
        self,
        session: Session,
        *,
        site: Site,
        version_values: dict[str, Any],
        linked_certificates: list[dict[str, Any]],
    ) -> tuple[
        BusinessEligibilityCertificate,
        BusinessEligibilityVersion,
        list[BusinessEligibilityCertificateLink],
    ]:
        self._get_company(session, site.company_id)
        row = BusinessEligibilityCertificate(
            site_id=site.id,
            company_id=site.company_id,
            latest_flag=False,
            latest_legacy_dkkd_id=None,
            replaces_legacy_dkkd_id=None,
            replaced_by_legacy_dkkd_id=None,
        )
        session.add(row)
        session.flush()

        version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=row.id,
            version_no=1,
            **version_values,
        )
        session.add(version)
        session.flush()
        created_links = self._replace_business_eligibility_links(
            session,
            business_eligibility_version_id=version.id,
            linked_certificates=linked_certificates,
            site_id=row.site_id,
        )
        return row, version, created_links

    def issue_business_eligibility(
        self,
        session: Session,
        *,
        site_id: str,
        certificate_number: str | None,
        issued_on,
        expires_on,
        professional_responsible_person_name: str | None,
        notes: str | None,
        linked_certificates: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        site = self._get_site(session, site_id)
        actor = self._get_or_create_app_user(session, user)

        row, version, created_links = self._create_business_eligibility_candidate(
            session,
            site=site,
            version_values={
                "certificate_number": certificate_number,
                "issued_on": issued_on,
                "expires_on": expires_on,
                "professional_responsible_person_name": professional_responsible_person_name,
                "notes": notes,
            },
            linked_certificates=linked_certificates,
        )
        after = {
            "site_id": row.site_id,
            "company_id": row.company_id,
            "latest_flag": row.latest_flag,
            "certificate_number": version.certificate_number,
            "issued_on": self._normalize_audit_value(version.issued_on),
            "expires_on": self._normalize_audit_value(version.expires_on),
            "professional_responsible_person_name": version.professional_responsible_person_name,
            "notes": version.notes,
            "linked_certificates": self._serialize_business_eligibility_links(created_links),
        }
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="business_eligibility_certificate",
            entity_id=row.id,
            action="business_eligibility.issue",
            payload=self._build_stage_payload(
                site_id=row.site_id,
                company_id=row.company_id,
                latest_flag=False,
                certificate_number=certificate_number,
                issued_on=None if issued_on is None else issued_on.isoformat(),
                expires_on=None if expires_on is None else expires_on.isoformat(),
                professional_responsible_person_name=professional_responsible_person_name,
                notes=notes,
                linked_certificates=self._serialize_business_eligibility_links(created_links),
                reason=reason,
            ),
            before=None,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "business_eligibility_certificate_id": row.id,
            "row_version": row.row_version,
            "site_id": row.site_id,
            "company_id": row.company_id,
            "latest_flag": row.latest_flag,
            "latest_version_id": version.id,
            "latest_version_no": version.version_no,
            "certificate_number": version.certificate_number,
            "issued_on": version.issued_on,
            "expires_on": version.expires_on,
            "professional_responsible_person_name": version.professional_responsible_person_name,
            "notes": version.notes,
            "linked_certificates": self._serialize_business_eligibility_links(created_links),
            "audit_event_id": audit_event.id,
            "inspection_event_id": None,
        }

    def upsert_business_eligibility_latest_version(
        self,
        session: Session,
        *,
        business_eligibility_certificate_id: str,
        expected_version: int | None = None,
        certificate_number: str | None,
        issued_on,
        expires_on,
        professional_responsible_person_name: str | None,
        notes: str | None,
        linked_certificates: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_business_eligibility(session, business_eligibility_certificate_id)
        self._assert_expected_version(row, expected_version, label="business_eligibility_certificate")
        actor = self._get_or_create_app_user(session, user)
        version = self._load_latest_business_eligibility_version(session, row.id)
        before = {
            "certificate_number": version.certificate_number,
            "issued_on": self._normalize_audit_value(version.issued_on),
            "expires_on": self._normalize_audit_value(version.expires_on),
            "professional_responsible_person_name": version.professional_responsible_person_name,
            "notes": version.notes,
            "linked_certificates": self._serialize_business_eligibility_links(
                list(
                    session.scalars(
                        select(BusinessEligibilityCertificateLink).where(
                            BusinessEligibilityCertificateLink.business_eligibility_version_id == version.id
                        )
                    )
                )
            ),
        }
        version.certificate_number = certificate_number
        version.issued_on = issued_on
        version.expires_on = expires_on
        version.professional_responsible_person_name = professional_responsible_person_name
        version.notes = notes
        # The optimistic-lock token belongs to the aggregate root. Mutating only
        # the child version/link rows would otherwise leave stale writers valid.
        row.updated_at = datetime.now(timezone.utc)
        created_links = self._replace_business_eligibility_links(
            session,
            business_eligibility_version_id=version.id,
            linked_certificates=linked_certificates,
            site_id=row.site_id,
        )
        after = {
            "certificate_number": version.certificate_number,
            "issued_on": self._normalize_audit_value(version.issued_on),
            "expires_on": self._normalize_audit_value(version.expires_on),
            "professional_responsible_person_name": version.professional_responsible_person_name,
            "notes": version.notes,
            "linked_certificates": self._serialize_business_eligibility_links(created_links),
        }
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="business_eligibility_version",
            entity_id=version.id,
            action="business_eligibility.latest_version.upsert",
            payload=self._build_stage_payload(
                business_eligibility_certificate_id=row.id,
                latest_version_no=version.version_no,
                certificate_number=certificate_number,
                issued_on=None if issued_on is None else issued_on.isoformat(),
                expires_on=None if expires_on is None else expires_on.isoformat(),
                professional_responsible_person_name=professional_responsible_person_name,
                notes=notes,
                linked_certificates=self._serialize_business_eligibility_links(created_links),
                reason=reason,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        session.flush()
        return {
            "business_eligibility_certificate_id": row.id,
            "row_version": row.row_version,
            "site_id": row.site_id,
            "company_id": row.company_id,
            "latest_flag": row.latest_flag,
            "latest_version_id": version.id,
            "latest_version_no": version.version_no,
            "certificate_number": version.certificate_number,
            "issued_on": version.issued_on,
            "expires_on": version.expires_on,
            "professional_responsible_person_name": version.professional_responsible_person_name,
            "notes": version.notes,
            "linked_certificates": self._serialize_business_eligibility_links(created_links),
            "audit_event_id": audit_event.id,
            "inspection_event_id": None,
        }

    def promote_business_eligibility_current(
        self,
        session: Session,
        *,
        business_eligibility_certificate_id: str,
        expected_version: int | None = None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_business_eligibility(session, business_eligibility_certificate_id)
        # The site owns the single-current invariant. Serialize promotion for one
        # site, then refresh/revalidate the candidate inside that lock so a
        # readiness snapshot or optimistic-lock token cannot race another promote.
        self._lock_site(session, row.site_id)
        session.refresh(row)
        self._assert_expected_version(row, expected_version, label="business_eligibility_certificate")
        candidate_version = self._load_latest_business_eligibility_version(session, row.id)
        blocker = self._get_business_eligibility_promotion_blocker(
            session,
            certificate=row,
            version=candidate_version,
        )
        if blocker is not None:
            details = {
                "certificate_data_incomplete": "Business eligibility promotion requires certificate number and issue date.",
                "invalid_linked_certificate": "Business eligibility promotion references an invalid linked Case, canonical ProductionLine, or cross-site certificate.",
                "multiple_current_records": "Business eligibility promotion is blocked because the site has multiple current records.",
                "already_current": "Business eligibility certificate is already the current record for this site.",
                "current_record_incomplete": "Business eligibility promotion is blocked because the current record is incomplete.",
                "candidate_issue_date_precedes_current": "Business eligibility promotion requires a candidate issue date that is not older than the current active record.",
            }
            raise HTTPException(status_code=409, detail=details[blocker])

        actor = self._get_or_create_app_user(session, user)
        current_rows = self._business_eligibility_current_rows(session, site_id=row.site_id)
        current = current_rows[0] if current_rows else None
        previous_current_id = None if current is None else current.id
        before = {
            "latest_flag": row.latest_flag,
            "previous_current_certificate_id": previous_current_id,
        }
        if current is not None and current.id != row.id:
            current.latest_flag = False
        row.latest_flag = True
        after = {
            "latest_flag": row.latest_flag,
            "previous_current_certificate_id": previous_current_id,
        }
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="business_eligibility_certificate",
            entity_id=row.id,
            action="business_eligibility.promote_current",
            payload=self._build_stage_payload(
                previous_current_certificate_id=previous_current_id,
                candidate_certificate_id=row.id,
                candidate_issued_on=candidate_version.issued_on.isoformat(),
                reason=reason,
            ),
            before=before,
            after=after,
            reason=reason,
        )
        created_links = list(
            session.scalars(
                select(BusinessEligibilityCertificateLink).where(
                    BusinessEligibilityCertificateLink.business_eligibility_version_id == candidate_version.id
                )
            )
        )
        session.flush()
        return {
            "business_eligibility_certificate_id": row.id,
            "row_version": row.row_version,
            "site_id": row.site_id,
            "company_id": row.company_id,
            "latest_flag": row.latest_flag,
            "latest_version_id": candidate_version.id,
            "latest_version_no": candidate_version.version_no,
            "certificate_number": candidate_version.certificate_number,
            "issued_on": candidate_version.issued_on,
            "expires_on": candidate_version.expires_on,
            "professional_responsible_person_name": candidate_version.professional_responsible_person_name,
            "notes": candidate_version.notes,
            "linked_certificates": self._serialize_business_eligibility_links(created_links),
            "audit_event_id": audit_event.id,
            "inspection_event_id": None,
        }
