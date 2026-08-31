from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.api.session import commit_or_409, get_session_from_request_factory
from backend.app.auth import AuthenticatedUser, get_authenticated_user, require_permissions
from backend.app.read_models import (
    BusinessEligibilityIssueRequest,
    BusinessEligibilityLatestVersionUpsertRequest,
    BusinessEligibilityMutationRead,
    BusinessEligibilityPromoteCurrentRequest,
    CapaCycleAssessRequest,
    CapaCycleCreateRequest,
    CapaCycleRead,
    CapaCycleSubmitRequest,
    CapaCycleUpdateRequest,
    CaseApplicationRead,
    CaseApplicationUpsertRequest,
    CaseAssessmentRead,
    CaseAssessmentUpsertRequest,
    CertificateIssueRequest,
    CertificateLatestVersionUpsertRequest,
    CertificateMutationRead,
    CertificatePromoteCurrentRequest,
    InspectionCaseCreateRead,
    InspectionCaseCreateRequest,
    CaseTransitionRead,
    CaseTransitionRequest,
    InspectionOutcomeRead,
    InspectionOutcomeUpsertRequest,
    InspectionPlanRead,
    InspectionPlanUpsertRequest,
    InspectionTeamRead,
    InspectionTeamUpsertRequest,
)
from backend.app.services import CaseWorkflowService

