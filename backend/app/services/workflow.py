from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.audit_payload import normalize_and_redact_audit_payload
from backend.app.auth import AuthenticatedUser
from backend.app.db.enums import AuditActorType, CaseState, InspectionEventType
from backend.app.db.models.phase1 import (
    AppUser,
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
    InspectionTeam,
    InspectionTeamMember,
    InspectionOutcome,
    InspectionPlan,
    Site,
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


CASE_STATE_TO_EVENT: dict[CaseState, InspectionEventType] = {
    CaseState.APPLICATION_RECEIVED: InspectionEventType.APPLICATION_SUBMITTED,
    CaseState.UNDER_ASSESSMENT: InspectionEventType.ASSESSMENT_COMPLETED,
    CaseState.PLANNED: InspectionEventType.PLAN_CREATED,
    CaseState.DECISION_ISSUED: InspectionEventType.DECISION_ISSUED,
    CaseState.INSPECTION_COMPLETED: InspectionEventType.INSPECTION_EXECUTED,
    CaseState.CERTIFIED: InspectionEventType.CERTIFICATE_ISSUED,
}

CAPA_BLOCKING_STATUSES = {"requested", "submitted"}
CAPA_ACCEPTED_STATUS = "accepted"
CAPA_REJECTED_STATUS = "rejected"
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
REASSESSMENT_INSPECTION_TYPE = "Tái"


class CaseWorkflowService:
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
            "role_label": member.role_label,
            "sort_order": member.sort_order,
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
            payload=json.dumps(payload, ensure_ascii=False),
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
        issuance_basis: str,
    ) -> None:
        if case is None and issuance_basis == "inspection_case":
            raise HTTPException(
                status_code=422,
                detail="inspection_case issuance requires a backing case_id.",
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
        latest = self._latest_case_capa_cycle(session, case.id)
        if latest is None:
            return
        if latest.status != CAPA_ACCEPTED_STATUS:
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
    ) -> list[BusinessEligibilityCertificateLink]:
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
        for payload in linked_certificates:
            certificate_id = payload["certificate_id"]
            if session.get(Certificate, certificate_id) is None:
                raise HTTPException(status_code=404, detail=f"Linked certificate {certificate_id} was not found.")
            link = BusinessEligibilityCertificateLink(
                business_eligibility_version_id=business_eligibility_version_id,
                certificate_id=certificate_id,
                link_role=payload.get("link_role") or "source_certificate",
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
            has_profile = bool(item.get("inspector_profile_id"))
            has_person = bool(item.get("person_id"))
            if has_profile == has_person:
                raise HTTPException(
                    status_code=422,
                    detail=f"Inspection team member at index {index} must set exactly one of inspector_profile_id or person_id.",
                )

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
    ) -> bool:
        normalized_line_code = self._normalize_line_code(line_code)
        case_match = session.scalars(
            select(Case.id).where(
                Case.site_id == site_id,
                Case.gxp_type == gxp_type,
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
                func.nullif(func.trim(Certificate.line_code), "") == normalized_line_code,
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
    ) -> Case | None:
        normalized_line_code = self._normalize_line_code(line_code)
        return session.scalars(
            select(Case)
            .where(
                Case.site_id == site_id,
                Case.gxp_type == gxp_type,
                func.nullif(func.trim(Case.scope_code), "") == normalized_line_code,
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
    ) -> tuple[str, str | None]:
        normalized_gxp_type = str(gxp_type or "").strip()
        if normalized_gxp_type not in SUPPORTED_CASE_GXP_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported GxP context for reassessment creation.")
        normalized_line_code = self._normalize_line_code(line_code)
        if not self._site_has_gxp_context(
            session,
            site_id=site_id,
            gxp_type=normalized_gxp_type,
            line_code=normalized_line_code,
        ):
            raise HTTPException(
                status_code=422,
                detail="Selected facility/GxP/line context is not an authoritative existing context for reassessment creation.",
            )
        return normalized_gxp_type, normalized_line_code

    def get_create_reassessment_case_action_readiness(
        self,
        session: Session,
        *,
        site_id: str,
        gxp_type: str | None,
        line_code: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        required_permissions = [CREATE_INSPECTION_CASE_PERMISSION]
        normalized_gxp_type = str(gxp_type or "").strip() or None
        normalized_line_code = self._normalize_line_code(line_code)
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
        if not self._site_has_gxp_context(
            session,
            site_id=site_id,
            gxp_type=normalized_gxp_type,
            line_code=normalized_line_code,
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

    def _serialize_capa_cycle(self, row: CapaCycle, *, audit_event_id: str | None = None) -> dict[str, Any]:
        return {
            "capa_cycle_id": row.id,
            "case_id": row.case_id,
            "row_version": row.row_version,
            "round_no": row.round_no,
            "requested_on": row.requested_on,
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

        allowed_targets = ALLOWED_CASE_TRANSITIONS.get(previous_state, set())
        if parsed_target_state not in allowed_targets:
            raise HTTPException(
                status_code=409,
                detail=f"Transition from {previous_state.value} to {parsed_target_state.value} is not allowed.",
            )
        if (
            previous_state == CaseState.INSPECTION_COMPLETED
            and parsed_target_state == CaseState.AWAITING_CERTIFICATE_DECISION
        ):
            self._assert_case_can_advance_without_pending_capa(session, row.id)
        if previous_state == CaseState.AWAITING_CERTIFICATE_DECISION and parsed_target_state == CaseState.CERTIFIED:
            self._assert_case_certificate_eligibility(
                session,
                case=row,
                allow_states={CaseState.AWAITING_CERTIFICATE_DECISION},
                blocked_detail="Case cannot transition to certified while CAPA remains required or unaccepted.",
            )

        actor = self._get_or_create_app_user(session, user)
        before = {"state": previous_state.value}
        row.state = parsed_target_state
        after = {"state": parsed_target_state.value}

        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=CASE_STATE_TO_EVENT.get(parsed_target_state),
            payload={
                "previous_state": previous_state.value,
                "current_state": parsed_target_state.value,
                "reason": reason,
                "actor_username": user.username,
            },
        )
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
        applicable_standard: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        locked_site = self._lock_site(session, site_id)
        normalized_gxp_type, normalized_line_code = self._validate_create_inspection_case_context(
            session,
            site_id=locked_site.id,
            gxp_type=gxp_type,
            line_code=line_code,
        )
        normalized_inspection_type = REASSESSMENT_INSPECTION_TYPE
        normalized_applicable_standard = str(applicable_standard or "").strip() or None
        existing_case = self._find_open_context_case(
            session,
            site_id=locked_site.id,
            gxp_type=normalized_gxp_type,
            line_code=normalized_line_code,
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
        after = {
            "case_id": case.id,
            "site_id": case.site_id,
            "gxp_type": case.gxp_type,
            "line_code": case.scope_code,
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
            "inspection_type": case.inspection_type,
            "applicable_standard": case.applicable_standard,
            "state": case.state.value,
            "row_version": case.row_version,
            "legacy_inspection_id": case.legacy_inspection_id,
            "legacy_inspection_code": case.legacy_inspection_code,
            "audit_event_id": audit_event.id,
        }

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
        notes: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
        self._assert_expected_version(row, expected_case_version, label="case")
        self._assert_case_allows_capa_request(row)
        self._assert_case_has_no_open_capa_cycle(session, row.id)
        actor = self._get_or_create_app_user(session, user)
        capa_cycle = CapaCycle(
            case_id=row.id,
            round_no=self._next_capa_round_no(session, row.id),
            requested_on=requested_on,
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
        notes: str | None,
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_capa_cycle(session, capa_cycle_id)
        self._assert_expected_version(row, expected_version, label="capa_cycle")
        if row.status == CAPA_ACCEPTED_STATUS:
            raise HTTPException(status_code=409, detail="Accepted CAPA cycles are immutable.")
        actor = self._get_or_create_app_user(session, user)
        before = self._snapshot_fields(row, ["requested_on", "notes", "status"])
        row.requested_on = requested_on
        row.notes = notes
        after = self._snapshot_fields(row, ["requested_on", "notes", "status"])
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
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
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
        stage.submitted_on = submitted_on
        stage.dossier_code = dossier_code
        stage.dossier_reference = dossier_reference
        stage.applicant_name = applicant_name
        after = self._snapshot_fields(
            stage,
            ["submitted_on", "dossier_code", "dossier_reference", "applicant_name"],
        )
        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=InspectionEventType.APPLICATION_SUBMITTED if submitted_on is not None else None,
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
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
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
        stage.assessed_on = assessed_on
        stage.assessor_name = assessor_name
        stage.assessment_result = assessment_result
        stage.notes = notes
        after = self._snapshot_fields(
            stage,
            ["assessed_on", "assessor_name", "assessment_result", "notes"],
        )
        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=InspectionEventType.ASSESSMENT_COMPLETED if assessed_on is not None else None,
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
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
        actor = self._get_or_create_app_user(session, user)
        stage = session.scalars(select(InspectionPlan).where(InspectionPlan.case_id == row.id)).first()
        if stage is None:
            stage = InspectionPlan(case_id=row.id)
            session.add(stage)
            session.flush()
        self._assert_expected_version(stage, expected_version, label="inspection_plan")
        before = self._snapshot_fields(
            stage,
            ["plan_start_on", "plan_end_on", "planning_sheet_name", "decision_document_hint"],
        )
        stage.plan_start_on = plan_start_on
        stage.plan_end_on = plan_end_on
        stage.planning_sheet_name = planning_sheet_name
        stage.decision_document_hint = decision_document_hint
        after = self._snapshot_fields(
            stage,
            ["plan_start_on", "plan_end_on", "planning_sheet_name", "decision_document_hint"],
        )
        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=InspectionEventType.PLAN_CREATED if plan_start_on is not None or plan_end_on is not None else None,
            payload=self._build_stage_payload(
                stage="inspection_plan",
                plan_start_on=None if plan_start_on is None else plan_start_on.isoformat(),
                plan_end_on=None if plan_end_on is None else plan_end_on.isoformat(),
                planning_sheet_name=planning_sheet_name,
                decision_document_hint=decision_document_hint,
                reason=reason,
            ),
        )
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
                decision_document_hint=decision_document_hint,
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
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
        actor = self._get_or_create_app_user(session, user)
        stage = session.scalars(select(InspectionOutcome).where(InspectionOutcome.case_id == row.id)).first()
        if stage is None:
            stage = InspectionOutcome(case_id=row.id)
            session.add(stage)
            session.flush()
        self._assert_expected_version(stage, expected_version, label="inspection_outcome")
        before = self._snapshot_fields(
            stage,
            ["inspected_on", "inspected_to_on", "decision_reference", "bbkt_reference", "outcome_result"],
        )
        stage.inspected_on = inspected_on
        stage.inspected_to_on = inspected_to_on
        stage.decision_reference = decision_reference
        stage.bbkt_reference = bbkt_reference
        stage.outcome_result = outcome_result
        after = self._snapshot_fields(
            stage,
            ["inspected_on", "inspected_to_on", "decision_reference", "bbkt_reference", "outcome_result"],
        )
        inspection_event = self._write_inspection_event(
            session,
            case_id=row.id,
            event_type=InspectionEventType.OUTCOME_RECORDED if outcome_result is not None else None,
            payload=self._build_stage_payload(
                stage="inspection_outcome",
                inspected_on=None if inspected_on is None else inspected_on.isoformat(),
                inspected_to_on=None if inspected_to_on is None else inspected_to_on.isoformat(),
                decision_reference=decision_reference,
                bbkt_reference=bbkt_reference,
                outcome_result=outcome_result,
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
                inspected_to_on=None if inspected_to_on is None else inspected_to_on.isoformat(),
                decision_reference=decision_reference,
                bbkt_reference=bbkt_reference,
                outcome_result=outcome_result,
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
            "decision_reference": stage.decision_reference,
            "bbkt_reference": stage.bbkt_reference,
            "outcome_result": stage.outcome_result,
            "audit_event_id": audit_event.id,
            "inspection_event_id": None if inspection_event is None else inspection_event.id,
        }

    def upsert_inspection_team(
        self,
        session: Session,
        *,
        case_id: str,
        expected_version: int | None = None,
        display_text: str | None,
        members: list[dict[str, Any]],
        reason: str | None,
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        row = self._get_case(session, case_id)
        self._validate_team_members(members)
        actor = self._get_or_create_app_user(session, user)

        team = session.scalars(select(InspectionTeam).where(InspectionTeam.case_id == row.id)).first()
        if team is None:
            team = InspectionTeam(case_id=row.id)
            session.add(team)
            session.flush()
        self._assert_expected_version(team, expected_version, label="inspection_team")
        existing_members = list(session.scalars(select(InspectionTeamMember).where(InspectionTeamMember.team_id == team.id)))
        before = {
            "display_text": team.display_text,
            "members": [
                self._team_member_payload(member)
                for member in sorted(existing_members, key=lambda item: item.sort_order)
            ],
        }

        team.display_text = display_text

        for member in existing_members:
            session.delete(member)
        session.flush()

        created_members: list[InspectionTeamMember] = []
        for item in members:
            member = InspectionTeamMember(
                team_id=team.id,
                inspector_profile_id=item.get("inspector_profile_id"),
                person_id=item.get("person_id"),
                role_label=item.get("role_label"),
                sort_order=int(item.get("sort_order", 0)),
            )
            session.add(member)
            created_members.append(member)
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
                display_text=display_text,
                member_count=len(created_members),
                members=[
                    {
                        "id": member.id,
                        "inspector_profile_id": member.inspector_profile_id,
                        "person_id": member.person_id,
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
                    "role_label": member.role_label,
                    "sort_order": member.sort_order,
                }
                for member in sorted(created_members, key=lambda item: item.sort_order)
            ],
            "audit_event_id": audit_event.id,
        }

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
        self._validate_certificate_case_link(site_id=site.id, case=case, issuance_basis=issuance_basis)
        if case is not None:
            self._assert_case_certificate_eligibility(
                session,
                case=case,
                allow_states={CaseState.AWAITING_CERTIFICATE_DECISION, CaseState.CERTIFIED},
                blocked_detail="Case-backed certificate issuance is blocked until the latest CAPA cycle is accepted.",
            )
        actor = self._get_or_create_app_user(session, user)

        certificate = Certificate(
            site_id=site.id,
            case_id=None if case is None else case.id,
            certificate_type=certificate_type,
            issuance_basis=issuance_basis,
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
            is_latest_version=True,
        )
        session.add(version)
        session.flush()
        created_scopes = self._replace_certificate_scopes(
            session,
            certificate_version_id=version.id,
            scopes=scopes,
        )
        after = {
            "site_id": certificate.site_id,
            "case_id": certificate.case_id,
            "certificate_type": certificate.certificate_type,
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
        if certificate.case_id is not None:
            case = self._get_case(session, certificate.case_id)
            self._assert_case_certificate_eligibility(
                session,
                case=case,
                allow_states={CaseState.AWAITING_CERTIFICATE_DECISION, CaseState.CERTIFIED},
                blocked_detail="Current-certificate promotion is blocked until the latest CAPA cycle is accepted.",
            )
        actor = self._get_or_create_app_user(session, user)
        candidate_version = self._load_latest_certificate_version(session, certificate.id)
        if not candidate_version.certificate_number or candidate_version.issue_date is None or candidate_version.expiry_date is None:
            raise HTTPException(
                status_code=409,
                detail="Certificate promotion requires certificate number, issue date, and expiry date.",
            )

        current = session.scalars(
            select(Certificate).where(
                Certificate.site_id == certificate.site_id,
                Certificate.certificate_type == certificate.certificate_type,
                Certificate.latest_flag.is_(True),
            )
        ).first()
        previous_current_id = None if current is None else current.id
        previous_current_version = None if current is None else self._load_latest_certificate_version(session, current.id)
        if previous_current_version is not None and previous_current_version.issue_date is not None:
            if candidate_version.issue_date < previous_current_version.issue_date:
                raise HTTPException(
                    status_code=409,
                    detail="Certificate promotion requires a candidate issue date that is not older than the current active certificate.",
                )
        before = {
            "latest_flag": certificate.latest_flag,
            "previous_current_certificate_id": previous_current_id,
        }
        if current is not None and current.id != certificate.id:
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
        self._get_company(session, site.company_id)
        actor = self._get_or_create_app_user(session, user)

        row = BusinessEligibilityCertificate(
            site_id=site.id,
            company_id=site.company_id,
            latest_flag=False,
            latest_legacy_dkkd_id=None,
        )
        session.add(row)
        session.flush()

        version = BusinessEligibilityVersion(
            business_eligibility_certificate_id=row.id,
            version_no=1,
            certificate_number=certificate_number,
            issued_on=issued_on,
            expires_on=expires_on,
            professional_responsible_person_name=professional_responsible_person_name,
            notes=notes,
        )
        session.add(version)
        session.flush()
        created_links = self._replace_business_eligibility_links(
            session,
            business_eligibility_version_id=version.id,
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
        created_links = self._replace_business_eligibility_links(
            session,
            business_eligibility_version_id=version.id,
            linked_certificates=linked_certificates,
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
        self._assert_expected_version(row, expected_version, label="business_eligibility_certificate")
        actor = self._get_or_create_app_user(session, user)
        candidate_version = self._load_latest_business_eligibility_version(session, row.id)
        if not candidate_version.certificate_number or candidate_version.issued_on is None:
            raise HTTPException(
                status_code=409,
                detail="Business eligibility promotion requires certificate number and issue date.",
            )

        current = session.scalars(
            select(BusinessEligibilityCertificate).where(
                BusinessEligibilityCertificate.site_id == row.site_id,
                BusinessEligibilityCertificate.latest_flag.is_(True),
            )
        ).first()
        previous_current_id = None if current is None else current.id
        previous_current_version = None if current is None else self._load_latest_business_eligibility_version(session, current.id)
        if previous_current_version is not None and previous_current_version.issued_on is not None:
            if candidate_version.issued_on < previous_current_version.issued_on:
                raise HTTPException(
                    status_code=409,
                    detail="Business eligibility promotion requires a candidate issue date that is not older than the current active record.",
                )
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
