from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
import mimetypes
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.app.audit_payload import normalize_and_redact_audit_payload
from backend.app.auth import AuthenticatedUser
from backend.app.db.enums import AuditActorType, DocumentGenerationStatus
from backend.app.db.models.phase1 import (
    AppUser,
    AuditEvent,
    BusinessEligibilityCertificate,
    CapaCycle,
    Case,
    Certificate,
    Document,
    DocumentGenerationRun,
    DocumentSourceDependency,
    DocumentVariant,
    DocumentVersion,
    TemplateDefinition,
)
from backend.app.document.docx_template_render import (
    DocxTemplateRenderError,
    render_template_aware_docx_and_finalize,
)
from backend.app.document.output_version import (
    OutputVersionAllocationError,
    _load_case_storage_identity,
    cleanup_output_target_if_owned,
)
from backend.app.document.persistence import (
    DocumentPersistenceError,
    resolve_generation_template_metadata,
)
from backend.app.document.payload_builders import DocumentPayloadBuildError
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    InspectionKeHoachKtPayloadInputError,
    load_inspection_ke_hoach_kt_payload_input,
)
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    INSPECTION_KE_HOACH_KT_FAMILY,
    InspectionKeHoachKtTemplateAssetContractError,
    get_inspection_ke_hoach_kt_output_filename,
)
from backend.app.document.service import (
    DocumentPreparationInput,
    prepare_document_generation_job,
    allocate_prepared_template_aware_docx_generation,
)
from backend.app.document.service_contract import (
    DocumentGenerationRequest,
    DocumentPayloadEnvelope,
    DocumentTemplateSelectionError,
    load_default_registry,
    plan_document_generation,
)
from backend.app.document.source_binary_contract import SourceBinaryContractError
from backend.app.document.template_binary import (
    TemplateBinaryError,
    build_prepared_template_binary_requirement,
    open_template_binary_stream,
)
from backend.app.document.template_contract_runtime import (
    TemplateContractRuntimeError,
    build_scalar_replacement_plan_for_template,
    load_default_template_contract_reconciliation,
)
from backend.app.db.enums import StorageResolutionStatus
from backend.app.storage.binding_service import StorageBindingService
from backend.app.storage.types import (
    StorageOperationError,
    StorageServiceProtocol,
    StorageTargetExistsError,
)


@dataclass(frozen=True)
class TemplateReadiness:
    template_definition_id: str | None
    family_code: str
    template_name: str
    readiness_status: str
    detail: str
    storage_root: str | None
    storage_relative_path: str | None
    original_filename: str | None
    checksum_sha256: str | None
    scalar_replacement_mode: str | None
    template_variant_key: str | None


@dataclass(frozen=True)
class DocumentBinaryLocator:
    document_id: str
    document_version_id: str
    storage_root: str
    storage_relative_path: str
    original_filename: str
    checksum_sha256: str
    media_type: str


DocumentBinaryParentScope = Literal["case", "capa_cycle"]