def register_workflow_routes(app, session_factory) -> None:
    dependency = Depends(get_session_from_request_factory(session_factory))
    service = CaseWorkflowService()

    def create_inspection_case(
        site_id: str,
        payload: InspectionCaseCreateRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"case.edit"})
        result = service.create_inspection_case(
            session,
            site_id=site_id,
            gxp_type=payload.gxp_type,
            line_code=payload.line_code,
            applicable_standard=payload.applicable_standard,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return InspectionCaseCreateRead(**result)

    def transition_case(
        case_id: str,
        payload: CaseTransitionRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"case.edit"})
        result = service.transition_case(
            session,
            case_id=case_id,
            target_state=payload.target_state,
            expected_version=payload.expected_version,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CaseTransitionRead(**result)

    def upsert_case_application(
        case_id: str,
        payload: CaseApplicationUpsertRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"case.edit"})
        result = service.upsert_case_application(
            session,
            case_id=case_id,
            expected_version=payload.expected_version,
            submitted_on=payload.submitted_on,
            dossier_code=payload.dossier_code,
            dossier_reference=payload.dossier_reference,
            applicant_name=payload.applicant_name,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CaseApplicationRead(**result)

    def upsert_case_assessment(
        case_id: str,
        payload: CaseAssessmentUpsertRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"case.edit"})
        result = service.upsert_case_assessment(
            session,
            case_id=case_id,
            expected_version=payload.expected_version,
            assessed_on=payload.assessed_on,
            assessor_name=payload.assessor_name,
            assessment_result=payload.assessment_result,
            notes=payload.notes,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CaseAssessmentRead(**result)

    def upsert_inspection_plan(
        case_id: str,
        payload: InspectionPlanUpsertRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"inspection.edit"})
        result = service.upsert_inspection_plan(
            session,
            case_id=case_id,
            expected_version=payload.expected_version,
            plan_start_on=payload.plan_start_on,
            plan_end_on=payload.plan_end_on,
            planning_sheet_name=payload.planning_sheet_name,
            decision_document_hint=payload.decision_document_hint,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return InspectionPlanRead(**result)

    def upsert_inspection_outcome(
        case_id: str,
        payload: InspectionOutcomeUpsertRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"inspection.edit"})
        result = service.upsert_inspection_outcome(
            session,
            case_id=case_id,
            expected_version=payload.expected_version,
            inspected_on=payload.inspected_on,
            inspected_to_on=payload.inspected_to_on,
            decision_reference=payload.decision_reference,
            bbkt_reference=payload.bbkt_reference,
            outcome_result=payload.outcome_result,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return InspectionOutcomeRead(**result)

    def upsert_inspection_team(
        case_id: str,
        payload: InspectionTeamUpsertRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"inspection.edit"})
        result = service.upsert_inspection_team(
            session,
            case_id=case_id,
            expected_version=payload.expected_version,
            display_text=payload.display_text,
            members=[item.model_dump() for item in payload.members],
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return InspectionTeamRead(**result)

    def list_capa_cycles(
        case_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"capa.view"})
        return [CapaCycleRead(**item) for item in service.list_capa_cycles(session, case_id=case_id)]

    def create_capa_cycle(
        case_id: str,
        payload: CapaCycleCreateRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"capa.edit"})
        result = service.create_capa_cycle(
            session,
            case_id=case_id,
            expected_case_version=payload.expected_case_version,
            requested_on=payload.requested_on,
            notes=payload.notes,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CapaCycleRead(**result)

    def update_capa_cycle(
        capa_cycle_id: str,
        payload: CapaCycleUpdateRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"capa.edit"})
        result = service.update_capa_cycle(
            session,
            capa_cycle_id=capa_cycle_id,
            expected_version=payload.expected_version,
            requested_on=payload.requested_on,
            notes=payload.notes,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CapaCycleRead(**result)

    def submit_capa_cycle(
        capa_cycle_id: str,
        payload: CapaCycleSubmitRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"capa.edit"})
        result = service.submit_capa_cycle(
            session,
            capa_cycle_id=capa_cycle_id,
            expected_version=payload.expected_version,
            submitted_on=payload.submitted_on,
            notes=payload.notes,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CapaCycleRead(**result)

    def assess_capa_cycle(
        capa_cycle_id: str,
        payload: CapaCycleAssessRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"capa.assess"})
        result = service.assess_capa_cycle(
            session,
            capa_cycle_id=capa_cycle_id,
            expected_version=payload.expected_version,
            assessed_on=payload.assessed_on,
            assessor_name=payload.assessor_name,
            result=payload.result,
            notes=payload.notes,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CapaCycleRead(**result)

    def issue_certificate(
        site_id: str,
        payload: CertificateIssueRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"certificate.issue"})
        result = service.issue_certificate(
            session,
            site_id=site_id,
            case_id=payload.case_id,
            certificate_type=payload.certificate_type,
            issuance_basis=payload.issuance_basis,
            certificate_number=payload.certificate_number,
            issue_date=payload.issue_date,
            expiry_date=payload.expiry_date,
            scopes=[item.model_dump() for item in payload.scopes],
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CertificateMutationRead(**result)

    def upsert_certificate_latest_version(
        certificate_id: str,
        payload: CertificateLatestVersionUpsertRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"certificate.edit"})
        result = service.upsert_certificate_latest_version(
            session,
            certificate_id=certificate_id,
            expected_version=payload.expected_version,
            certificate_number=payload.certificate_number,
            issue_date=payload.issue_date,
            expiry_date=payload.expiry_date,
            scopes=[item.model_dump() for item in payload.scopes],
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CertificateMutationRead(**result)

    def promote_certificate_current(
        certificate_id: str,
        payload: CertificatePromoteCurrentRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"certificate.approve"})
        result = service.promote_certificate_current(
            session,
            certificate_id=certificate_id,
            expected_version=payload.expected_version,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return CertificateMutationRead(**result)

    def issue_business_eligibility(
        site_id: str,
        payload: BusinessEligibilityIssueRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"certificate.issue"})
        result = service.issue_business_eligibility(
            session,
            site_id=site_id,
            certificate_number=payload.certificate_number,
            issued_on=payload.issued_on,
            expires_on=payload.expires_on,
            professional_responsible_person_name=payload.professional_responsible_person_name,
            notes=payload.notes,
            linked_certificates=[item.model_dump() for item in payload.linked_certificates],
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return BusinessEligibilityMutationRead(**result)

    def upsert_business_eligibility_latest_version(
        business_eligibility_certificate_id: str,
        payload: BusinessEligibilityLatestVersionUpsertRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"certificate.edit"})
        result = service.upsert_business_eligibility_latest_version(
            session,
            business_eligibility_certificate_id=business_eligibility_certificate_id,
            expected_version=payload.expected_version,
            certificate_number=payload.certificate_number,
            issued_on=payload.issued_on,
            expires_on=payload.expires_on,
            professional_responsible_person_name=payload.professional_responsible_person_name,
            notes=payload.notes,
            linked_certificates=[item.model_dump() for item in payload.linked_certificates],
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return BusinessEligibilityMutationRead(**result)

    def promote_business_eligibility_current(
        business_eligibility_certificate_id: str,
        payload: BusinessEligibilityPromoteCurrentRequest,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"certificate.approve"})
        result = service.promote_business_eligibility_current(
            session,
            business_eligibility_certificate_id=business_eligibility_certificate_id,
            expected_version=payload.expected_version,
            reason=payload.reason,
            user=user,
        )
        commit_or_409(session)
        return BusinessEligibilityMutationRead(**result)

    app.add_api_route(
        "/sites/{site_id}/inspection-cases",
        create_inspection_case,
        methods=["POST"],
        response_model=InspectionCaseCreateRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/transition",
        transition_case,
        methods=["POST"],
        response_model=CaseTransitionRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/application",
        upsert_case_application,
        methods=["PUT"],
        response_model=CaseApplicationRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/assessment",
        upsert_case_assessment,
        methods=["PUT"],
        response_model=CaseAssessmentRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/plan",
        upsert_inspection_plan,
        methods=["PUT"],
        response_model=InspectionPlanRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/outcome",
        upsert_inspection_outcome,
        methods=["PUT"],
        response_model=InspectionOutcomeRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/team",
        upsert_inspection_team,
        methods=["PUT"],
        response_model=InspectionTeamRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/capa-cycles",
        list_capa_cycles,
        methods=["GET"],
        response_model=list[CapaCycleRead],
        tags=["workflow"],
    )
    app.add_api_route(
        "/cases/{case_id}/capa-cycles",
        create_capa_cycle,
        methods=["POST"],
        response_model=CapaCycleRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/capa-cycles/{capa_cycle_id}",
        update_capa_cycle,
        methods=["PUT"],
        response_model=CapaCycleRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/capa-cycles/{capa_cycle_id}/submit",
        submit_capa_cycle,
        methods=["POST"],
        response_model=CapaCycleRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/capa-cycles/{capa_cycle_id}/assess",
        assess_capa_cycle,
        methods=["POST"],
        response_model=CapaCycleRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/sites/{site_id}/certificates",
        issue_certificate,
        methods=["POST"],
        response_model=CertificateMutationRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/certificates/{certificate_id}/latest-version",
        upsert_certificate_latest_version,
        methods=["PUT"],
        response_model=CertificateMutationRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/certificates/{certificate_id}/promote-current",
        promote_certificate_current,
        methods=["POST"],
        response_model=CertificateMutationRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/sites/{site_id}/business-eligibility-certificates",
        issue_business_eligibility,
        methods=["POST"],
        response_model=BusinessEligibilityMutationRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/business-eligibility-certificates/{business_eligibility_certificate_id}/latest-version",
        upsert_business_eligibility_latest_version,
        methods=["PUT"],
        response_model=BusinessEligibilityMutationRead,
        tags=["workflow"],
    )
    app.add_api_route(
        "/business-eligibility-certificates/{business_eligibility_certificate_id}/promote-current",
        promote_business_eligibility_current,
        methods=["POST"],
        response_model=BusinessEligibilityMutationRead,
        tags=["workflow"],
    )