class DocumentWorkflowService:
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
    ) -> AuditEvent:
        audit_event = AuditEvent(
            actor_type=AuditActorType.USER,
            actor_user_id=actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_redacted=json.dumps(normalize_and_redact_audit_payload(payload), ensure_ascii=False, sort_keys=True),
        )
        session.add(audit_event)
        session.flush()
        return audit_event

    @staticmethod
    def _current_openable_khkt_version_id(
        session: Session, *, case_id: str,
    ) -> str | None:
        """Shared read-only current KHKT predicate for CREATE and diagnostic."""
        return session.scalar(
            select(DocumentVersion.id)
            .join(
                DocumentVariant,
                DocumentVariant.id == DocumentVersion.document_variant_id,
            )
            .join(Document, Document.id == DocumentVariant.document_id)
            .where(
                Document.case_id == case_id,
                Document.family_code == INSPECTION_KE_HOACH_KT_FAMILY,
                DocumentVersion.is_current.is_(True),
                *(
                    func.length(func.trim(field)) > 0
                    for field in (
                        DocumentVersion.storage_root,
                        DocumentVersion.storage_relative_path,
                        DocumentVersion.original_filename,
                        DocumentVersion.checksum_sha256,
                    )
                ),
            )
            .limit(1)
        )

    @staticmethod
    def build_case_inspection_plan_render_payload(
        session: Session,
        *,
        case_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """Build KHKT typed create input from the canonical Case.

        The Case row lock serializes two typed creates for the same Case until
        the route commits. An already-openable current KHKT version means the
        contextual action is OPEN/HISTORY, not CREATE; a second fresh create
        must not bypass that state by calling this endpoint directly.
        """
        case = session.scalar(
            select(Case).where(Case.id == case_id).with_for_update()
        )
        if case is None:
            raise HTTPException(status_code=404, detail="Case was not found.")
        try:
            filename = get_inspection_ke_hoach_kt_output_filename(case.gxp_type)
        except InspectionKeHoachKtTemplateAssetContractError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        current_version_id = DocumentWorkflowService._current_openable_khkt_version_id(
            session, case_id=case.id,
        )
        if current_version_id is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Current inspection plan document already exists for this Case; "
                    "open its current version or history instead of creating another."
                ),
            )
        return {
            "family_code": INSPECTION_KE_HOACH_KT_FAMILY,
            "case_id": case.id,
            "gxp_type": case.gxp_type,
            "storage_scope": "inspection_folder",
            "language_code": "vi",
            "idempotency_key": idempotency_key,
            "output_filename": filename,
            "payload": {},
            "strict_payload": True,
        }

    def get_case_inspection_plan_runtime_readiness(
        self,
        session: Session,
        *,
        case_id: str,
        storage: StorageServiceProtocol | None,
    ) -> dict[str, Any]:
        """On-demand read-only KHKT diagnostic, not a render or allocation.

        A ready outcome means prerequisites were *observed* at request time,
        not that a later output write will succeed or remain race-free. No
        actor, document shell, generation run, binding, resolution log or
        storage output is created by this method.
        """
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case was not found.")
        try:
            # Manifest validation remains authoritative: do not fall back to
            # a different template or generic GxP if an asset is unsupported.
            get_inspection_ke_hoach_kt_output_filename(case.gxp_type)
        except InspectionKeHoachKtTemplateAssetContractError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        input_status = "blocked"
        template_status = "not_checked"
        folder_status = "not_checked"
        blockers: list[str] = []
        with session.no_autoflush:
            # Identical current-version predicate as typed and generic KHKT
            # CREATE, but without taking a FOR UPDATE lock in this GET probe.
            if self._current_openable_khkt_version_id(session, case_id=case.id):
                blockers.append("current_khkt_document_already_exists")
            try:
                canonical = load_inspection_ke_hoach_kt_payload_input(
                    session,
                    case_id=case.id,
                    generated_at=datetime.now(timezone.utc),
                )
            except (InspectionKeHoachKtPayloadInputError, DocumentPayloadBuildError):
                blockers.append("canonical_input_unavailable")
            else:
                input_status = "ready"
                request = DocumentGenerationRequest(
                    family_code=INSPECTION_KE_HOACH_KT_FAMILY,
                    requested_by_user_id=None,
                    case_id=case.id,
                    gxp_type=case.gxp_type,
                    language_code="vi",
                    storage_scope="inspection_folder",
                )
                try:
                    plan = plan_document_generation(
                        load_default_registry(),
                        request,
                        DocumentPayloadEnvelope(
                            family_code=INSPECTION_KE_HOACH_KT_FAMILY,
                            fields=(),
                            source_procedures=(),
                        ),
                    )
                    definition, binding = resolve_generation_template_metadata(
                        session, plan,
                    )
                    # Only these three properties are consumed by the exact
                    # template-readiness owner. No persistence state/run exists.
                    preview = SimpleNamespace(
                        generation_plan=plan,
                        persisted_state=SimpleNamespace(
                            template_definition_id=None if definition is None else definition.id,
                            template_binding_id=None if binding is None else binding.id,
                        ),
                        khkt_payload_input=canonical,
                    )
                    template = self._inspect_template_readiness(
                        session, storage, preview,
                    )
                    template_status = (
                        "ready" if template.readiness_status == "direct_stream_ready"
                        and template.scalar_replacement_mode == "khkt_contract_exact"
                        else "blocked"
                    )
                except (DocumentPersistenceError, DocumentTemplateSelectionError):
                    template_status = "blocked"
                if template_status != "ready":
                    blockers.append("template_binary_or_contract_unavailable")

            if storage is None:
                folder_status = "unavailable"
                blockers.append("storage_service_unavailable")
            else:
                try:
                    year, site_legacy_id, inspection_code = _load_case_storage_identity(
                        session, case.id,
                    )
                    folder = StorageBindingService(storage).preview_inspection_folder(
                        session,
                        case_id=case.id,
                        year=year,
                        site_legacy_id=site_legacy_id,
                        inspection_legacy_code=inspection_code,
                    )
                except (OutputVersionAllocationError, StorageOperationError, FileNotFoundError):
                    folder_status = "blocked"
                else:
                    folder_status = (
                        "ready"
                        if folder.resolution.status == StorageResolutionStatus.RESOLVED
                        else "blocked"
                    )
                if folder_status != "ready":
                    blockers.append("inspection_folder_unavailable")

        return {
            "case_id": case.id,
            "family_code": INSPECTION_KE_HOACH_KT_FAMILY,
            "gxp_type": case.gxp_type,
            "canonical_input_status": input_status,
            "template_binary_status": template_status,
            "inspection_folder_status": folder_status,
            "ready_to_attempt_render": (
                input_status == "ready"
                and template_status == "ready"
                and folder_status == "ready"
                and "current_khkt_document_already_exists" not in blockers
            ),
            "blocked_reasons": blockers,
        }

    def _build_generation_request(self, payload: dict[str, Any], user_id: str) -> DocumentGenerationRequest:
        return DocumentGenerationRequest(
            family_code=payload["family_code"],
            requested_by_user_id=user_id,
            case_id=payload.get("case_id"),
            capa_cycle_id=payload.get("capa_cycle_id"),
            certificate_id=payload.get("certificate_id"),
            business_eligibility_certificate_id=payload.get("business_eligibility_certificate_id"),
            change_request_id=payload.get("change_request_id"),
            gxp_type=payload.get("gxp_type"),
            legacy_mode=payload.get("legacy_mode"),
            storage_scope=payload.get("storage_scope"),
            language_code=payload.get("language_code") or "vi",
            idempotency_key=payload.get("idempotency_key"),
            payload=payload.get("payload"),
        )

    def _build_preparation_input(self, payload: dict[str, Any], user_id: str) -> DocumentPreparationInput:
        request = self._build_generation_request(payload, user_id)
        return DocumentPreparationInput(
            request=request,
            payload_values=dict(payload.get("payload") or {}),
            payload_notes=payload.get("payload_notes"),
            strict_payload=bool(payload.get("strict_payload", True)),
            copy_pt=bool(payload.get("copy_pt", False)),
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _resolve_render_output_filename(prepared, requested_output_filename: object) -> str:
        requested = str(requested_output_filename or "").strip()
        if prepared.generation_plan.template.family_code != INSPECTION_KE_HOACH_KT_FAMILY:
            return requested
        if prepared.khkt_payload_input is None:
            raise DocumentPayloadBuildError(
                "INSPECTION_KE_HOACH_KT canonical payload input is unavailable while resolving output filename."
            )
        try:
            canonical = get_inspection_ke_hoach_kt_output_filename(
                prepared.khkt_payload_input.gxp_type
            )
        except InspectionKeHoachKtTemplateAssetContractError as exc:
            raise DocumentPayloadBuildError(str(exc)) from exc
        if requested != canonical:
            raise DocumentPayloadBuildError(
                "INSPECTION_KE_HOACH_KT output filename is backend-owned by the exact "
                f"template variant; expected {canonical!r}."
            )
        return canonical

    def _load_template_definition(self, session: Session, template_definition_id: str | None) -> TemplateDefinition | None:
        if template_definition_id is None:
            return None
        return session.get(TemplateDefinition, template_definition_id)

    def _inspect_template_readiness(
        self,
        session: Session,
        storage: StorageServiceProtocol | None,
        prepared,
    ) -> TemplateReadiness:
        requirement = build_prepared_template_binary_requirement(session, prepared)
        if requirement.readiness_status != "direct_stream_ready":
            return TemplateReadiness(
                template_definition_id=requirement.template_definition_id,
                family_code=requirement.family_code,
                template_name=requirement.template_name,
                readiness_status=requirement.readiness_status,
                detail=requirement.detail,
                storage_root=requirement.storage_root,
                storage_relative_path=requirement.storage_relative_path,
                original_filename=requirement.original_filename,
                checksum_sha256=requirement.checksum_sha256,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        if storage is None:
            return TemplateReadiness(
                template_definition_id=requirement.template_definition_id,
                family_code=requirement.family_code,
                template_name=requirement.template_name,
                readiness_status="storage_service_unavailable",
                detail="StorageService is not available, so template bytes cannot be opened.",
                storage_root=requirement.storage_root,
                storage_relative_path=requirement.storage_relative_path,
                original_filename=requirement.original_filename,
                checksum_sha256=requirement.checksum_sha256,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        try:
            with open_template_binary_stream(storage, requirement) as stream:
                template_bytes = stream.read()
            if prepared.generation_plan.template.family_code == "INSPECTION_KE_HOACH_KT":
                from backend.app.document.inspection_ke_hoach_kt_effective_template_contract import (
                    InspectionKeHoachKtEffectiveTemplateContractError,
                    build_inspection_ke_hoach_kt_effective_template_contract,
                )

                if prepared.khkt_payload_input is None:
                    raise TemplateContractRuntimeError(
                        "KHKT canonical payload input is unavailable during template readiness."
                    )
                try:
                    contract = build_inspection_ke_hoach_kt_effective_template_contract(
                        gxp_type=prepared.khkt_payload_input.gxp_type,
                        template_bytes=template_bytes,
                    )
                except InspectionKeHoachKtEffectiveTemplateContractError as exc:
                    raise TemplateContractRuntimeError(str(exc)) from exc
                replacement_plan = type(
                    "_KhktReadinessPlan",
                    (),
                    {
                        "mode": "khkt_contract_exact",
                        "template_variant_key": contract.gxp_type,
                    },
                )()
            else:
                replacement_plan = build_scalar_replacement_plan_for_template(
                    load_default_template_contract_reconciliation(),
                    prepared.generation_plan.template.family_code,
                    prepared.payload_result.envelope.fields,
                    template_bytes=template_bytes,
                )
        except (TemplateContractRuntimeError, TemplateBinaryError, StorageOperationError, FileNotFoundError) as exc:
            return TemplateReadiness(
                template_definition_id=requirement.template_definition_id,
                family_code=requirement.family_code,
                template_name=requirement.template_name,
                readiness_status="runtime_contract_failed",
                detail=str(exc),
                storage_root=requirement.storage_root,
                storage_relative_path=requirement.storage_relative_path,
                original_filename=requirement.original_filename,
                checksum_sha256=requirement.checksum_sha256,
                scalar_replacement_mode=None,
                template_variant_key=None,
            )
        return TemplateReadiness(
            template_definition_id=requirement.template_definition_id,
            family_code=requirement.family_code,
            template_name=requirement.template_name,
            readiness_status="direct_stream_ready",
            detail=requirement.detail,
            storage_root=requirement.storage_root,
            storage_relative_path=requirement.storage_relative_path,
            original_filename=requirement.original_filename,
            checksum_sha256=requirement.checksum_sha256,
            scalar_replacement_mode=replacement_plan.mode,
            template_variant_key=replacement_plan.template_variant_key,
        )

    def _build_blocked_reasons(self, prepared, template_readiness: TemplateReadiness) -> list[str]:
        reasons: list[str] = []
        if not prepared.render_ready:
            for requirement in prepared.source_binary_requirements:
                if requirement.readiness_status != "direct_stream_ready":
                    reasons.append(
                        f"source_dependency:{requirement.source_family_code}:{requirement.readiness_status}"
                    )
        if prepared.generation_plan.template.source_application != "Word":
            reasons.append(f"source_application:{prepared.generation_plan.template.source_application}")
        if template_readiness.readiness_status != "direct_stream_ready":
            reasons.append(f"template:{template_readiness.readiness_status}")
        elif template_readiness.scalar_replacement_mode not in {"contract_exact", "contract_variant_exact", "khkt_contract_exact"}:
            reasons.append(f"template:{template_readiness.scalar_replacement_mode or 'unknown_mode'}")
        return reasons

    @staticmethod
    def _claim_reused_generation_run_for_render(
        session: Session,
        prepared: object,
    ) -> None:
        if not prepared.persisted_state.reused_generation_run:
            return
        generation_run_id = prepared.persisted_state.generation_run_id
        row = session.execute(
            select(DocumentGenerationRun)
            .where(DocumentGenerationRun.id == generation_run_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=409,
                detail="Reused document generation run no longer exists.",
            )
        session.refresh(row)
        if row.status == DocumentGenerationStatus.SUCCEEDED:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Document generation run already succeeded; open the current "
                    "document instead of rendering it again."
                ),
            )
        if row.status == DocumentGenerationStatus.CANCELLED:
            raise HTTPException(
                status_code=409,
                detail="Cancelled document generation run cannot be retried.",
            )
        if row.status == DocumentGenerationStatus.FAILED:
            row.status = DocumentGenerationStatus.PENDING
            row.error_summary = None
            session.flush()
            return
        if row.status == DocumentGenerationStatus.PENDING:
            return
        raise HTTPException(
            status_code=409,
            detail=f"Document generation run is not renderable from status {row.status.value!r}.",
        )

    _RENDER_FAILURE_COMMIT_KEY = "document.render_failure_state_ready_to_commit"

    def _mark_generation_run_failed(self, session: Session, generation_run_id: str, detail: str) -> None:
        row = session.get(DocumentGenerationRun, generation_run_id)
        if row is None:
            return
        row.status = DocumentGenerationStatus.FAILED
        row.error_summary = detail
        session.flush()
        # Only a successfully flushed failure transition is eligible for the
        # route's intentional error-response commit. Preflight conflicts must
        # still roll back through the normal session dependency.
        session.info[self._RENDER_FAILURE_COMMIT_KEY] = generation_run_id

    @classmethod
    def consume_render_failure_commit_request(cls, session: Session) -> bool:
        return bool(session.info.pop(cls._RENDER_FAILURE_COMMIT_KEY, None))

    def _serialize_generation_status(self, session: Session, generation_run_id: str) -> dict[str, Any]:
        row = session.get(DocumentGenerationRun, generation_run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document generation run not found.")
        dependencies = list(
            session.scalars(
                select(DocumentSourceDependency).where(
                    DocumentSourceDependency.document_generation_run_id == row.id
                )
            )
        )
        return {
            "generation_run_id": row.id,
            "document_id": row.document_id,
            "template_binding_id": row.template_binding_id,
            "template_definition_id": row.template_definition_id,
            "output_document_version_id": row.output_document_version_id,
            "status": row.status.value,
            "source_application": row.source_application,
            "requested_by_user_id": row.requested_by_user_id,
            "input_payload_redacted": None if row.input_payload_redacted is None else json.loads(row.input_payload_redacted),
            "error_summary": row.error_summary,
            "idempotency_key": row.idempotency_key,
            "source_dependencies": [
                {
                    "source_family_code": self._source_dependency_family_code(session, item.source_document_id),
                    "dependency_type": item.dependency_type,
                    "required_bookmarks": []
                    if item.source_bookmarks is None
                    else list(json.loads(item.source_bookmarks)),
                    "condition": item.notes,
                }
                for item in dependencies
            ],
        }

    def _source_dependency_family_code(self, session: Session, source_document_id: str) -> str:
        row = session.get(Document, source_document_id)
        return "unknown" if row is None else row.family_code

    def get_owner_document_metadata(
        self,
        session: Session,
        *,
        owner_kind: Literal["certificate", "business_eligibility_certificate"],
        owner_id: str,
    ) -> dict[str, Any]:
        """Inventory only canonical Document/Variant/Version ROWS, not binary evidence.

        Exact owner FK is the only selector. Neither Case adjacency nor DDK
        GxP source-cell hints are a substitute for explicit Document ownership.
        An ambiguous multi-owner document is an integrity error, not a match.
        """
        if owner_kind == "certificate":
            owner_type, owner_column = Certificate, Document.certificate_id
        elif owner_kind == "business_eligibility_certificate":
            owner_type, owner_column = (
                BusinessEligibilityCertificate, Document.business_eligibility_certificate_id
            )
        else:
            raise ValueError("Unknown canonical document owner kind.")

        if session.get(owner_type, owner_id) is None:
            raise HTTPException(status_code=404, detail="Document business owner not found.")

        documents = list(session.scalars(
            select(Document).where(owner_column == owner_id).order_by(Document.id)
        ))
        for row in documents:
            owners = {
                key: value
                for key, value in (
                    ("case", row.case_id),
                    ("capa_cycle", row.capa_cycle_id),
                    ("certificate", row.certificate_id),
                    ("business_eligibility_certificate", row.business_eligibility_certificate_id),
                    ("change_request", row.change_request_id),
                )
                if value is not None
            }
            if owners != {owner_kind: owner_id}:
                raise HTTPException(
                    status_code=409,
                    detail="Document has ambiguous canonical business ownership.",
                )

        document_ids = [doc.id for doc in documents]
        variants = (
            list(session.scalars(select(DocumentVariant).where(
                DocumentVariant.document_id.in_(document_ids)
            )))
            if document_ids else []
        )
        variant_document_id = {variant.id: variant.document_id for variant in variants}
        versions = (
            list(session.scalars(select(DocumentVersion).where(
                DocumentVersion.document_variant_id.in_(variant_document_id)
            )))
            if variant_document_id else []
        )
        counts = {doc_id: [0, 0, 0] for doc_id in document_ids}
        for variant in variants:
            counts[variant.document_id][0] += 1
        for version in versions:
            document_id = variant_document_id[version.document_variant_id]
            counts[document_id][1] += 1
            if version.is_current:
                counts[document_id][2] += 1

        return {
            "owner_kind": owner_kind,
            "owner_id": owner_id,
            "metadata_status": (
                "registered_metadata_only_unverified"
                if documents else "no_registered_document_metadata"
            ),
            # No file is opened, streamed, trusted, signed or storage-verified.
            "binary_verified": False,
            "original_signed_document_verified": False,
            "documents": [
                {
                    "document_id": doc.id,
                    "family_code": doc.family_code,
                    "document_type_code": doc.document_type_code,
                    "title": doc.title,
                    "registered_variant_count": counts[doc.id][0],
                    "registered_version_count": counts[doc.id][1],
                    "registered_current_version_count": counts[doc.id][2],
                }
                for doc in documents
            ],
        }

    def _serialize_document_detail(self, session: Session, document_id: str) -> dict[str, Any]:
        row = session.get(Document, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        variants = list(session.scalars(select(DocumentVariant).where(DocumentVariant.document_id == row.id)))
        runs = list(session.scalars(select(DocumentGenerationRun).where(DocumentGenerationRun.document_id == row.id)))
        return {
            "document_id": row.id,
            "family_code": row.family_code,
            "document_type_code": row.document_type_code,
            "title": row.title,
            "legacy_entity_type": None if row.legacy_entity_type is None else row.legacy_entity_type.value,
            "case_id": row.case_id,
            "capa_cycle_id": row.capa_cycle_id,
            "certificate_id": row.certificate_id,
            "business_eligibility_certificate_id": row.business_eligibility_certificate_id,
            "change_request_id": row.change_request_id,
            "variants": [
                {
                    "id": variant.id,
                    "variant_type": variant.variant_type.value,
                    "language_code": variant.language_code,
                    "is_active": variant.is_active,
                    "versions": [
                        {
                            "id": version.id,
                            "version_no": version.version_no,
                            "original_filename": version.original_filename,
                            "is_current": version.is_current,
                            "issued_on": version.issued_on,
                        }
                        for version in session.scalars(
                            select(DocumentVersion)
                            .where(DocumentVersion.document_variant_id == variant.id)
                            .order_by(DocumentVersion.version_no.asc())
                        )
                    ],
                }
                for variant in variants
            ],
            "generation_runs": [self._serialize_generation_status(session, run.id) for run in runs],
        }

    def prepare_generation(
        self,
        session: Session,
        *,
        storage: StorageServiceProtocol | None,
        payload: dict[str, Any],
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        if payload.get("family_code") == INSPECTION_KE_HOACH_KT_FAMILY:
            # Generic PREPARE is also a KHKT create entrypoint: it persists a
            # document shell and generation run even without rendering Word.
            # Reuse the exact typed/render Case lock and current-version owner
            # before creating an AppUser, run or audit event.
            case_id = payload.get("case_id")
            if not isinstance(case_id, str) or not case_id.strip():
                raise HTTPException(
                    status_code=409,
                    detail="INSPECTION_KE_HOACH_KT prepare requires canonical case_id.",
                )
            self.build_case_inspection_plan_render_payload(
                session,
                case_id=case_id,
                idempotency_key=payload.get("idempotency_key"),
            )
        actor = self._get_or_create_app_user(session, user)
        try:
            prepared = prepare_document_generation_job(
                session,
                self._build_preparation_input(payload, actor.id),
            )
        except (
            DocumentTemplateSelectionError,
            DocumentPayloadBuildError,
            DocumentPersistenceError,
            SourceBinaryContractError,
        ) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        template_readiness = self._inspect_template_readiness(session, storage, prepared)
        blocked_reasons = self._build_blocked_reasons(prepared, template_readiness)
        audit_event = self._write_audit_event(
            session,
            actor=actor,
            entity_type="document_generation_run",
            entity_id=prepared.persisted_state.generation_run_id,
            action="document.prepare",
            payload={
                "family_code": prepared.generation_plan.template.family_code,
                "document_id": prepared.persisted_state.document_id,
                "generation_run_id": prepared.persisted_state.generation_run_id,
                "render_ready": prepared.render_ready,
                "template_render_ready": not blocked_reasons,
                "blocked_reasons": blocked_reasons,
            },
        )
        session.flush()
        generation_run = session.get(DocumentGenerationRun, prepared.persisted_state.generation_run_id)
        if generation_run is None:
            raise HTTPException(status_code=500, detail="Prepared generation run disappeared unexpectedly.")
        return {
            "document_id": prepared.persisted_state.document_id,
            "document_variant_id": prepared.persisted_state.document_variant_id,
            "generation_run_id": prepared.persisted_state.generation_run_id,
            "generation_status": generation_run.status.value,
            "reused_generation_run": prepared.persisted_state.reused_generation_run,
            "render_ready": prepared.render_ready,
            "template_render_ready": len(blocked_reasons) == 0,
            "blocked_reasons": blocked_reasons,
            "selected_template": {
                "family_code": prepared.generation_plan.template.family_code,
                "logical_name": prepared.generation_plan.template.logical_name,
                "template_pattern": prepared.generation_plan.template.template_pattern,
                "source_application": prepared.generation_plan.template.source_application,
                "storage_scope": prepared.generation_plan.template.storage_scope,
                "host_procedure": prepared.generation_plan.template.host_procedure,
                "population_procedures": list(prepared.generation_plan.template.population_procedures),
                "notes": prepared.generation_plan.template.notes,
            },
            "payload_used_fields": list(prepared.payload_result.used_fields),
            "missing_registry_fields": list(prepared.payload_result.missing_registry_fields),
            "unexpected_input_fields": list(prepared.payload_result.unexpected_input_fields),
            "source_dependencies": [
                {
                    "source_family_code": item.source_family_code,
                    "dependency_type": item.dependency_type,
                    "required_bookmarks": list(item.required_bookmarks),
                    "condition": item.condition,
                }
                for item in prepared.generation_plan.source_dependencies
            ],
            "source_binary_requirements": [
                {
                    "source_document_id": item.source_document_id,
                    "source_document_version_id": item.source_document_version_id,
                    "source_family_code": item.source_family_code,
                    "readiness_status": item.readiness_status,
                    "detail": item.detail,
                    "storage_root": item.storage_root,
                    "folder_relative_path": item.folder_relative_path,
                    "exact_storage_root": item.exact_storage_root,
                    "exact_storage_relative_path": item.exact_storage_relative_path,
                    "original_filename": item.original_filename,
                    "required_bookmarks": list(item.required_bookmarks),
                    "legacy_filename_prefix_hints": list(item.legacy_filename_prefix_hints),
                }
                for item in prepared.source_binary_requirements
            ],
            "template_readiness": {
                "template_definition_id": template_readiness.template_definition_id,
                "family_code": template_readiness.family_code,
                "template_name": template_readiness.template_name,
                "readiness_status": template_readiness.readiness_status,
                "detail": template_readiness.detail,
                "storage_root": template_readiness.storage_root,
                "storage_relative_path": template_readiness.storage_relative_path,
                "original_filename": template_readiness.original_filename,
                "checksum_sha256": template_readiness.checksum_sha256,
                "scalar_replacement_mode": template_readiness.scalar_replacement_mode,
                "template_variant_key": template_readiness.template_variant_key,
            },
            "template_definition_id": prepared.persisted_state.template_definition_id,
            "template_binding_id": prepared.persisted_state.template_binding_id,
            "audit_event_id": audit_event.id,
        }

    def _cleanup_allocated_render_output(
        self,
        storage: StorageServiceProtocol,
        allocated: object | None,
        *,
        output_was_current_before_render: bool,
        expected_checksum: str | None,
    ) -> str | None:
        if (
            allocated is None
            or output_was_current_before_render
            or not str(expected_checksum or "").strip()
        ):
            return None
        allocation = allocated.allocated.output_allocation
        return cleanup_output_target_if_owned(
            storage,
            storage_root=allocation.storage_root,
            storage_relative_path=allocation.storage_relative_path,
            expected_checksum=str(expected_checksum),
        )

    @staticmethod
    def _capture_previous_current_version_ids(
        session: Session,
        allocated: object,
    ) -> tuple[str, ...]:
        allocation = allocated.allocated.output_allocation
        return tuple(
            row.id
            for row in session.scalars(
                select(DocumentVersion).where(
                    DocumentVersion.document_variant_id
                    == allocation.document_variant_id
                )
            )
            if row.id != allocation.document_version_id and row.is_current
        )

    @staticmethod
    def _restore_render_version_state(
        session: Session,
        allocated: object | None,
        previous_current_version_ids: tuple[str, ...],
        *,
        output_was_current_before_render: bool,
    ) -> None:
        if allocated is None or output_was_current_before_render:
            return
        allocation = allocated.allocated.output_allocation
        allocated_version = session.get(
            DocumentVersion,
            allocation.document_version_id,
        )
        if allocated_version is None or not allocated_version.is_current:
            return

        previous_ids = tuple(dict.fromkeys(previous_current_version_ids))
        if len(previous_ids) > 1:
            allocated_version.is_current = False
            allocated_version.checksum_sha256 = None
            allocated_version.issued_on = None
            session.flush()
            return

        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == allocation.document_version_id)
            .values(
                is_current=False,
                checksum_sha256=None,
                issued_on=None,
            )
        )
        if previous_ids:
            session.execute(
                update(DocumentVersion)
                .where(
                    DocumentVersion.id == previous_ids[0],
                    DocumentVersion.document_variant_id
                    == allocation.document_variant_id,
                )
                .values(is_current=True)
            )
        session.flush()

    def cleanup_render_output_after_commit_failure(
        self,
        storage: StorageServiceProtocol,
        render_result: dict[str, Any],
    ) -> str | None:
        if not bool(render_result.get("_rollback_cleanup_required")):
            return None
        return cleanup_output_target_if_owned(
            storage,
            storage_root=str(render_result["output_storage_root"]),
            storage_relative_path=str(render_result["output_storage_relative_path"]),
            expected_checksum=str(render_result.get("checksum_sha256") or ""),
        )

    def render_template_docx(
        self,
        session: Session,
        *,
        storage: StorageServiceProtocol | None,
        payload: dict[str, Any],
        user: AuthenticatedUser,
    ) -> dict[str, Any]:
        if storage is None:
            raise HTTPException(status_code=503, detail="StorageService is unavailable for document rendering.")
        render_payload = dict(payload)
        if render_payload.get("family_code") == INSPECTION_KE_HOACH_KT_FAMILY:
            # The generic Word renderer is also a KHKT writer. Apply exactly
            # the typed Case CREATE guard before creating an actor, generation
            # run, output allocation or storage write. The Case lock remains
            # held by this transaction through the route's render commit.
            case_id = render_payload.get("case_id")
            if not isinstance(case_id, str) or not case_id.strip():
                raise HTTPException(
                    status_code=409,
                    detail="INSPECTION_KE_HOACH_KT render requires canonical case_id.",
                )
            self.build_case_inspection_plan_render_payload(
                session,
                case_id=case_id,
                idempotency_key=render_payload.get("idempotency_key"),
            )
        actor = self._get_or_create_app_user(session, user)
        if not render_payload.get("idempotency_key"):
            render_payload["idempotency_key"] = f"render-{uuid4()}"
        prepared = None
        allocated = None
        render_claimed = False
        output_was_current_before_render = True
        rendered_checksum: str | None = None
        previous_current_version_ids: tuple[str, ...] = ()
        try:
            preparation_input = self._build_preparation_input(render_payload, actor.id)
            prepared = prepare_document_generation_job(
                session,
                preparation_input,
            )
            self._claim_reused_generation_run_for_render(
                session,
                prepared,
            )
            render_claimed = True
            output_filename = self._resolve_render_output_filename(
                prepared,
                render_payload.get("output_filename"),
            )
            template_readiness = self._inspect_template_readiness(session, storage, prepared)
            blocked_reasons = self._build_blocked_reasons(prepared, template_readiness)
            if blocked_reasons:
                detail = "Document family is not render-safe: " + ", ".join(blocked_reasons)
                raise HTTPException(status_code=409, detail=detail)
            allocated = allocate_prepared_template_aware_docx_generation(
                session,
                storage,
                prepared,
                output_filename=output_filename,
            )
            allocated_version = session.get(
                DocumentVersion,
                allocated.allocated.output_allocation.document_version_id,
            )
            if allocated_version is None:
                raise OutputVersionAllocationError(
                    "Allocated document version disappeared before render."
                )
            output_was_current_before_render = bool(allocated_version.is_current)
            if not output_was_current_before_render:
                previous_current_version_ids = self._capture_previous_current_version_ids(
                    session,
                    allocated,
                )
            result = render_template_aware_docx_and_finalize(session, storage, allocated)
            rendered_checksum = result.checksum_sha256
            audit_event = self._write_audit_event(
                session,
                actor=actor,
                entity_type="document_generation_run",
                entity_id=result.generation_run_id,
                action="document.render_template_docx",
                payload={
                    "document_version_id": result.document_version_id,
                    "generation_run_id": result.generation_run_id,
                    "checksum_sha256": result.checksum_sha256,
                    "scalar_replacement_mode": result.scalar_replacement_mode,
                    "template_variant_key": result.template_variant_key,
                },
            )
            session.flush()
            document_version = session.get(DocumentVersion, result.document_version_id)
            if (
                document_version is None
                or document_version.storage_root is None
                or document_version.storage_relative_path is None
            ):
                raise HTTPException(
                    status_code=500,
                    detail="Rendered document version locator is incomplete.",
                )
            generation_run = session.get(DocumentGenerationRun, result.generation_run_id)
            if generation_run is None:
                raise HTTPException(
                    status_code=500,
                    detail="Rendered generation run disappeared unexpectedly.",
                )
            return {
                "document_id": generation_run.document_id,
                "document_variant_id": document_version.document_variant_id,
                "document_version_id": result.document_version_id,
                "generation_run_id": result.generation_run_id,
                "generation_status": generation_run.status.value,
                "output_storage_root": document_version.storage_root,
                "output_storage_relative_path": document_version.storage_relative_path,
                "output_original_filename": document_version.original_filename,
                "checksum_sha256": result.checksum_sha256,
                "byte_size": result.byte_size,
                "scalar_replacement_mode": result.scalar_replacement_mode,
                "template_variant_key": result.template_variant_key,
                "replaced_bookmarks": list(result.replaced_bookmarks),
                "replaced_table_regions": list(result.replaced_table_regions),
                "replaced_parts": list(result.replaced_parts),
                "audit_event_id": audit_event.id,
                "_rollback_cleanup_required": not output_was_current_before_render,
            }
        except HTTPException as exc:
            cleanup_error = self._cleanup_allocated_render_output(
                storage,
                allocated,
                output_was_current_before_render=output_was_current_before_render,
                expected_checksum=rendered_checksum,
            )
            if session.is_active:
                self._restore_render_version_state(
                    session,
                    allocated,
                    previous_current_version_ids,
                    output_was_current_before_render=output_was_current_before_render,
                )
            detail = str(exc.detail)
            if cleanup_error is not None:
                detail += f" Output cleanup failed: {cleanup_error}"
            if render_claimed and prepared is not None and session.is_active:
                self._mark_generation_run_failed(
                    session,
                    prepared.persisted_state.generation_run_id,
                    detail,
                )
            if cleanup_error is not None:
                raise HTTPException(status_code=500, detail=detail) from exc
            raise
        except (
            DocumentTemplateSelectionError,
            DocumentPayloadBuildError,
            DocumentPersistenceError,
            OutputVersionAllocationError,
            SourceBinaryContractError,
            TemplateBinaryError,
            TemplateContractRuntimeError,
            DocxTemplateRenderError,
            StorageOperationError,
        ) as exc:
            cleanup_error = (
                None
                if isinstance(exc, StorageTargetExistsError)
                else self._cleanup_allocated_render_output(
                    storage,
                    allocated,
                    output_was_current_before_render=output_was_current_before_render,
                    expected_checksum=rendered_checksum,
                )
            )
            if session.is_active:
                self._restore_render_version_state(
                    session,
                    allocated,
                    previous_current_version_ids,
                    output_was_current_before_render=output_was_current_before_render,
                )
            detail = str(exc)
            if cleanup_error is not None:
                detail += f" Output cleanup failed: {cleanup_error}"
            if prepared is not None and session.is_active:
                self._mark_generation_run_failed(
                    session,
                    prepared.persisted_state.generation_run_id,
                    detail,
                )
            status_code = 500 if cleanup_error is not None else 409
            raise HTTPException(status_code=status_code, detail=detail) from exc
        except Exception as exc:
            cleanup_error = self._cleanup_allocated_render_output(
                storage,
                allocated,
                output_was_current_before_render=output_was_current_before_render,
                expected_checksum=rendered_checksum,
            )
            if session.is_active:
                self._restore_render_version_state(
                    session,
                    allocated,
                    previous_current_version_ids,
                    output_was_current_before_render=output_was_current_before_render,
                )
            detail = str(exc)
            if cleanup_error is not None:
                detail += f" Output cleanup failed: {cleanup_error}"
            if prepared is not None and session.is_active:
                self._mark_generation_run_failed(
                    session,
                    prepared.persisted_state.generation_run_id,
                    detail,
                )
            if cleanup_error is not None:
                raise RuntimeError(detail) from exc
            raise

    def get_generation_run(self, session: Session, generation_run_id: str) -> dict[str, Any]:
        return self._serialize_generation_status(session, generation_run_id)

    def get_document(self, session: Session, document_id: str) -> dict[str, Any]:
        return self._serialize_document_detail(session, document_id)

    def get_current_document_binary_locator_for_parent(
        self,
        session: Session,
        *,
        document_id: str,
        expected_parent_scope: DocumentBinaryParentScope,
        expected_parent_id: str,
        expected_case_id: str | None = None,
    ) -> DocumentBinaryLocator:
        row = session.get(Document, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        parent_ids = {
            scope: parent_id
            for scope, parent_id in {
                "case": row.case_id,
                "capa_cycle": row.capa_cycle_id,
                "certificate": row.certificate_id,
                "business_eligibility_certificate": row.business_eligibility_certificate_id,
                "change_request": row.change_request_id,
            }.items()
            if parent_id is not None
        }
        if parent_ids != {expected_parent_scope: expected_parent_id}:
            raise HTTPException(status_code=404, detail="Document not found for requested business owner.")
        if expected_parent_scope == "case":
            if session.get(Case, expected_parent_id) is None:
                raise HTTPException(status_code=404, detail="Case not found.")
        else:
            cycle = session.get(CapaCycle, expected_parent_id)
            if cycle is None:
                raise HTTPException(status_code=404, detail="CAPA cycle not found.")
            if expected_case_id is None or cycle.case_id != expected_case_id:
                raise HTTPException(status_code=404, detail="CAPA cycle not found for requested case.")
            if session.get(Case, expected_case_id) is None:
                raise HTTPException(status_code=404, detail="Case not found.")
        variants = list(
            session.scalars(
                select(DocumentVariant)
                .where(DocumentVariant.document_id == row.id)
                .order_by(DocumentVariant.id)
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        )
        # Lock every variant, including retired ones, so concurrent status
        # changes cannot alter the eligible set during binary verification.
        # Only active variants may supply the current binary.
        active_variants = [variant for variant in variants if variant.is_active]
        versions = [
            version
            for variant in active_variants
            for version in session.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.document_variant_id == variant.id)
                .execution_options(populate_existing=True)
            )
        ]
        document_version = self._pick_current_document_version(versions)
        if document_version is None:
            raise HTTPException(status_code=409, detail="Document does not have a current binary version.")
        if not all(
            value is not None and value.strip()
            for value in (
                document_version.storage_root,
                document_version.storage_relative_path,
                document_version.original_filename,
                document_version.checksum_sha256,
            )
        ):
            raise HTTPException(status_code=409, detail="Document current version locator is incomplete.")
        media_type, _ = mimetypes.guess_type(document_version.original_filename)
        return DocumentBinaryLocator(
            document_id=row.id,
            document_version_id=document_version.id,
            storage_root=document_version.storage_root,
            storage_relative_path=document_version.storage_relative_path,
            original_filename=document_version.original_filename,
            checksum_sha256=document_version.checksum_sha256,
            media_type=media_type or "application/octet-stream",
        )

    @staticmethod
    def _pick_current_document_version(versions: list[DocumentVersion]) -> DocumentVersion | None:
        current_versions = [row for row in versions if row.is_current]
        if not current_versions:
            return None

        current_counts_by_variant: dict[str, int] = {}
        for row in current_versions:
            current_counts_by_variant[row.document_variant_id] = (
                current_counts_by_variant.get(row.document_variant_id, 0) + 1
            )
        if any(count > 1 for count in current_counts_by_variant.values()):
            raise HTTPException(
                status_code=409,
                detail="Document variant has multiple current binary versions.",
            )

        return max(
            current_versions,
            key=lambda row: (
                all(
                    value is not None and value.strip()
                    for value in (
                        row.storage_root,
                        row.storage_relative_path,
                        row.original_filename,
                        row.checksum_sha256,
                    )
                ),
                row.issued_on or row.created_at,
                row.version_no,
                row.id,
            ),
        )
