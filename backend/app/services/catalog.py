from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import String, and_, cast, func, literal, or_, select, true, union_all
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_readable_scope
from backend.app.domain.legacy_certificate_search_quarantine import is_witnessed_historical_search_quarantine
from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.document.contextual_actions import (
    build_case_contextual_document_specs,
    build_document_action_states,
    get_case_document_context_spec,
    list_case_document_labels,
    KHKT_CASE_TYPED_RENDER_ROUTE,
)
from backend.app.rbac import ROLE_PERMISSIONS
from backend.app.document.service_contract import load_default_registry
from backend.app.document.inspection_ke_hoach_kt_payload_input import (
    InspectionKeHoachKtPayloadInputError,
    load_inspection_ke_hoach_kt_payload_input,
)
from backend.app.document.payload_builders import DocumentPayloadBuildError
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    INSPECTION_KE_HOACH_KT_FAMILY,
    SUPPORTED_GXP_TYPES as KHKT_SUPPORTED_GXP_TYPES,
    get_inspection_ke_hoach_kt_output_filename,
)
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityGxpSourceGroup,
    BusinessEligibilityGxpReferenceEvidence,
    BusinessEligibilityVersion,
    Case,
    CaseCertificateNonissuanceDecision,
    CaseEvaluationScope,
    CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection,
    CaseEvaluationScopeUnkeyedEntry,
    CaseApplication,
    CaseAssessment,
    CapaCycle,
    Certificate,
    CertificateScope,
    CertificateVersion,
    ChangeApproval,
    ChangeRequest,
    ChangeRequestAffectedArtifact,
    ChangeRequestDetail,
    ChangeRequestIssuedArtifact,
    Company,
    Document,
    DocumentVariant,
    DocumentVersion,
    InspectionEvent,
    InspectionPlan,
    InspectionApprovalSubmission,
    InspectionApprovalDocumentLink,
    InspectionOutcome,
    InspectionPeriodSegment,
    InspectionTeam,
    InspectionTeamMember,
    InspectionTeamParticipantCatalog,
    InspectorProfile,
    Person,
    ProductionLine,
    Site,
    EvaluationScopeTaxonomyNode,
)
from backend.app.db.enums import InspectionEventType
from backend.app.services.workflow import CaseWorkflowService, inspection_team_existing_identity_state

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
    production_line_id: str | None = None
    production_line_code: str | None = None
    production_line_identity_state: str = "facility_wide"
    scope_summary: str | None = None


@dataclass(frozen=True)
class DocumentChecklistDefinition:
    checklist_key: str
    label: str
    family_code: str | None
    parent_scope: str
    parent_id: str


CASE_DOCUMENT_FAMILY_LABELS = {
    **list_case_document_labels(),
}

CHANGE_REQUEST_DOCUMENT_FAMILY_LABELS = {
    "NAME_ADDRESS_CHANGE_LETTER": "Đổi tên, địa chỉ",
    "CHANGE_REPORT_ROUTE_LETTER": "Đánh giá thay đổi",
    "CONSENT_CHANGE_LETTER": "CV đồng ý thay đổi",
}


class CatalogReadService:
    @staticmethod
    def _serialize_evaluation_scope(session: Session, *, case: Case) -> dict[str, object]:
        scope = session.scalar(
            select(CaseEvaluationScope).where(CaseEvaluationScope.case_id == case.id)
        )
        terminal = case.state in {CaseState.CLOSED, CaseState.CANCELLED}
        if scope is None:
            return {
                "id": None,
                "row_version": None,
                "source_classification": None,
                "rendered_prose": None,
                "summary_text": None,
                "summary_source": None,
                "limitation_text": None,
                "editable": False,
                "read_only_reason": "Chưa có phạm vi đánh giá canonical cho hồ sơ này.",
                "taxonomy_version_id": None,
                "gxp_type": case.gxp_type,
                "blocks": [],
                "taxonomy_nodes": [],
            }

        blocks = list(
            session.scalars(
                select(CaseEvaluationScopeBlock)
                .where(CaseEvaluationScopeBlock.case_evaluation_scope_id == scope.id)
                .order_by(CaseEvaluationScopeBlock.ordinal.asc(), CaseEvaluationScopeBlock.id.asc())
            )
        )
        block_ids = [block.id for block in blocks]
        selections_by_block: dict[str, list[dict[str, object]]] = defaultdict(list)
        unkeyed_by_block: dict[str, list[dict[str, object]]] = defaultdict(list)
        if block_ids:
            for row in session.scalars(
                select(CaseEvaluationScopeSelection)
                .where(CaseEvaluationScopeSelection.block_id.in_(block_ids))
                .order_by(CaseEvaluationScopeSelection.block_id.asc(), CaseEvaluationScopeSelection.source_order.asc())
            ):
                selections_by_block[row.block_id].append(
                    {
                        "taxonomy_node_id": row.taxonomy_node_id,
                        "node_key_snapshot": row.node_key_snapshot,
                        "taxonomy_description_snapshot": row.taxonomy_description_snapshot,
                        "custom_description": row.custom_description,
                        "source_order": row.source_order,
                    }
                )
            for row in session.scalars(
                select(CaseEvaluationScopeUnkeyedEntry)
                .where(CaseEvaluationScopeUnkeyedEntry.block_id.in_(block_ids))
                .order_by(CaseEvaluationScopeUnkeyedEntry.block_id.asc(), CaseEvaluationScopeUnkeyedEntry.source_order.asc())
            ):
                unkeyed_by_block[row.block_id].append({"source_order": row.source_order, "text": row.text})

        nodes: list[dict[str, object]] = []
        if scope.taxonomy_version_id is not None:
            rows = list(
                session.scalars(
                    select(EvaluationScopeTaxonomyNode)
                    .where(
                        EvaluationScopeTaxonomyNode.taxonomy_version_id == scope.taxonomy_version_id,
                        EvaluationScopeTaxonomyNode.gxp_type == case.gxp_type,
                    )
                    .order_by(EvaluationScopeTaxonomyNode.source_order.asc(), EvaluationScopeTaxonomyNode.id.asc())
                )
            )
            keys = {row.id: row.node_key for row in rows}
            nodes = [
                {
                    "id": row.id,
                    "key": row.node_key,
                    "parent_id": row.parent_node_id,
                    "parent_key": None if row.parent_node_id is None else keys.get(row.parent_node_id),
                    "description": row.description,
                    "hint": row.hint,
                    "main_topic": row.main_topic,
                    "short_render": row.short_render,
                    "no_expand": row.no_expand,
                    "source_order": row.source_order,
                }
                for row in rows
            ]

        node_key_by_id = {str(node["id"]): str(node["key"]) for node in nodes}
        prose_only = scope.source_classification == "PROSE_ONLY"
        serialized_blocks = [
            {
                "id": block.id,
                "ordinal": block.ordinal,
                "name": block.name,
                "note": block.note,
                "selections": selections_by_block[block.id],
                "unkeyed_entries": unkeyed_by_block[block.id],
            }
            for block in blocks
        ]
        # Imported legacy prose remains evidence.  Once an operator changes the
        # aggregate, project the current canonical selections instead of showing
        # the stale import-era string.
        summary_source = "historical_prose" if prose_only else "legacy_rendered_prose" if scope.row_version == 1 and scope.rendered_prose else "canonical_projection"
        summary_text = (
            scope.rendered_prose
            if summary_source in {"historical_prose", "legacy_rendered_prose"}
            else compile_vba_readable_scope(
                blocks=[
                    {
                        "id": block["id"],
                        "ordinal": block["ordinal"],
                        "name": block["name"],
                        "note": block["note"],
                        "selections": [
                            {**selection, "key": node_key_by_id[str(selection["taxonomy_node_id"])]}
                            for selection in block["selections"]
                        ],
                    }
                    for block in serialized_blocks
                ],
                taxonomy_nodes=nodes,
                limitation_text=scope.limitation_text,
                gxp_type=case.gxp_type,
            ).text
        )
        has_unkeyed_entries = any(unkeyed_by_block.values())
        read_only_reason = (
            "Phạm vi lịch sử dạng văn bản chỉ đọc."
            if prose_only
            else "Phạm vi có mục lịch sử chưa gắn taxonomy; chưa có contract VBA để chỉnh sửa các mục này."
            if has_unkeyed_entries
            else "Hồ sơ đã ở trạng thái kết thúc."
            if terminal
            else None
        )
        return {
            "id": scope.id,
            "row_version": scope.row_version,
            "source_classification": scope.source_classification,
            "rendered_prose": scope.rendered_prose,
            "summary_text": summary_text,
            "summary_source": summary_source,
            "limitation_text": scope.limitation_text,
            "editable": not terminal and not prose_only and not has_unkeyed_entries and scope.source_classification == "STRUCTURED_VALID",
            "read_only_reason": read_only_reason,
            "taxonomy_version_id": scope.taxonomy_version_id,
            "gxp_type": case.gxp_type,
            "blocks": serialized_blocks,
            "taxonomy_nodes": nodes,
        }

    @staticmethod
    def _effective_permissions(user: AuthenticatedUser) -> frozenset[str]:
        if user.permissions:
            return user.permissions
        derived: set[str] = set()
        for role_code in user.role_codes:
            derived.update(ROLE_PERMISSIONS.get(role_code, frozenset()))
        return frozenset(derived)

    @staticmethod
    def _person_display_name(person: Person) -> str:
        return person.display_name or person.full_name

    def list_inspection_team_identity_options(self, session: Session) -> list[dict[str, object]]:
        # A Person with an InspectorProfile has one runtime identity: the profile.
        # Keeping it out of the generic compatibility list prevents duplicate and
        # inactive-inspector paths around the profile activity rule.
        people = list(
            session.scalars(
                select(Person)
                .outerjoin(InspectorProfile, InspectorProfile.person_id == Person.id)
                .where(InspectorProfile.id.is_(None))
                .order_by(Person.full_name.asc(), Person.id.asc())
            )
        )
        profiles = list(
            session.execute(
                select(InspectorProfile, Person)
                .join(Person, Person.id == InspectorProfile.person_id)
                .where(InspectorProfile.is_active.is_(True))
                .order_by(InspectorProfile.is_active.desc(), Person.full_name.asc(), InspectorProfile.id.asc())
            ).all()
        )
        catalogs = list(session.scalars(select(InspectionTeamParticipantCatalog).where(InspectionTeamParticipantCatalog.is_active.is_(True)).order_by(InspectionTeamParticipantCatalog.code.asc(), InspectionTeamParticipantCatalog.id.asc())))
        return [
            *[
                {
                    "identity_kind": "inspector_profile",
                    "inspector_profile_id": profile.id,
                    "person_id": profile.person_id,
                    "display_name": self._person_display_name(person),
                    "is_active": profile.is_active,
                }
                for profile, person in profiles
            ],
            *[
                {
                    "identity_kind": "person",
                    "inspector_profile_id": None,
                    "person_id": person.id,
                    "display_name": self._person_display_name(person),
                    "is_active": None,
                }
                for person in people
            ],
            *[
                {
                    "identity_kind": "organization_representative",
                    "inspector_profile_id": None,
                    "person_id": None,
                    "participant_catalog_id": item.id,
                    "code": item.code,
                    "display_name": item.display_name,
                    "is_active": item.is_active,
                }
                for item in catalogs
            ],
        ]

    @staticmethod
    @lru_cache(maxsize=1)
    def _document_registry_labels() -> dict[str, str]:
        labels: dict[str, str] = {}
        for entry in load_default_registry():
            labels.setdefault(entry.family_code, entry.logical_name)
        labels.update(CASE_DOCUMENT_FAMILY_LABELS)
        labels.update(CHANGE_REQUEST_DOCUMENT_FAMILY_LABELS)
        return labels

    @staticmethod
    def _normalize_line_code(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _line_identity(*, site_id: str, production_line_id: str | None, raw_line_code: str | None, lines: dict[str, ProductionLine]) -> tuple[str | None, str | None, str]:
        if production_line_id is not None:
            line = lines.get(production_line_id)
            if line is None:
                raise HTTPException(status_code=409, detail="Canonical ProductionLine reference is missing.")
            if line.site_id != site_id:
                raise HTTPException(status_code=409, detail="Canonical ProductionLine reference belongs to a different site.")
            return line.id, line.code, "canonical"
        line_code = CatalogReadService._normalize_line_code(raw_line_code)
        return None, line_code, "legacy_unlinked" if line_code is not None else "facility_wide"

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
    def _build_search_result_key(
        site_id: str,
        *,
        gxp_type: str | None,
        identity_state: str,
        production_line_id: str | None,
        line_code: str | None,
    ) -> str:
        """Keep canonical search contexts distinct even when legacy codes coincide."""
        discriminator = production_line_id if identity_state == "canonical" else line_code or ""
        return f"{site_id}:{gxp_type or ''}:{identity_state}:{discriminator}"

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
                item.certificate.latest_flag,
                item.version.issue_date or date.min,
                item.version.expiry_date or date.max,
                item.certificate.updated_at,
            ),
        )

    @staticmethod
    def _history_order_key(
        *,
        occurred_on: date | None,
        created_at: datetime,
        updated_at: datetime,
        source_type: str,
        reference_code: str | None,
        item_id: str,
    ) -> tuple[date, datetime, datetime, int, str, str]:
        effective_date = occurred_on or created_at.date()
        source_rank = 1 if source_type == "case" else 0
        return (
            effective_date,
            created_at,
            updated_at,
            source_rank,
            reference_code or "",
            item_id,
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
        if not row.certificate.latest_flag:
            return "superseded"
        return "active"

    @staticmethod
    def _describe_certificate_source(
        *,
        certificate: Certificate,
        linked_case: Case | None,
        inspected_on: date | None,
    ) -> str | None:
        if linked_case is not None:
            if inspected_on is not None:
                return f"Đợt kiểm tra {linked_case.gxp_type} ngày {inspected_on.strftime('%d-%m-%Y')}"
            if linked_case.legacy_inspection_code:
                return f"Đợt kiểm tra {linked_case.gxp_type} {linked_case.legacy_inspection_code}"
            return f"Đợt kiểm tra {linked_case.gxp_type}"
        if certificate.issuance_basis == "administrative_no_inspection":
            return "Cấp hành chính không gắn đợt kiểm tra"
        return None

    @staticmethod
    def _pick_document_version(versions: list[DocumentVersion]) -> DocumentVersion | None:
        if not versions:
            return None
        current_versions = [row for row in versions if row.is_current]
        candidates = current_versions or versions
        return max(
            candidates,
            key=lambda row: (
                row.is_current
                and all(
                    value is not None and value.strip()
                    for value in (
                        row.storage_root,
                        row.storage_relative_path,
                        row.original_filename,
                        row.checksum_sha256,
                    )
                ),
                row.is_current,
                row.issued_on or row.created_at,
                row.version_no,
                row.id,
            ),
        )

    @staticmethod
    def _document_version_open_available(version: DocumentVersion | None) -> bool:
        if version is None or not version.is_current:
            return False
        return all(
            value is not None and value.strip()
            for value in (
                version.storage_root,
                version.storage_relative_path,
                version.original_filename,
                version.checksum_sha256,
            )
        )

    @staticmethod
    def _document_parent_pairs(document: Document) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if document.case_id is not None:
            pairs.append(("case", document.case_id))
        if document.capa_cycle_id is not None:
            pairs.append(("capa_cycle", document.capa_cycle_id))
        if document.change_request_id is not None:
            pairs.append(("change_request", document.change_request_id))
        return pairs

    def _serialize_document_checklist_items(
        self,
        session: Session,
        *,
        definitions: list[DocumentChecklistDefinition],
    ) -> list[dict[str, object]]:
        if not definitions:
            return []

        case_ids = sorted({item.parent_id for item in definitions if item.parent_scope == "case"})
        capa_cycle_ids = sorted({item.parent_id for item in definitions if item.parent_scope == "capa_cycle"})
        change_request_ids = sorted({item.parent_id for item in definitions if item.parent_scope == "change_request"})

        conditions = []
        if case_ids:
            conditions.append(Document.case_id.in_(case_ids))
        if capa_cycle_ids:
            conditions.append(Document.capa_cycle_id.in_(capa_cycle_ids))
        if change_request_ids:
            conditions.append(Document.change_request_id.in_(change_request_ids))

        documents = list(session.scalars(select(Document).where(or_(*conditions)))) if conditions else []
        allowed_parents = {(item.parent_scope, item.parent_id) for item in definitions}
        definition_keys = {
            (item.parent_scope, item.parent_id, item.family_code)
            for item in definitions
            if item.family_code is not None
        }
        documents_by_key: dict[tuple[str, str, str], list[Document]] = defaultdict(list)
        for row in documents:
            matching_keys = [
                (parent_scope, parent_id, row.family_code)
                for parent_scope, parent_id in self._document_parent_pairs(row)
                if (parent_scope, parent_id) in allowed_parents
            ]
            if not matching_keys:
                continue
            exact_matching_keys = [key for key in matching_keys if key in definition_keys]
            for key in exact_matching_keys or matching_keys:
                documents_by_key[key].append(row)

        document_ids = [row.id for row in documents]
        variants = (
            list(session.scalars(select(DocumentVariant).where(DocumentVariant.document_id.in_(document_ids))))
            if document_ids
            else []
        )
        variants_by_document_id: dict[str, list[DocumentVariant]] = defaultdict(list)
        for row in variants:
            variants_by_document_id[row.document_id].append(row)

        variant_ids = [row.id for row in variants]
        versions = (
            list(session.scalars(select(DocumentVersion).where(DocumentVersion.document_variant_id.in_(variant_ids))))
            if variant_ids
            else []
        )
        versions_by_variant_id: dict[str, list[DocumentVersion]] = defaultdict(list)
        for row in versions:
            versions_by_variant_id[row.document_variant_id].append(row)

        def select_best_document(candidates: list[Document]) -> tuple[Document | None, DocumentVersion | None, list[str]]:
            best_document: Document | None = None
            best_version: DocumentVersion | None = None
            best_variant_types: list[str] = []
            best_key = None
            for candidate in candidates:
                candidate_variants = variants_by_document_id.get(candidate.id, [])
                candidate_versions = [
                    version
                    for variant in candidate_variants
                    for version in versions_by_variant_id.get(variant.id, [])
                ]
                selected_version = self._pick_document_version(candidate_versions)
                variant_types = sorted({variant.variant_type.value for variant in candidate_variants if variant.variant_type})
                sort_key = (
                    self._document_version_open_available(selected_version),
                    selected_version is not None,
                    False if selected_version is None or selected_version.issued_on is None else True,
                    date.min if selected_version is None or selected_version.issued_on is None else selected_version.issued_on.date(),
                    candidate.updated_at,
                    candidate.id,
                )
                if best_key is None or sort_key > best_key:
                    best_document = candidate
                    best_version = selected_version
                    best_variant_types = variant_types
                    best_key = sort_key
            return best_document, best_version, best_variant_types

        labels = self._document_registry_labels()
        items: list[dict[str, object]] = []

        for definition in definitions:
            matched_documents = (
                documents_by_key.get((definition.parent_scope, definition.parent_id, definition.family_code), [])
                if definition.family_code
                else []
            )
            best_document, best_version, variant_types = select_best_document(matched_documents)
            items.append(
                {
                    "checklist_key": definition.checklist_key,
                    "label": definition.label,
                    "family_code": definition.family_code,
                    "parent_scope": definition.parent_scope,
                    "parent_id": definition.parent_id,
                    "status": "available" if best_document is not None else "missing",
                    "document_id": None if best_document is None else best_document.id,
                    "document_type_code": None if best_document is None else best_document.document_type_code,
                    "title": None if best_document is None else best_document.title,
                    "original_filename": None if best_version is None else best_version.original_filename,
                    "issued_on": None if best_version is None else best_version.issued_on,
                    "available_variant_types": variant_types,
                    "detail_available": best_document is not None,
                    "open_available": self._document_version_open_available(best_version),
                }
            )

        for parent_scope, parent_id, family_code in sorted(
            key for key in documents_by_key if key not in definition_keys
        ):
            matched_documents = documents_by_key[(parent_scope, parent_id, family_code)]
            best_document, best_version, variant_types = select_best_document(matched_documents)
            if best_document is None:
                continue
            checklist_key = f"{parent_scope}:{parent_id}:{family_code}"
            items.append(
                {
                    "checklist_key": checklist_key,
                    "label": labels.get(family_code, best_document.title or family_code),
                    "family_code": family_code,
                    "parent_scope": parent_scope,
                    "parent_id": parent_id,
                    "status": "available",
                    "document_id": best_document.id,
                    "document_type_code": best_document.document_type_code,
                    "title": best_document.title,
                    "original_filename": None if best_version is None else best_version.original_filename,
                    "issued_on": None if best_version is None else best_version.issued_on,
                    "available_variant_types": variant_types,
                    "detail_available": True,
                    "open_available": self._document_version_open_available(best_version),
                }
            )

        items.sort(
            key=lambda item: (
                item["parent_scope"],
                item["label"],
                item["family_code"] or "",
                item["parent_id"],
                item["checklist_key"],
            )
        )
        return items

    def _build_case_document_checklist(
        self,
        session: Session,
        *,
        case_id: str,
        capa_cycles: list[CapaCycle],
    ) -> dict[str, object]:
        definitions = [
            DocumentChecklistDefinition(
                checklist_key=f"case:{case_id}:{family_code}",
                label=label,
                family_code=family_code,
                parent_scope="case",
                parent_id=case_id,
            )
            for family_code, label in CASE_DOCUMENT_FAMILY_LABELS.items()
            if (spec := get_case_document_context_spec(family_code)) is None or spec.parent_scope == "case"
        ]
        for cycle in capa_cycles:
            if cycle.round_no == 1:
                definitions.append(
                    DocumentChecklistDefinition(
                        checklist_key=f"capa_cycle:{cycle.id}:INSPECTION_CAPA_LAN_1",
                        label=CASE_DOCUMENT_FAMILY_LABELS["INSPECTION_CAPA_LAN_1"],
                        family_code="INSPECTION_CAPA_LAN_1",
                        parent_scope="capa_cycle",
                        parent_id=cycle.id,
                    )
                )
            elif cycle.round_no == 2:
                definitions.append(
                    DocumentChecklistDefinition(
                        checklist_key=f"capa_cycle:{cycle.id}:INSPECTION_CAPA_LAN_2",
                        label=CASE_DOCUMENT_FAMILY_LABELS["INSPECTION_CAPA_LAN_2"],
                        family_code="INSPECTION_CAPA_LAN_2",
                        parent_scope="capa_cycle",
                        parent_id=cycle.id,
                    )
                )
            elif cycle.round_no > 2:
                # No supported legacy template family exists for later CAPA
                # rounds. Register the canonical parent only: the existing
                # checklist serializer will discover persisted documents
                # with their real family codes, never a fabricated CAPA_3.
                definitions.append(
                    DocumentChecklistDefinition(
                        checklist_key=f"capa_cycle:{cycle.id}:unclassified",
                        label=f"Tài liệu CAPA lần {cycle.round_no}",
                        family_code=None,
                        parent_scope="capa_cycle",
                        parent_id=cycle.id,
                    )
                )
        items = self._serialize_document_checklist_items(session, definitions=definitions)
        later_rounds = {cycle.id: cycle.round_no for cycle in capa_cycles if cycle.round_no > 2}
        if not later_rounds:
            return {"items": items}
        documented_rounds = {
            item["parent_id"] for item in items
            if item["parent_scope"] == "capa_cycle"
            and item["parent_id"] in later_rounds
            and item["family_code"] is not None
            and item["status"] == "available"
        }
        result: list[dict[str, object]] = []
        for item in items:
            cycle_id = item["parent_id"]
            if item["parent_scope"] == "capa_cycle" and cycle_id in later_rounds:
                if item["family_code"] is None and cycle_id in documented_rounds:
                    # The real persisted family rows replace this placeholder.
                    continue
                if item["family_code"] is not None:
                    item = {
                        **item,
                        "label": f"CAPA lần {later_rounds[cycle_id]} — "
                                 f"{item['title'] or item['family_code']}",
                    }
            result.append(item)
        return {"items": result}

    def _build_approval_document_candidates(
        self,
        session: Session,
        *,
        case_id: str,
        approval_submissions: list[InspectionApprovalSubmission],
        approval_document_links: list[dict[str, object]],
        permissions: set[str],
        terminal_case: bool,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Return every canonical Case document and permission-aware bind actions.

        The ordinary checklist selects only one best Document for each family.
        A multi-round PCT/CT operator needs all exact Case-owned Documents,
        including metadata-only rows. Neither filenames nor submission dates
        establish a link; only the persisted UUID link does.
        """
        family_stage = {"INSPECTION_PT_PCT": "PCT", "INSPECTION_PT_CT": "CT"}
        documents = list(session.scalars(
            select(Document)
            .where(
                Document.case_id == case_id,
                Document.family_code.in_(tuple(family_stage)),
                Document.capa_cycle_id.is_(None),
                Document.certificate_id.is_(None),
                Document.business_eligibility_certificate_id.is_(None),
                Document.change_request_id.is_(None),
            )
            .order_by(Document.family_code.asc(), Document.created_at.asc(), Document.id.asc())
            .execution_options(populate_existing=True)
        ))
        ids = [row.id for row in documents]
        variants = (
            list(session.scalars(
                select(DocumentVariant).where(DocumentVariant.document_id.in_(ids))
                .execution_options(populate_existing=True)
            ))
            if ids else []
        )
        variants_by_document: dict[str, list[DocumentVariant]] = defaultdict(list)
        for variant in variants:
            variants_by_document[variant.document_id].append(variant)
        variant_ids = [variant.id for variant in variants]
        versions = (
            list(session.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.document_variant_id.in_(variant_ids))
                .execution_options(populate_existing=True)
            ))
            if variant_ids else []
        )
        versions_by_variant: dict[str, list[DocumentVersion]] = defaultdict(list)
        for version in versions:
            versions_by_variant[version.document_variant_id].append(version)
        bound_by_document = {
            item["document_id"]: item["approval_submission_id"]
            for item in approval_document_links
        }
        candidates: list[dict[str, object]] = []
        for document in documents:
            document_versions = [
                version
                for variant in variants_by_document.get(document.id, ())
                for version in versions_by_variant.get(variant.id, ())
            ]
            chosen = self._pick_document_version(document_versions)
            candidates.append({
                "document_id": document.id,
                "stage": family_stage[document.family_code],
                "family_code": document.family_code,
                "title": document.title,
                "open_available": self._document_version_open_available(chosen),
                "bound_submission_id": bound_by_document.get(document.id),
            })

        permission_set = {"inspection.edit", "document.read"}
        readiness: list[dict[str, object]] = []
        for submission in approval_submissions:
            if submission.stage not in {"PCT", "CT"}:
                # Invalid legacy stages must never become enabled binding actions.
                continue
            eligible = [
                item["document_id"]
                for item in candidates
                if item["stage"] == submission.stage
                and item["bound_submission_id"] in (None, submission.id)
            ]
            reason = (
                "missing_permission" if not permission_set.issubset(permissions)
                else "terminal_case" if terminal_case
                else "no_eligible_documents" if not eligible
                else None
            )
            readiness.append({
                "action_key": "bind_approval_document",
                "approval_submission_id": submission.id,
                "stage": submission.stage,
                "round_no": submission.round_no,
                "expected_version": submission.row_version,
                "available": reason is None,
                "reason_code": reason,
                "required_permissions": ["inspection.edit", "document.read"],
                "eligible_document_ids": eligible if reason is None else [],
            })
        return candidates, readiness

    @staticmethod
    def _build_approval_document_evidence(
        *,
        approval_submissions: list[InspectionApprovalSubmission],
        document_checklist: dict[str, object],
        linked_submission_ids: set[str],
    ) -> list[dict[str, object]]:
        """Expose Case-level inventory separately from explicit round binding.

        Family evidence alone never proves a submission binding or issuance.
        """
        case_documents = {
            item["family_code"]: item
            for item in document_checklist["items"]
            if item["parent_scope"] == "case"
            and item["family_code"] in {"INSPECTION_PT_PCT", "INSPECTION_PT_CT"}
        }
        result: list[dict[str, object]] = []
        for stage, family in (("PCT", "INSPECTION_PT_PCT"), ("CT", "INSPECTION_PT_CT")):
            stage_submissions = [item for item in approval_submissions if item.stage == stage]
            case_document = case_documents.get(family)
            result.append({
                "stage": stage,
                "family_code": family,
                "case_document_status": (
                    "available"
                    if case_document is not None and case_document["status"] == "available"
                    else "missing"
                ),
                "selected_case_document_id": (
                    None if case_document is None else case_document["document_id"]
                ),
                "selected_case_document_open_available": (
                    False if case_document is None else bool(case_document["open_available"])
                ),
                "round_document_binding_state": (
                    "bound"
                    if stage_submissions and all(item.id in linked_submission_ids for item in stage_submissions)
                    else "partially_bound"
                    if any(item.id in linked_submission_ids for item in stage_submissions)
                    else "unbound"
                ),
                "submission_ids": [item.id for item in stage_submissions],
                "completed_submission_ids": [
                    item.id for item in stage_submissions if item.completed_on is not None
                ],
            })
        return result

    def _build_case_contextual_document_actions(
        self,
        session: Session,
        *,
        case_id: str,
        capa_cycles: list[CapaCycle],
        user: AuthenticatedUser,
    ) -> list[dict[str, object]]:
        definitions = []
        case = session.get(Case, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        spec_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
        for spec, parent_id in build_case_contextual_document_specs(capa_cycles):
            resolved_parent_id = case_id if spec.parent_scope == "case" else parent_id
            definition = DocumentChecklistDefinition(
                checklist_key=f"{spec.parent_scope}:{resolved_parent_id}:{spec.family_code}",
                label=spec.label,
                family_code=spec.family_code,
                parent_scope=spec.parent_scope,
                parent_id=resolved_parent_id,
            )
            definitions.append(definition)
            spec_by_key[(spec.parent_scope, resolved_parent_id, spec.family_code)] = {
                "workflow_step": spec.workflow_step,
                "create_readiness": spec.create_readiness,
            }

        items = self._serialize_document_checklist_items(session, definitions=definitions)
        contextual_items: list[dict[str, object]] = []
        permissions = self._effective_permissions(user)
        for item in items:
            family_code = item.get("family_code")
            if not isinstance(family_code, str):
                continue
            spec = spec_by_key.get((str(item["parent_scope"]), str(item["parent_id"]), family_code))
            if spec is None:
                continue
            create_contract = None
            effective_create_readiness = spec["create_readiness"]
            if family_code == INSPECTION_KE_HOACH_KT_FAMILY:
                if case.gxp_type not in KHKT_SUPPORTED_GXP_TYPES:
                    # The Case remains readable even if this document family
                    # has no template for its canonical GxP. Do not invent a
                    # filename or expose a generic create action.
                    effective_create_readiness = "UNSUPPORTED_GXP_TYPE"
                else:
                    # A supported variant must still pass the exact template
                    # asset contract; do not hide a malformed/missing manifest.
                    create_contract = {
                        "create_gxp_type": case.gxp_type,
                        "create_storage_scope": "inspection_folder",
                        "create_output_filename": get_inspection_ke_hoach_kt_output_filename(case.gxp_type),
                    }
                    if bool(item["open_available"]):
                        effective_create_readiness = "READY_OPEN_HISTORY"
                    elif effective_create_readiness == "READY_CREATE_OPEN_HISTORY" and "document.write" in permissions:
                        # Read-only canonical input preview. This is the same
                        # source aggregate consumed by the KHKT renderer, not
                        # an independently maintained set of required fields.
                        # Binary/template/storage checks still belong to the
                        # rendering owner; input readiness alone never claims
                        # the final Word output is guaranteed to succeed.
                        try:
                            load_inspection_ke_hoach_kt_payload_input(
                                session,
                                case_id=case.id,
                                generated_at=datetime.now(timezone.utc),
                            )
                        except (InspectionKeHoachKtPayloadInputError, DocumentPayloadBuildError) as exc:
                            effective_create_readiness = "BUSINESS_INPUT_NOT_READY"
                            create_contract["create_input_readiness"] = "CANONICAL_INPUT_BLOCKED"
                            create_contract["create_input_blocked_reason"] = str(exc)
                        else:
                            create_contract["create_input_readiness"] = "CANONICAL_INPUT_READY"
                            create_contract["create_input_blocked_reason"] = None
                            # Caller metadata cannot redirect to another Case,
                            # GxP type, template or generic document renderer.
                            create_contract["create_endpoint"] = (
                                KHKT_CASE_TYPED_RENDER_ROUTE.format(case_id=case.id)
                            )
                            create_contract["create_http_method"] = "POST"
            contextual_items.append(
                {
                    **item,
                    "workflow_step": spec["workflow_step"],
                    "actions": build_document_action_states(
                        open_available=bool(item["open_available"]),
                        history_available=bool(item["detail_available"]),
                        create_readiness=effective_create_readiness,
                        permissions=permissions,
                        family_code=family_code,
                        parent_scope=str(item["parent_scope"]),
                        parent_id=str(item["parent_id"]),
                        document_type_code=item.get("document_type_code"),
                        create_contract=create_contract,
                    ),
                }
            )
        return contextual_items

    def _build_change_request_document_checklist(
        self,
        session: Session,
        *,
        change_request_id: str,
    ) -> dict[str, object]:
        definitions = [
            DocumentChecklistDefinition(
                checklist_key=f"change_request:{change_request_id}:{family_code}",
                label=label,
                family_code=family_code,
                parent_scope="change_request",
                parent_id=change_request_id,
            )
            for family_code, label in CHANGE_REQUEST_DOCUMENT_FAMILY_LABELS.items()
        ]
        return {"items": self._serialize_document_checklist_items(session, definitions=definitions)}

    def _serialize_gxp_certificate_detail(
        self,
        *,
        certificate: Certificate,
        version: CertificateVersion,
        linked_case: Case | None,
        site: Site,
        company: Company,
        scope_summary: str | None,
        scope_rows: list[CertificateScope],
        inspected_on: date | None,
    ) -> dict[str, object]:
        context = CertificateContextRow(
            certificate=certificate,
            version=version,
            line_code=self._certificate_line_code(certificate, linked_case),
            scope_summary=scope_summary,
        )
        return {
            "certificate_id": certificate.id,
            "row_version": certificate.row_version,
            "site_id": certificate.site_id,
            "case_id": certificate.case_id,
            "certificate_type": certificate.certificate_type,
            "line_code": context.line_code,
            "issuance_basis": certificate.issuance_basis,
            "latest_flag": certificate.latest_flag,
            "certificate_number": version.certificate_number,
            "issue_date": version.issue_date,
            "expiry_date": version.expiry_date,
            "applicable_standard": version.applicable_standard,
            "issuing_authority": version.issuing_authority,
            "status": self._derive_certificate_status(context),
            "facility_name": site.site_name,
            "address": site.site_address,
            "company_name": company.legal_name,
            "company_legal_address": company.legal_address,
            "scope_summary": scope_summary,
            "scopes": [
                {
                    "id": scope.id,
                    "scope_key": scope.scope_key,
                    "scope_text": scope.scope_text,
                    "language_code": scope.language_code,
                    "sort_order": scope.sort_order,
                }
                for scope in sorted(scope_rows, key=lambda item: (item.sort_order, item.created_at, item.id))
            ],
            "limitation_text": None,
            "source_description": self._describe_certificate_source(
                certificate=certificate,
                linked_case=linked_case,
                inspected_on=inspected_on,
            ),
            "action_readiness": [],
        }

    def _serialize_business_eligibility_detail(
        self,
        *,
        certificate: BusinessEligibilityCertificate,
        version: BusinessEligibilityVersion,
        site: Site,
        company: Company,
        linked_gxp_certificates: list[dict[str, object]],
        replacement_map: dict[int, str | None],
        action_readiness: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "business_eligibility_certificate_id": certificate.id,
            "row_version": certificate.row_version,
            "site_id": certificate.site_id,
            "company_id": certificate.company_id,
            "latest_flag": certificate.latest_flag,
            "certificate_number": version.certificate_number,
            "issued_on": version.issued_on,
            "expires_on": version.expires_on,
            "notes": version.notes,
            "decision_reference": version.decision_reference,
            "issuance_sequence_text": version.issuance_sequence_text,
            "issuance_history_text": version.issuance_history_text,
            "company_name": company.legal_name,
            "company_legal_address": company.legal_address,
            "facility_name": site.site_name,
            "address": site.site_address,
            "professional_responsible_person_name": version.professional_responsible_person_name,
            "quality_assurance_person_name": version.quality_assurance_person_name,
            "professional_qualification_text": version.professional_qualification_text,
            "professional_license_number": version.professional_license_number,
            "professional_license_issued_on": version.professional_license_issued_on,
            "professional_license_issuer": version.professional_license_issuer,
            "responsible_license_issued_on": version.responsible_license_issued_on,
            "responsible_license_issuer": version.responsible_license_issuer,
            "business_activity_text": version.business_activity_text,
            "current_status_text": version.current_status_text,
            "handled_by_name": version.handled_by_name,
            "application_dossier_reference": version.application_dossier_reference,
            "replaces_certificate_number": replacement_map.get(certificate.replaces_legacy_dkkd_id),
            "replaced_by_certificate_number": replacement_map.get(certificate.replaced_by_legacy_dkkd_id),
            "linked_gxp_certificates": linked_gxp_certificates,
            "action_readiness": action_readiness or [],
        }

    @staticmethod
    def _build_latest_business_eligibility_version_subquery():
        return (
            select(
                BusinessEligibilityVersion.business_eligibility_certificate_id.label("business_eligibility_certificate_id"),
                func.max(BusinessEligibilityVersion.version_no).label("max_version_no"),
            )
            .group_by(BusinessEligibilityVersion.business_eligibility_certificate_id)
            .subquery()
        )

    @staticmethod
    def _normalize_match_kind(selected_line_code: str | None, row_line_code: str | None) -> str:
        if selected_line_code is None:
            return "site_wide"
        if row_line_code == selected_line_code:
            return "exact_line"
        return "facility_wide"

    @staticmethod
    def _certificate_line_code(certificate: Certificate, linked_case: Case | None) -> str | None:
        direct_line_code = CatalogReadService._normalize_line_code(certificate.line_code)
        if direct_line_code is not None:
            return direct_line_code
        if linked_case is None:
            return None
        return CatalogReadService._normalize_line_code(linked_case.scope_code)

    @staticmethod
    def _assert_certificate_links_valid(session: Session, *, site_id: str | None = None) -> None:
        statement = select(Certificate).where(Certificate.case_id.is_not(None))
        if site_id is not None:
            statement = statement.where(Certificate.site_id == site_id)
        for certificate in session.scalars(statement):
            CaseWorkflowService._validate_certificate_linked_case(session, certificate)

    @staticmethod
    def _quarantined_historical_search_certificates(
        session: Session, *, site_id: str | None = None,
    ) -> tuple[set[str], list[int]]:
        """Read-only committed owner preflight before downstream filters.

        Use one scalar Certificate/Case/Site projection rather than ORM
        populate_existing: a GET may not flush, overwrite cached drafts,
        or accept a stale Case owner from another transaction. The exact
        independently witnessed legacy quarantine predicate is unchanged.
        """
        statement = (
            select(
                Certificate.id.label("cert_id"),
                Certificate.case_id.label("cert_case_id"),
                Certificate.site_id.label("cert_site_id"),
                Certificate.certificate_type.label("cert_type"),
                Certificate.issuance_basis.label("cert_basis"),
                Certificate.legacy_certificate_id.label("cert_legacy_id"),
                Case.id.label("case_id"),
                Case.site_id.label("case_site_id"),
                Case.gxp_type.label("case_gxp_type"),
                Case.legacy_inspection_id.label("case_legacy_id"),
                Site.id.label("site_id"),
                Site.legacy_site_id.label("site_legacy_id"),
            )
            .select_from(Certificate)
            .outerjoin(Case, Case.id == Certificate.case_id)
            .outerjoin(Site, Site.id == Certificate.site_id)
            .where(Certificate.case_id.is_not(None))
        )
        if site_id is not None:
            statement = statement.where(Certificate.site_id == site_id)
        with session.no_autoflush:
            rows = session.execute(statement).mappings().all()
        return CatalogReadService._quarantine_historical_projection_rows(rows)

    @staticmethod
    def _quarantine_historical_projection_rows(rows) -> tuple[set[str], list[int]]:
        """Validate the exact witnessed historical links from one SQL snapshot.

        This pure owner predicate is shared by report/search preflights and the
        Facility workspace's atomic source projection. Any unrecognized link
        corruption fails closed regardless of current filters or GCN status.
        """
        quarantined: set[str] = set()
        legacy_ids: list[int] = []
        for row in rows:
            if (
                row["case_id"] == row["cert_case_id"]
                and row["case_site_id"] == row["cert_site_id"]
                and row["case_gxp_type"] == row["cert_type"]
            ):
                continue
            cert = SimpleNamespace(
                id=row["cert_id"], case_id=row["cert_case_id"],
                site_id=row["cert_site_id"], certificate_type=row["cert_type"],
                issuance_basis=row["cert_basis"],
                legacy_certificate_id=row["cert_legacy_id"],
            )
            linked_case = (
                SimpleNamespace(
                    id=row["case_id"], site_id=row["case_site_id"],
                    gxp_type=row["case_gxp_type"],
                    legacy_inspection_id=row["case_legacy_id"],
                )
                if row["case_id"] is not None else None
            )
            site = (
                SimpleNamespace(
                    id=row["site_id"], legacy_site_id=row["site_legacy_id"],
                )
                if row["site_id"] is not None else None
            )
            if not is_witnessed_historical_search_quarantine(cert, linked_case, site):
                raise HTTPException(
                    status_code=409,
                    detail="Certificate references an invalid linked Case.",
                )
            quarantined.add(row["cert_id"])
            legacy_ids.append(row["cert_legacy_id"])
        return quarantined, sorted(legacy_ids)

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
        excluded_certificate_ids: set[str] | None = None,
    ):
        conditions = [Certificate.site_id == Site.id, Certificate.latest_flag.is_(True)]
        if excluded_certificate_ids:
            conditions.append(Certificate.id.not_in(excluded_certificate_ids))
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
        # Newly created masters have NULL legacy IDs; SQLite and PostgreSQL
        # sort those differently by default. Keep discovery deterministic.
        stmt = select(Company).order_by(Company.legacy_company_id.asc().nulls_last(), Company.id).limit(limit)
        if q:
            stmt = stmt.where(Company.legal_name.ilike(f"%{q}%"))
        return list(session.scalars(stmt))

    def get_company(self, session: Session, company_id: str) -> Company:
        row = session.get(Company, company_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Company not found.")
        return row

    @staticmethod
    def _committed_master_snapshot(
        session: Session, *, model: type, identity: str, missing_detail: str,
    ) -> SimpleNamespace:
        """Read a persisted resource for unknown-POST-outcome recovery.

        Unlike Session.get or ORM entity SELECT, column projection does not
        return the Session's dirty/cached identity or autoflush pending drafts.
        It also does not expire or overwrite a tracked operator edit. This
        snapshot must not be treated as a lock, authorization, or proof that a
        missing POST can safely be replayed.
        """
        with session.no_autoflush:
            row = session.execute(
                select(*model.__table__.columns)
                .where(model.id == identity)
            ).mappings().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=missing_detail)
        return SimpleNamespace(**row)

    def get_company_master_persisted(
        self, session: Session, company_id: str,
    ) -> SimpleNamespace:
        return self._committed_master_snapshot(
            session, model=Company, identity=company_id,
            missing_detail="Company not found.",
        )

    def get_site_master_persisted(
        self, session: Session, site_id: str,
    ) -> SimpleNamespace:
        return self._committed_master_snapshot(
            session, model=Site, identity=site_id,
            missing_detail="Site not found.",
        )

    def get_production_line_master_persisted(
        self, session: Session, production_line_id: str,
    ) -> SimpleNamespace:
        return self._committed_master_snapshot(
            session, model=ProductionLine, identity=production_line_id,
            missing_detail="ProductionLine not found.",
        )

    def list_sites(self, session: Session, *, q: str | None, limit: int):
        # Preserve legacy-first ordering consistently across database engines.
        stmt = select(Site).order_by(Site.legacy_site_id.asc().nulls_last(), Site.id).limit(limit)
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

    def get_case_master_persisted(
        self, session: Session, case_id: str,
    ) -> SimpleNamespace:
        """Canonical Initial Case readback after uncertain client-UUID POST.

        Project persisted Case scalars, not the Session identity-map snapshot.
        Missing result does not establish that an in-flight POST cannot commit.
        """
        return self._committed_master_snapshot(
            session, model=Case, identity=case_id,
            missing_detail="Case not found.",
        )

    def get_case_report(self, session: Session, *, gxp_type: str | None, state: str | None,
                        q: str | None, opened_year: int | None, inspection_queue: bool,
                        export: bool, offset: int, limit: int,
                        certificate_decision_status: str | None = None) -> dict[str, object]:
        states = WAITING_INSPECTION_CASE_STATES if inspection_queue else ACTIVE_CASE_STATES
        if state:
            allowed = {item.value: item for item in states}
            if state not in allowed:
                raise HTTPException(status_code=422, detail="Invalid report case state.")
            states = [allowed[state]]
        allowed_decision_filters = {
            "awaiting_decision", "nonissuance_recorded", "not_at_decision_stage",
        }
        if certificate_decision_status is not None and certificate_decision_status not in allowed_decision_filters:
            raise HTTPException(status_code=422, detail="Invalid certificate decision report filter.")
        # Classification comes only from Case state plus the persisted decision,
        # never missing GCN, free-text final evaluation, or an inferred outcome.
        conditions = [Case.state.in_(states)]
        if certificate_decision_status == "nonissuance_recorded":
            conditions.append(CaseCertificateNonissuanceDecision.id.is_not(None))
        elif certificate_decision_status == "awaiting_decision":
            conditions.extend((
                Case.state == CaseState.AWAITING_CERTIFICATE_DECISION,
                CaseCertificateNonissuanceDecision.id.is_(None),
            ))
        elif certificate_decision_status == "not_at_decision_stage":
            conditions.extend((
                Case.state != CaseState.AWAITING_CERTIFICATE_DECISION,
                CaseCertificateNonissuanceDecision.id.is_(None),
            ))
        if gxp_type:
            conditions.append(Case.gxp_type == gxp_type)
        if q:
            pattern = f"%{q}%"
            # Search the same canonical Case and its explicitly linked decision.
            # Operators often paste a Case UUID or decision reference from a
            # notification. Never infer a decision from a missing Certificate.
            # A Certificate number is a useful path back to its owning Case,
            # but a historical cross-Site/GxP/line association is not proof of
            # that ownership. Require exact canonical identity and the
            # explicitly latest version; do not match administrative-only or
            # unlinked legacy Certificate records.
            canonical_certificate_number = (
                select(Certificate.id)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(
                    Certificate.case_id == Case.id,
                    Certificate.site_id == Case.site_id,
                    Certificate.certificate_type == Case.gxp_type,
                    Certificate.issuance_basis == "inspection_case",
                    or_(
                        and_(
                            Case.production_line_id.is_not(None),
                            Certificate.production_line_id == Case.production_line_id,
                        ),
                        and_(
                            Case.production_line_id.is_(None),
                            Certificate.production_line_id.is_(None),
                            Case.scope_code.is_(None),
                            Certificate.line_code.is_(None),
                        ),
                    ),
                    CertificateVersion.certificate_number.ilike(pattern),
                )
                .correlate(Case)
                .exists()
            )
            conditions.append(or_(
                Site.site_name.ilike(pattern),
                Company.legal_name.ilike(pattern),
                Case.legacy_inspection_code.ilike(pattern),
                cast(Case.id, String).ilike(pattern),
                CaseCertificateNonissuanceDecision.decision_reference.ilike(pattern),
                canonical_certificate_number,
            ))
        if opened_year is not None:
            conditions.append(Case.opened_year == opened_year)
        # A report is a persisted read, not a mutable ORM entity refresh.
        # SQL filters, counts and output columns must use the same committed
        # values without flushing or replacing operator drafts in the Session.
        base = (
            select(
                Case.id.label("case_id"),
                Case.site_id.label("case_site_id"),
                Case.production_line_id.label("case_line_id"),
                Case.gxp_type.label("case_type"),
                Case.scope_code.label("case_scope_code"),
                Case.state.label("case_state"),
                Case.legacy_inspection_code.label("case_reference_code"),
                Case.opened_year.label("case_opened_year"),
                Site.id.label("site_id"),
                Site.site_name.label("site_name"),
                Company.legal_name.label("company_name"),
                ProductionLine.id.label("line_id"),
                ProductionLine.site_id.label("line_site_id"),
                ProductionLine.code.label("line_code"),
                CaseCertificateNonissuanceDecision.id.label("decision_id"),
                CaseCertificateNonissuanceDecision.decision_reference.label("decision_reference"),
                CaseCertificateNonissuanceDecision.decided_on.label("decision_on"),
            )
            .select_from(Case)
            .join(Site, Site.id == Case.site_id)
            .join(Company, Company.id == Site.company_id)
            .outerjoin(ProductionLine, ProductionLine.id == Case.production_line_id)
            .outerjoin(
                CaseCertificateNonissuanceDecision,
                CaseCertificateNonissuanceDecision.case_id == Case.id,
            )
            .where(*conditions)
        )
        with session.no_autoflush:
            if export:
                if offset != 0:
                    raise HTTPException(status_code=422, detail="Export offset must be zero.")
                rows = session.execute(
                    base.order_by(Case.id).limit(10001)
                ).mappings().all()
                if len(rows) > 10000:
                    raise HTTPException(status_code=413, detail="Report exceeds 10000 rows; narrow the filters.")
                total, limit = len(rows), 10000
            else:
                page = base.order_by(Case.id).offset(offset).limit(limit).subquery("case_report_page")
                total_for_page = (
                    select(func.count())
                    .select_from(Case)
                    .join(Site, Site.id == Case.site_id)
                    .join(Company, Company.id == Site.company_id)
                    .outerjoin(
                        CaseCertificateNonissuanceDecision,
                        CaseCertificateNonissuanceDecision.case_id == Case.id,
                    )
                    .where(*conditions)
                    .scalar_subquery()
                )
                anchor = select(literal(1).label("anchor")).subquery("case_report_anchor")
                counted_rows = session.execute(
                    select(*page.c, total_for_page.label("report_total_count"))
                    .select_from(anchor.outerjoin(page, true()))
                    .order_by(page.c.case_id)
                ).mappings().all()
                total = counted_rows[0]["report_total_count"] if counted_rows else 0
                rows = [row for row in counted_rows if row["case_id"] is not None]

        items = []
        for row in rows:
            line_id, line_code, identity = self._line_identity(
                site_id=row["case_site_id"],
                production_line_id=row["case_line_id"],
                raw_line_code=row["case_scope_code"],
                lines=(
                    {row["line_id"]: SimpleNamespace(
                        id=row["line_id"], site_id=row["line_site_id"], code=row["line_code"],
                    )} if row["line_id"] is not None else {}
                ),
            )
            decision_id = row["decision_id"]
            state_value = row["case_state"].value
            items.append({
                "case_id": row["case_id"],
                "site_id": row["site_id"],
                "production_line_id": line_id,
                "result_key": self._build_search_result_key(
                    row["site_id"], gxp_type=row["case_type"],
                    identity_state=identity, production_line_id=line_id, line_code=line_code,
                ),
                "facility_name": row["site_name"],
                "company_name": row["company_name"],
                "gxp_type": row["case_type"],
                "state": state_value,
                "reference_code": row["case_reference_code"],
                "opened_year": row["case_opened_year"],
                "certificate_decision_status": (
                    "nonissuance_recorded" if decision_id is not None
                    else "awaiting_decision" if row["case_state"] == CaseState.AWAITING_CERTIFICATE_DECISION
                    else "not_at_decision_stage"
                ),
                "nonissuance_decision_id": decision_id,
                "nonissuance_decision_reference": (
                    row["decision_reference"] if decision_id is not None else None
                ),
                "nonissuance_decided_on": (
                    row["decision_on"] if decision_id is not None else None
                ),
            })
        return {"items": items, "total_count": total, "offset": offset, "limit": limit}

    def get_certificate_report(
        self, session: Session, *, gxp_type: str | None, q: str | None,
        expiry_days: int | None, export: bool, offset: int, limit: int,
        number: str | None = None,
    ) -> dict[str, object]:
        """One committed current Certificate and Version projection per report row.

        Filter predicates and output fields must come from persisted values,
        never dirty ORM identities. This read-only report cannot flush pending
        operator drafts. Canonical integrity/quarantine remains owner-controlled.
        """
        if expiry_days is not None and expiry_days not in (30, 60, 90):
            raise HTTPException(status_code=422, detail="Unsupported certificate expiry window.")
        if gxp_type is not None and gxp_type not in ("GMP", "GLP", "GMPbb", "GSP", "GDP"):
            raise HTTPException(status_code=422, detail="Invalid certificate GxP type.")
        if export and offset != 0:
            raise HTTPException(status_code=422, detail="Export offset must be zero.")

        with session.no_autoflush:
            # Preflight all linked Case owners before filters/pagination. The
            # three independently witnessed legacy exceptions are quarantine
            # only, never repaired or silently accepted.
            quarantined_ids, quarantined_legacy_ids = (
                self._quarantined_historical_search_certificates(session)
            )
            conditions = [
                Certificate.latest_flag.is_(True),
                CertificateVersion.is_latest_version.is_(True),
                Certificate.id.not_in(quarantined_ids),
            ]
            if gxp_type:
                conditions.append(Certificate.certificate_type == gxp_type)
            if q:
                term = f"%{q}%"
                conditions.append(or_(
                    Site.site_name.ilike(term),
                    Company.legal_name.ilike(term),
                    CertificateVersion.certificate_number.ilike(term),
                ))
            if number:
                conditions.append(CertificateVersion.certificate_number.ilike(f"%{number}%"))
            if expiry_days is not None:
                today = date.today()
                conditions.extend((
                    CertificateVersion.expiry_date.is_not(None),
                    CertificateVersion.expiry_date >= today,
                    CertificateVersion.expiry_date <= today + timedelta(days=expiry_days),
                ))

            source = (
                select(
                    Certificate.id.label("certificate_id"),
                    Certificate.site_id.label("root_site_id"),
                    Certificate.case_id.label("root_case_id"),
                    Certificate.production_line_id.label("root_line_id"),
                    Certificate.certificate_type.label("root_type"),
                    Certificate.line_code.label("root_line_code"),
                    Certificate.latest_flag.label("root_latest_flag"),
                    CertificateVersion.id.label("version_id"),
                    CertificateVersion.certificate_number.label("version_number"),
                    CertificateVersion.issue_date.label("version_issue_date"),
                    CertificateVersion.expiry_date.label("version_expiry_date"),
                    CertificateVersion.lifecycle_state.label("version_lifecycle"),
                    Site.id.label("site_id"),
                    Site.site_name.label("site_name"),
                    Company.legal_name.label("company_name"),
                    ProductionLine.id.label("line_id"),
                    ProductionLine.site_id.label("line_site_id"),
                    ProductionLine.code.label("line_code"),
                    Case.id.label("case_id"),
                    Case.site_id.label("case_site_id"),
                    Case.gxp_type.label("case_type"),
                    Case.scope_code.label("case_scope_code"),
                )
                .select_from(Certificate)
                .join(CertificateVersion, CertificateVersion.certificate_id == Certificate.id)
                .join(Site, Site.id == Certificate.site_id)
                .join(Company, Company.id == Site.company_id)
                .outerjoin(ProductionLine, ProductionLine.id == Certificate.production_line_id)
                .outerjoin(Case, Case.id == Certificate.case_id)
                .where(*conditions)
            )
            # Preserve the global latest-version integrity check even when
            # filters select a subset of the current versions.
            matching = (
                select(Certificate.id)
                .join(CertificateVersion, CertificateVersion.certificate_id == Certificate.id)
                .join(Site, Site.id == Certificate.site_id)
                .join(Company, Company.id == Site.company_id)
                .where(*conditions)
            )
            conflict_count_stmt = select(func.count()).select_from(
                select(CertificateVersion.certificate_id)
                .where(
                    CertificateVersion.is_latest_version.is_(True),
                    CertificateVersion.certificate_id.in_(matching),
                )
                .group_by(CertificateVersion.certificate_id)
                .having(func.count() > 1)
                .subquery()
            )
            conflicts = session.scalar(conflict_count_stmt) or 0
            # A second owner writer can commit another latest Version AFTER
            # the preflight above. Check the same conflict universe in the
            # final row statement's PostgreSQL READ COMMITTED snapshot.
            late_conflicts = conflict_count_stmt.scalar_subquery()
            if conflicts:
                raise HTTPException(status_code=409, detail="Certificate has conflicting latest versions.")
            ordered = source.order_by(Certificate.id, CertificateVersion.id)
            if export:
                export_page = ordered.limit(10001).subquery("report_export")
                anchor = select(literal(1).label("anchor")).subquery("report_anchor")
                export_snapshot = session.execute(
                    select(
                        *export_page.c,
                        late_conflicts.label("report_conflict_count"),
                    )
                    .select_from(anchor.outerjoin(export_page, true()))
                    .order_by(export_page.c.certificate_id, export_page.c.version_id)
                ).mappings().all()
                if export_snapshot and export_snapshot[0]["report_conflict_count"]:
                    raise HTTPException(status_code=409, detail="Certificate has conflicting latest versions.")
                rows = [row for row in export_snapshot if row["certificate_id"] is not None]
                if len(rows) > 10000:
                    raise HTTPException(status_code=413, detail="Report exceeds 10000 rows; narrow the filters.")
                total, limit = len(rows), 10000
            else:
                # COUNT and page must share the SAME PostgreSQL READ COMMITTED
                # statement snapshot. A separate COUNT followed by a page
                # SELECT could include a concurrent committed Certificate in
                # the page while retaining the old count. A one-row anchor
                # preserves total_count when the requested page is empty.
                page = ordered.offset(offset).limit(limit).subquery("report_page")
                count_at_page_snapshot = (
                    select(func.count())
                    .select_from(Certificate)
                    .join(CertificateVersion, CertificateVersion.certificate_id == Certificate.id)
                    .join(Site, Site.id == Certificate.site_id)
                    .join(Company, Company.id == Site.company_id)
                    .where(*conditions)
                    .scalar_subquery()
                )
                anchor = select(literal(1).label("anchor")).subquery("report_anchor")
                counted_rows = session.execute(
                    select(
                        *page.c,
                        count_at_page_snapshot.label("report_total_count"),
                        late_conflicts.label("report_conflict_count"),
                    )
                    .select_from(anchor.outerjoin(page, true()))
                    .order_by(page.c.certificate_id, page.c.version_id)
                ).mappings().all()
                if counted_rows and counted_rows[0]["report_conflict_count"]:
                    raise HTTPException(status_code=409, detail="Certificate has conflicting latest versions.")
                total = counted_rows[0]["report_total_count"] if counted_rows else 0
                rows = [row for row in counted_rows if row["certificate_id"] is not None]

        items = []
        for row in rows:
            # These identity checks use the same SQL statement as the actual
            # report row: cached Case or Line objects cannot override the
            # committed Certificate identity or the current Version number.
            if row["root_case_id"] is not None and (
                row["case_id"] != row["root_case_id"]
                or row["case_site_id"] != row["root_site_id"]
                or row["case_type"] != row["root_type"]
            ):
                raise HTTPException(
                    status_code=409, detail="Certificate references an invalid linked Case.",
                )
            if row["root_line_id"] is not None:
                if row["line_id"] != row["root_line_id"]:
                    raise HTTPException(
                        status_code=409, detail="Canonical ProductionLine reference is missing.",
                    )
                if row["line_site_id"] != row["root_site_id"]:
                    raise HTTPException(
                        status_code=409,
                        detail="Canonical ProductionLine reference belongs to a different site.",
                    )
            certificate = SimpleNamespace(
                certificate_type=row["root_type"],
                line_code=row["root_line_code"],
                latest_flag=row["root_latest_flag"],
            )
            linked_case = (
                SimpleNamespace(scope_code=row["case_scope_code"])
                if row["case_id"] is not None else None
            )
            resolved_line_code = self._certificate_line_code(certificate, linked_case)
            line_id, line_code, identity = self._line_identity(
                site_id=row["root_site_id"],
                production_line_id=row["root_line_id"],
                raw_line_code=resolved_line_code,
                lines=(
                    {
                        row["line_id"]: SimpleNamespace(
                            id=row["line_id"],
                            site_id=row["line_site_id"],
                            code=row["line_code"],
                        )
                    }
                    if row["line_id"] is not None else {}
                ),
            )
            version = SimpleNamespace(expiry_date=row["version_expiry_date"])
            items.append({
                "certificate_id": row["certificate_id"],
                "result_key": self._build_search_result_key(
                    row["site_id"],
                    gxp_type=row["root_type"],
                    identity_state=identity,
                    production_line_id=line_id,
                    line_code=line_code,
                ),
                "certificate_version_id": row["version_id"],
                "site_id": row["site_id"],
                "case_id": row["root_case_id"],
                "production_line_id": row["root_line_id"],
                "line_code": line_code,
                "facility_name": row["site_name"],
                "company_name": row["company_name"],
                "gxp_type": row["root_type"],
                "certificate_number": row["version_number"],
                "issue_date": row["version_issue_date"],
                "expiry_date": row["version_expiry_date"],
                "lifecycle_state": row["version_lifecycle"],
                "status": self._derive_certificate_status(
                    CertificateContextRow(
                        certificate=certificate, version=version, line_code=line_code,
                    )
                ),
            })
        return {
            "items": items, "total_count": total, "offset": offset, "limit": limit,
            "quarantined_historical_certificate_legacy_ids": quarantined_legacy_ids,
        }

    def get_change_request_report(
        self, session: Session, *, state: str | None, q: str | None,
        export: bool, offset: int, limit: int,
    ) -> dict[str, object]:
        """Committed Site-owned Change Request report without ORM draft flush.

        Filter, count, and visible projection use persisted columns, not the
        identity-map values of dirty cached ChangeRequest, Site or Company.
        This does not claim a transaction-wide snapshot across count/page.
        """
        allowed = {item.value: item for item in OPEN_CHANGE_REQUEST_STATES}
        if state is not None and state not in allowed:
            raise HTTPException(status_code=422, detail="Invalid open Change Request state.")
        if export and offset != 0:
            raise HTTPException(status_code=422, detail="Export offset must be zero.")

        conditions = [ChangeRequest.state.in_([allowed[state]] if state else OPEN_CHANGE_REQUEST_STATES)]
        if q:
            term = f"%{q}%"
            conditions.append(or_(
                Site.site_name.ilike(term), Company.legal_name.ilike(term),
                ChangeRequest.scope_label.ilike(term), ChangeRequest.description.ilike(term),
            ))
        source = (
            select(
                ChangeRequest.id.label("request_id"),
                ChangeRequest.site_id.label("request_site_id"),
                ChangeRequest.legacy_change_request_id.label("legacy_request_id"),
                ChangeRequest.scope_label.label("request_scope_label"),
                ChangeRequest.description.label("request_description"),
                ChangeRequest.submitted_on.label("request_submitted_on"),
                ChangeRequest.requester_name.label("request_requester_name"),
                ChangeRequest.state.label("request_state"),
                Site.id.label("site_id"),
                Site.site_name.label("site_name"),
                Company.legal_name.label("company_name"),
            )
            .select_from(ChangeRequest)
            .join(Site, Site.id == ChangeRequest.site_id)
            .join(Company, Company.id == Site.company_id)
            .where(*conditions)
        )
        with session.no_autoflush:
            if export:
                rows = session.execute(
                    source.order_by(ChangeRequest.id).limit(10001)
                ).mappings().all()
                if len(rows) > 10000:
                    raise HTTPException(status_code=413, detail="Report exceeds 10000 rows; narrow the filters.")
                total, limit = len(rows), 10000
            else:
                # One PostgreSQL READ COMMITTED statement must own both the
                # total and the visible page. A concurrent committed writer
                # cannot appear only in the second SELECT. The anchor retains
                # total_count even if the requested offset has no items.
                page = (
                    source.order_by(ChangeRequest.id)
                    .offset(offset).limit(limit)
                    .subquery("change_report_page")
                )
                count_at_page_snapshot = (
                    select(func.count()).select_from(ChangeRequest)
                    .join(Site, Site.id == ChangeRequest.site_id)
                    .join(Company, Company.id == Site.company_id)
                    .where(*conditions)
                    .scalar_subquery()
                )
                anchor = select(literal(1).label("anchor")).subquery("change_report_anchor")
                counted_rows = session.execute(
                    select(*page.c, count_at_page_snapshot.label("report_total_count"))
                    .select_from(anchor.outerjoin(page, true()))
                    .order_by(page.c.request_id)
                ).mappings().all()
                total = counted_rows[0]["report_total_count"] if counted_rows else 0
                rows = [row for row in counted_rows if row["request_id"] is not None]
        items = [
            {
                "change_request_id": row["request_id"],
                "site_id": row["site_id"],
                "legacy_change_request_id": row["legacy_request_id"],
                "facility_name": row["site_name"],
                "company_name": row["company_name"],
                "scope_label": row["request_scope_label"],
                "description": row["request_description"],
                "submitted_on": row["request_submitted_on"],
                "requester_name": row["request_requester_name"],
                "state": row["request_state"].value,
            }
            for row in rows
        ]
        return {"items": items, "total_count": total, "offset": offset, "limit": limit}

    def get_dashboard_summary(self, session: Session, *, queue_limit: int):
        """Committed dashboard counts and Case queue without flushing drafts.

        The queue's Case, Site, Company, and canonical ProductionLine fields
        share one SQL row projection, independent of dirty identity-map state.
        This does not promise one transaction snapshot across aggregate queries.
        """
        with session.no_autoflush:
            # Source-validated quarantine is authoritative for certificate
            # metrics. Unknown invalid Certificate/Case ownership fails closed.
            quarantined_ids, quarantined_legacy_ids = (
                self._quarantined_historical_search_certificates(session)
            )
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
                    self._build_current_certificate_exists_clause(
                        certificate_state="active",
                        excluded_certificate_ids=quarantined_ids,
                    )
                )
            ) or 0
            expiring_certificates_90_days = session.scalar(
                select(func.count()).select_from(Site).where(
                    self._build_current_certificate_exists_clause(
                        certificate_expiring_within_days=90,
                        excluded_certificate_ids=quarantined_ids,
                    )
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
                select(
                    Case.id.label("case_id"),
                    Case.site_id.label("case_site_id"),
                    Case.production_line_id.label("case_line_id"),
                    Case.scope_code.label("case_scope_code"),
                    Case.gxp_type.label("case_gxp_type"),
                    Case.state.label("case_state"),
                    Case.legacy_inspection_code.label("case_reference_code"),
                    Case.opened_year.label("case_opened_year"),
                    Site.id.label("site_id"),
                    Site.site_name.label("site_name"),
                    Company.legal_name.label("company_name"),
                    ProductionLine.id.label("line_id"),
                    ProductionLine.site_id.label("line_site_id"),
                    ProductionLine.code.label("line_code"),
                )
                .select_from(Case)
                .join(Site, Site.id == Case.site_id)
                .join(Company, Company.id == Site.company_id)
                .outerjoin(
                    ProductionLine, ProductionLine.id == Case.production_line_id,
                )
                .where(Case.state.notin_([
                    CaseState.CERTIFIED, CaseState.CLOSED, CaseState.CANCELLED,
                ]))
                .order_by(
                    Case.opened_year.desc(), Case.legacy_inspection_id.desc(),
                    Site.legacy_site_id.asc(),
                )
                .limit(queue_limit)
            ).mappings().all()

        queue = []
        for row in queue_rows:
            line_id, line_code, identity_state = self._line_identity(
                site_id=row["case_site_id"],
                production_line_id=row["case_line_id"],
                raw_line_code=row["case_scope_code"],
                lines=(
                    {
                        row["line_id"]: SimpleNamespace(
                            id=row["line_id"], site_id=row["line_site_id"],
                            code=row["line_code"],
                        )
                    }
                    if row["line_id"] is not None else {}
                ),
            )
            queue.append({
                "case_id": row["case_id"],
                "site_id": row["site_id"],
                "result_key": self._build_search_result_key(
                    row["site_id"],
                    gxp_type=row["case_gxp_type"],
                    identity_state=identity_state,
                    production_line_id=line_id,
                    line_code=line_code,
                ),
                "facility_name": row["site_name"],
                "company_name": row["company_name"],
                "gxp_type": row["case_gxp_type"],
                "state": row["case_state"].value,
                "reference_code": row["case_reference_code"],
                "opened_year": row["case_opened_year"],
            })

        return {
            "total_facilities": total_facilities,
            "total_cases": total_cases,
            "active_cases": active_cases,
            "waiting_inspection": waiting_inspection,
            "waiting_certificate_decision": waiting_certificate_decision,
            "active_certificates": active_certificates,
            "expiring_certificates_90_days": expiring_certificates_90_days,
            "incomplete_changes": incomplete_changes,
            "quarantined_historical_certificate_legacy_ids": quarantined_legacy_ids,
            "queue": queue,
        }

    def search_facilities(
        self,
        session: Session,
        *,
        q: str | None = None,
        facility_name: str | None = None,
        site_id: str | None = None,
        certificate_scope: str | None = None,
        gxp_type: str | None = None,
        province: str | None = None,
        case_states: list[str] | None = None,
        change_request_states: list[str] | None = None,
        certificate_state: str | None = None,
        certificate_expiring_within_days: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, object]:
        return self._search_facilities_by_production_line(
            session,
            q=q,
            facility_name=facility_name,
            site_id=site_id,
            certificate_scope=certificate_scope,
            gxp_type=gxp_type,
            province=province,
            case_states=case_states,
            change_request_states=change_request_states,
            certificate_state=certificate_state,
            certificate_expiring_within_days=certificate_expiring_within_days,
            offset=offset,
            limit=limit,
        )

    def _search_facilities_by_production_line(
        self,
        session: Session,
        *,
        q: str | None,
        facility_name: str | None,
        site_id: str | None,
        certificate_scope: str | None,
        gxp_type: str | None,
        province: str | None,
        case_states: list[str] | None,
        change_request_states: list[str] | None,
        certificate_state: str | None,
        certificate_expiring_within_days: int | None,
        offset: int,
        limit: int,
    ) -> dict[str, object]:
        # All owner-side search inputs are persisted SQL projections. ORM
        # entities from a reused Session can be stale or contain uncommitted
        # operator drafts; an ordinary SELECT can also autoflush those edits.
        # Keep the existing search/context algorithm but never feed it dirty
        # identity-map objects.
        with session.no_autoflush:
            # Certificate link integrity and current Certificate rows must
            # share the same statement snapshot. A separate READ COMMITTED
            # preflight can be invalidated by another committed Case writer.

            def committed_rows(model, *, where=None, order_by=()):
                stmt = select(*model.__table__.columns)
                if where is not None:
                    stmt = stmt.where(where)
                if order_by:
                    stmt = stmt.order_by(*order_by)
                return [
                    SimpleNamespace(**row)
                    for row in session.execute(stmt).mappings().all()
                ]

            sites = committed_rows(Site, order_by=(Site.legacy_site_id, Site.id))
            companies = {row.id: row for row in committed_rows(Company)}
            lines = {row.id: row for row in committed_rows(ProductionLine)}
            # Case state and latest CertificateVersion are one Search read
            # owner: under PostgreSQL READ COMMITTED, separate SELECTs can
            # combine a Case before a writer commit with a GCN number after
            # that same atomic commit. A tagged UNION keeps both grains
            # without Case x Version fanout or ORM identity refresh.
            case_columns = tuple(Case.__table__.columns)
            version_columns = tuple(CertificateVersion.__table__.columns)
            combined = union_all(
                select(
                    literal("case").label("source_kind"),
                    *(column.label("case_" + column.name) for column in case_columns),
                    *(cast(literal(None), column.type).label("version_" + column.name)
                      for column in version_columns),
                ).select_from(Case),
                select(
                    literal("version").label("source_kind"),
                    *(cast(literal(None), column.type).label("case_" + column.name)
                      for column in case_columns),
                    *(column.label("version_" + column.name)
                      for column in version_columns),
                ).select_from(CertificateVersion).where(
                    CertificateVersion.is_latest_version.is_(True)
                ),
            ).subquery("search_atomic_read")
            cross_group_rows = session.execute(
                select(*combined.c)
            ).mappings().all()
            cases = [
                SimpleNamespace(**{
                    column.name: row["case_" + column.name]
                    for column in case_columns
                })
                for row in cross_group_rows if row["source_kind"] == "case"
            ]
            latest_versions = [
                SimpleNamespace(**{
                    column.name: row["version_" + column.name]
                    for column in version_columns
                })
                for row in cross_group_rows if row["source_kind"] == "version"
            ]
            outcomes_by_case_id = {
                row.case_id: row for row in committed_rows(InspectionOutcome)
            }
            inspection_event_dates_by_case_id = {
                case_id: occurred_at.date()
                for case_id, occurred_at in session.execute(
                    select(InspectionEvent.case_id, func.max(InspectionEvent.occurred_at))
                    .where(InspectionEvent.event_type == InspectionEventType.INSPECTION_EXECUTED)
                    .group_by(InspectionEvent.case_id)
                )
                if occurred_at is not None
            }
            # Inspect all Certificate owners independently of Site/GxP
            # filters and latest flags. One scalar SELECT joins the exact
            # committed Certificate, linked Case, and Site; do not resurrect
            # a stale Case owner after a separate preflight.
            certificate_columns = tuple(Certificate.__table__.columns)
            certificate_owner_rows = session.execute(
                select(
                    *(column.label("source_" + column.name)
                      for column in certificate_columns),
                    Certificate.id.label("cert_id"),
                    Certificate.case_id.label("cert_case_id"),
                    Certificate.site_id.label("cert_site_id"),
                    Certificate.certificate_type.label("cert_type"),
                    Certificate.issuance_basis.label("cert_basis"),
                    Certificate.legacy_certificate_id.label("cert_legacy_id"),
                    Case.id.label("case_id"),
                    Case.site_id.label("case_site_id"),
                    Case.gxp_type.label("case_gxp_type"),
                    Case.legacy_inspection_id.label("case_legacy_id"),
                    Site.id.label("site_id"),
                    Site.legacy_site_id.label("site_legacy_id"),
                )
                .select_from(Certificate)
                .outerjoin(Case, Case.id == Certificate.case_id)
                .outerjoin(Site, Site.id == Certificate.site_id)
            ).mappings().all()
            quarantined_ids, quarantined_legacy_ids = (
                self._quarantine_historical_projection_rows(
                    row for row in certificate_owner_rows
                    if row["cert_case_id"] is not None
                )
            )
            certificates = [
                SimpleNamespace(**{
                    column.name: row["source_" + column.name]
                    for column in certificate_columns
                })
                for row in certificate_owner_rows
                if row["source_latest_flag"] and row["cert_id"] not in quarantined_ids
            ]
            change_requests = committed_rows(ChangeRequest)
            # Last-write-wins dictionary construction would silently hide
            # two latest Versions of one current GCN. Fail closed for the
            # requested Site/GxP scope before selecting a current certificate.
            visible_certificate_ids = {
                cert.id for cert in certificates
                if (site_id is None or cert.site_id == site_id)
                and (gxp_type is None or cert.certificate_type == gxp_type)
            }
            seen_latest_ids = set()
            for version in latest_versions:
                if version.certificate_id not in visible_certificate_ids:
                    continue
                if version.certificate_id in seen_latest_ids:
                    raise HTTPException(
                        status_code=409,
                        detail="Certificate has ambiguous latest CertificateVersion identity.",
                    )
                seen_latest_ids.add(version.certificate_id)
            versions = {row.certificate_id: row for row in latest_versions}
            scopes: dict[str, list[CertificateScope]] = defaultdict(list)
            for scope in committed_rows(CertificateScope):
                scopes[scope.certificate_version_id].append(scope)

        case_by_id = {row.id: row for row in cases}
        cases_by_context: dict[tuple[str, str | None, str, str | None], list[Case]] = defaultdict(list)
        certificates_by_context: dict[tuple[str, str | None, str, str | None], list[CertificateContextRow]] = defaultdict(list)

        def key_for(*, site_id: str, regulatory: str, production_line_id: str | None, raw_code: str | None):
            line_id, line_code, state = self._line_identity(site_id=site_id, production_line_id=production_line_id, raw_line_code=raw_code, lines=lines)
            return (site_id, regulatory, state, line_id if state == "canonical" else line_code), line_id, line_code, state

        for row in cases:
            key, _, _, _ = key_for(site_id=row.site_id, regulatory=row.gxp_type, production_line_id=row.production_line_id, raw_code=row.scope_code)
            cases_by_context[key].append(row)
        for certificate in certificates:
            version = versions.get(certificate.id)
            if version is None:
                continue
            linked_case = case_by_id.get(certificate.case_id) if certificate.case_id else None
            raw_code = self._certificate_line_code(certificate, linked_case)
            key, line_id, line_code, state = key_for(site_id=certificate.site_id, regulatory=certificate.certificate_type, production_line_id=certificate.production_line_id, raw_code=raw_code)
            certificates_by_context[key].append(CertificateContextRow(certificate=certificate, version=version, line_code=line_code, production_line_id=line_id, production_line_code=line_code, production_line_identity_state=state, scope_summary=self._build_certificate_scope_summary(scopes.get(version.id, []))))
        # A site with only change-request work is still searchable through its
        # facility-wide context; it must not invent a production-line identity.
        for change_request in change_requests:
            if not any(key[0] == change_request.site_id for key in set(cases_by_context) | set(certificates_by_context)):
                cases_by_context[(change_request.site_id, None, "facility_wide", None)]

        # A newly registered Site is a first-class facility even before the
        # first Case, Change Request or Certificate. Keep it discoverable in a
        # facility-wide, GxP-unclassified context; never invent a GxP type or
        # canonical ProductionLine identity from Site master attributes.
        known_contexts = set(cases_by_context) | set(certificates_by_context)
        for site in sites:
            if not any(key[0] == site.id for key in known_contexts):
                fallback = (site.id, None, "facility_wide", None)
                cases_by_context[fallback]
                known_contexts.add(fallback)

        results: list[dict[str, object]] = []
        for site in sites:
            company = companies.get(site.company_id)
            if company is None:
                continue
            if site_id is not None and site.id != site_id:
                continue
            site_cases = [row for row in cases if row.site_id == site.id]
            site_certificates = [row for row in certificates if row.site_id == site.id]
            # Search eligibility is site-wide; canonical context partitioning
            # below remains strictly keyed by ProductionLine UUID when present.
            haystack = " ".join(
                filter(
                    None,
                    (
                        site.site_name,
                        site.short_name,
                        site.site_address,
                        site.province_name,
                        company.legal_name,
                        company.short_name,
                        *(value for row in site_cases for value in (row.scope_code, row.legacy_inspection_code, row.applicable_standard)),
                        *(
                            value
                            for row in site_certificates
                            for value in (
                                row.line_code,
                                versions.get(row.id).certificate_number if versions.get(row.id) else None,
                                self._build_certificate_scope_summary(scopes.get(versions[row.id].id, [])) if row.id in versions else None,
                            )
                        ),
                    ),
                )
            )
            if q and q.lower() not in haystack.lower():
                continue
            if facility_name and facility_name.lower() not in site.site_name.lower():
                continue
            if province and (site.province_name or "").lower().find(province.lower()) < 0:
                continue
            if change_request_states and not any(row.site_id == site.id and row.state.value in change_request_states for row in change_requests):
                continue
            site_keys = sorted(
                (key for key in set(cases_by_context) | set(certificates_by_context) if key[0] == site.id and (not gxp_type or key[1] == gxp_type)),
                key=lambda key: (key[1] or "", key[2], key[3] or ""),
            )
            for key in site_keys:
                _, regulatory, state, discriminator = key
                context_cases = cases_by_context[key]
                context_certificates = certificates_by_context[key]
                if case_states and not any(row.state.value in case_states for row in context_cases):
                    continue
                if certificate_scope and not any(certificate.scope_summary and certificate_scope.lower() in certificate.scope_summary.lower() for certificate in context_certificates):
                    continue
                if certificate_state or certificate_expiring_within_days is not None:
                    today = date.today()
                    eligible = [row for row in context_certificates if (certificate_state != "active" or row.version.expiry_date is None or row.version.expiry_date >= today) and (certificate_expiring_within_days is None or (row.version.expiry_date is not None and today <= row.version.expiry_date <= today + timedelta(days=certificate_expiring_within_days)))]
                    if not eligible:
                        continue
                line_id = discriminator if state == "canonical" else None
                line_code = lines[line_id].code if line_id is not None else discriminator
                latest_case = self._select_latest_case(context_cases)
                certificate_context = self._select_current_certificate_context(context_certificates, regulatory)
                result_key = self._build_search_result_key(
                    site.id,
                    gxp_type=regulatory,
                    identity_state=state,
                    production_line_id=line_id,
                    line_code=line_code,
                )
                results.append({"result_key": result_key, "site_id": site.id, "legacy_site_id": site.legacy_site_id, "facility_code": self._preferred_site_code(site, regulatory), "context_code": self._build_context_code(site, gxp_type=regulatory, line_code=line_code), "result_grain": "facility" if state == "facility_wide" else "production_line", "gxp_type": regulatory, "line_code": line_code, "production_line_id": line_id, "production_line_code": line_code, "production_line_identity_state": state, "facility_name": site.site_name, "company_name": company.legal_name, "gxp_types": sorted({key[1] for key in site_keys if key[1] is not None}), "certificate_scope_summary": None if certificate_context is None else certificate_context.scope_summary, "province_name": site.province_name, "last_inspection_on": self._select_latest_inspection_on(context_cases, outcomes_by_case_id=outcomes_by_case_id, inspection_event_dates_by_case_id=inspection_event_dates_by_case_id), "current_state": None if latest_case is None else latest_case.state.value, "current_certificate_number": None if certificate_context is None else certificate_context.version.certificate_number, "current_certificate_expiry": None if certificate_context is None else certificate_context.version.expiry_date})
        results.sort(key=lambda row: (row["legacy_site_id"] is None, row["legacy_site_id"] or 0, row["facility_name"], row["gxp_type"] or "", row["production_line_identity_state"], row["production_line_id"] or "", row["line_code"] or ""))
        return {"items": results[offset : offset + limit], "total_count": len(results),
                "offset": offset, "limit": limit,
                "quarantined_historical_certificate_legacy_ids": quarantined_legacy_ids}

    def get_facility_workspace(self, session: Session, *, site_id: str, gxp_type: str | None, line_code: str | None, production_line_id: str | None = None):
        # The Facility workspace is a persisted read boundary. Do not use
        # tracked ORM entities: a reused Session may hold dirty operator
        # drafts or stale identities from an earlier transaction. All source
        # rows are column-projected without autoflush, and no identity is
        # expired, refreshed or overwritten as a side effect of this GET.
        with session.no_autoflush:
            # Quarantine and all workspace rows must share one SQL statement
            # snapshot. A separate READ COMMITTED preflight is not a durable
            # proof after an independent writer changes a linked Case.

            # Read Site/Company/Case, ChangeRequest, GCN/Version/Scope,
            # ProductionLine and aggregated inspection-event dates from ONE
            # SQL statement snapshot. Independent branches avoid Cartesian
            # Case x CR x Scope x event fanout and preserve owner grain.
            # CAST(NULL AS field_type) preserves Postgres UNION column types
            # (including UUID/enum/date) even when the first branch is empty.
            snapshots = {
                "site": tuple(Site.__table__.columns),
                "company": tuple(Company.__table__.columns),
                "case": tuple(Case.__table__.columns),
                "change": tuple(ChangeRequest.__table__.columns),
                "cert": tuple(Certificate.__table__.columns),
                "version": tuple(CertificateVersion.__table__.columns),
                "scope": tuple(CertificateScope.__table__.columns),
                "line": tuple(ProductionLine.__table__.columns),
                # Only these two columns are needed for the historical
                # latest-event-date aggregate, not the full event register.
                "event": (
                    InspectionEvent.__table__.c.case_id,
                    InspectionEvent.__table__.c.occurred_at,
                ),
            }
            cert_columns = snapshots["cert"]
            version_columns = snapshots["version"]
            scope_columns = snapshots["scope"]

            def tagged_columns(*present, aggregate_event_dates=False):
                def project(kind, column):
                    label = f"{kind}_{column.name}"
                    if kind not in present:
                        return cast(literal(None), column.type).label(label)
                    if (
                        aggregate_event_dates
                        and kind == "event"
                        and column.name == "occurred_at"
                    ):
                        return func.max(column).label(label)
                    return column.label(label)

                return [
                    project(kind, column)
                    for kind, columns in snapshots.items()
                    for column in columns
                ]

            owner_stmt = (
                select(literal("owner").label("source_kind"), *tagged_columns("site", "company", "case"))
                .select_from(Site)
                .outerjoin(Company, Company.id == Site.company_id)
                .outerjoin(Case, Case.site_id == Site.id)
                .where(Site.id == site_id)
            )
            change_stmt = (
                select(literal("change").label("source_kind"), *tagged_columns("change"))
                .select_from(ChangeRequest)
                .where(ChangeRequest.site_id == site_id)
            )
            certificate_stmt = (
                select(
                    literal("certificate").label("source_kind"),
                    *tagged_columns("cert", "version", "scope"),
                )
                .select_from(Certificate)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .outerjoin(
                    CertificateScope,
                    CertificateScope.certificate_version_id == CertificateVersion.id,
                )
                .where(
                    Certificate.site_id == site_id,
                    Certificate.latest_flag.is_(True),
                )
            )
            line_stmt = (
                select(literal("line").label("source_kind"), *tagged_columns("line"))
                .select_from(ProductionLine)
                .where(ProductionLine.site_id == site_id)
            )
            event_stmt = (
                select(
                    literal("event").label("source_kind"),
                    *tagged_columns("event", aggregate_event_dates=True),
                )
                .select_from(InspectionEvent)
                .where(
                    InspectionEvent.case_id.in_(
                        select(Case.id).where(Case.site_id == site_id)
                    )
                )
                .group_by(InspectionEvent.case_id)
            )
            certificate_owner_stmt = (
                select(
                    literal("certificate_owner").label("source_kind"),
                    *tagged_columns("cert", "case", "site"),
                )
                .select_from(Certificate)
                .outerjoin(Case, Case.id == Certificate.case_id)
                .outerjoin(Site, Site.id == Certificate.site_id)
                .where(
                    Certificate.site_id == site_id,
                    Certificate.case_id.is_not(None),
                )
            )
            combined = union_all(
                owner_stmt, change_stmt, certificate_stmt, line_stmt,
                event_stmt, certificate_owner_stmt,
            ).subquery("facility_workspace_atomic_read")
            persisted = session.execute(
                select(*combined.c).order_by(
                    combined.c.source_kind,
                    combined.c.case_id,
                    combined.c.cert_id,
                    combined.c.version_id,
                    combined.c.scope_sort_order,
                    combined.c.scope_created_at,
                    combined.c.scope_id,
                )
            ).mappings().all()
            # Validate both current and non-current Certificate links from
            # exactly the same statement snapshot used by the workspace.
            # Only the independently witnessed historical source pairs may
            # be omitted; unknown corrupted links always fail closed.
            quarantined_ids, quarantined_legacy_ids = (
                self._quarantine_historical_projection_rows(
                    {
                        # The atomic UNION source uses raw model column
                        # labels, while the shared owner predicate consumes
                        # the preflight's explicit canonical aliases.
                        "cert_id": row["cert_id"],
                        "cert_case_id": row["cert_case_id"],
                        "cert_site_id": row["cert_site_id"],
                        "cert_type": row["cert_certificate_type"],
                        "cert_basis": row["cert_issuance_basis"],
                        "cert_legacy_id": row["cert_legacy_certificate_id"],
                        "case_id": row["case_id"],
                        "case_site_id": row["case_site_id"],
                        "case_gxp_type": row["case_gxp_type"],
                        "case_legacy_id": row["case_legacy_inspection_id"],
                        "site_id": row["site_id"],
                        "site_legacy_id": row["site_legacy_site_id"],
                    }
                    for row in persisted
                    if row["source_kind"] == "certificate_owner"
                )
            )
            owner_rows = [row for row in persisted if row["source_kind"] == "owner"]
            if not owner_rows:
                raise HTTPException(status_code=404, detail="Site not found.")
            owner = owner_rows[0]
            if owner["company_id"] is None:
                raise HTTPException(status_code=404, detail="Company not found.")
            site = SimpleNamespace(**{
                column.name: owner["site_" + column.name]
                for column in snapshots["site"]
            })
            company = SimpleNamespace(**{
                column.name: owner["company_" + column.name]
                for column in snapshots["company"]
            })
            site_cases = [
                SimpleNamespace(**{
                    column.name: row["case_" + column.name]
                    for column in snapshots["case"]
                })
                for row in owner_rows if row["case_id"] is not None
            ]
            change_requests = [
                SimpleNamespace(**{
                    column.name: row["change_" + column.name]
                    for column in snapshots["change"]
                })
                for row in persisted if row["source_kind"] == "change"
            ]
            cert_pairs = [
                row for row in persisted
                if row["source_kind"] == "certificate"
                and row["cert_id"] not in quarantined_ids
            ]
            normalized_line_code = self._normalize_line_code(line_code)
            lines = {
                row["line_id"]: SimpleNamespace(**{
                    column.name: row["line_" + column.name]
                    for column in snapshots["line"]
                })
                for row in persisted if row["source_kind"] == "line"
            }
            selected_line_id, selected_line_code, identity_state = self._line_identity(
                site_id=site_id, production_line_id=production_line_id,
                raw_line_code=normalized_line_code, lines=lines,
            )
            if (
                production_line_id is not None
                and normalized_line_code is not None
                and selected_line_code != normalized_line_code
            ):
                raise HTTPException(
                    status_code=422,
                    detail="line_code does not match the selected canonical ProductionLine.",
                )
            scoped_cases = [
                row for row in site_cases if not gxp_type or row.gxp_type == gxp_type
            ]
            if identity_state == "canonical":
                scoped_cases = [
                    row for row in scoped_cases
                    if row.production_line_id == selected_line_id
                ]
            elif identity_state == "legacy_unlinked":
                scoped_cases = [
                    row for row in scoped_cases
                    if row.production_line_id is None
                    and self._normalize_line_code(row.scope_code) == selected_line_code
                ]
            else:
                scoped_cases = [
                    row for row in scoped_cases
                    if row.production_line_id is None
                    and self._normalize_line_code(row.scope_code) is None
                ]

            event_dates = {
                row["event_case_id"]: row["event_occurred_at"].date()
                if row["event_occurred_at"] is not None else None
                for row in persisted if row["source_kind"] == "event"
            }
            # All report inputs (including line and last event date) were
            # projected from the same tagged statement as Site/Company/Case.
            # Scope fanout yields multiple rows for one valid latest Version.
            # Only distinct latest Version identities for the *same* current
            # Certificate are ambiguous; never reject repeated scope rows.
            current_version_ids = {}
            current_certificates = []
            certificate_scope_rows_by_version: dict[str, list[CertificateScope]] = defaultdict(list)
            for pair in cert_pairs:
                cert_id, version_id = pair["cert_id"], pair["version_id"]
                previous_version_id = current_version_ids.get(cert_id)
                if previous_version_id is not None and previous_version_id != version_id:
                    if gxp_type is None or pair["cert_certificate_type"] == gxp_type:
                        raise HTTPException(
                            status_code=409,
                            detail="Certificate has ambiguous latest CertificateVersion identity.",
                        )
                if previous_version_id is None:
                    current_version_ids[cert_id] = version_id
                    current_certificates.append((
                        SimpleNamespace(**{
                            column.name: pair["cert_" + column.name]
                            for column in cert_columns
                        }),
                        SimpleNamespace(**{
                            column.name: pair["version_" + column.name]
                            for column in version_columns
                        }),
                    ))
                if pair["scope_id"] is not None:
                    certificate_scope_rows_by_version[version_id].append(
                        SimpleNamespace(**{
                            column.name: pair["scope_" + column.name]
                            for column in scope_columns
                        })
                    )
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
        matching_certificates = [
            row for row in certificate_context_rows
            if (
                (identity_state == "canonical" and row.certificate.production_line_id == selected_line_id)
                or (identity_state == "legacy_unlinked" and row.certificate.production_line_id is None and row.line_code == selected_line_code)
                or (identity_state == "facility_wide" and row.certificate.production_line_id is None and row.line_code is None)
            )
        ]
        current_certificate = self._select_current_certificate_context(matching_certificates, gxp_type)

        history_entries: list[tuple[tuple[date, datetime, datetime, int, str, str], dict[str, object]]] = []
        for row in scoped_cases:
            occurred_on = event_dates.get(row.id)
            history_entries.append(
                (
                    self._history_order_key(
                        occurred_on=occurred_on,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        source_type="case",
                        reference_code=row.legacy_inspection_code,
                        item_id=row.id,
                    ),
                    {
                        "id": row.id,
                        "source_type": "case",
                        "reference_code": row.legacy_inspection_code,
                        "event_type": row.inspection_type or "Đợt kiểm tra",
                        "gxp_type": row.gxp_type,
                        "standard": row.applicable_standard or row.scope_code,
                        "occurred_on": occurred_on,
                        "state": row.state.value,
                    },
                )
            )
        for row in change_requests:
            occurred_on = row.submitted_on
            history_entries.append(
                (
                    self._history_order_key(
                        occurred_on=occurred_on,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        source_type="change_request",
                        reference_code=None if row.legacy_change_request_id is None else str(row.legacy_change_request_id),
                        item_id=row.id,
                    ),
                    {
                        "id": row.id,
                        "source_type": "change_request",
                        "reference_code": None if row.legacy_change_request_id is None else str(row.legacy_change_request_id),
                        "event_type": "Thay đổi cơ sở",
                        "gxp_type": None,
                        "standard": row.scope_label,
                        "occurred_on": occurred_on,
                        "state": row.state.value,
                    },
                )
            )
        history = [payload for _, payload in sorted(history_entries, key=lambda item: item[0], reverse=True)]

        return {
            "summary": {
                "quarantined_historical_certificate_legacy_ids": quarantined_legacy_ids,
                "context_key": self._build_result_key(site.id, gxp_type=gxp_type, line_code=selected_line_code) + (f":{selected_line_id}" if selected_line_id else f":{identity_state}"),
                "site_id": site.id,
                "legacy_site_id": site.legacy_site_id,
                "facility_code": self._preferred_site_code(site, gxp_type),
                "context_code": self._build_context_code(site, gxp_type=gxp_type, line_code=selected_line_code),
                "context_grain": "production_line" if identity_state != "facility_wide" else "facility",
                "selected_line_code": selected_line_code,
                "selected_production_line_id": selected_line_id,
                "selected_production_line_code": selected_line_code,
                "production_line_identity_state": identity_state,
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "company_legal_address": company.legal_address,
                "company_leader": site.facility_leader_name,
                "company_foreign_investment": site.foreign_investment_text,
                "assigned_specialist": company.assigned_specialist_text,
                "address": site.site_address,
                "contact_information": site.contact_information,
                "professional_responsible_person": site.professional_responsible_person_name,
                "quality_assurance_person": site.quality_assurance_person_name,
                "facility_current_status": site.current_status_text,
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

    def list_site_gxp_certificates(
        self,
        session: Session,
        *,
        site_id: str,
        gxp_type: str | None,
        line_code: str | None,
        production_line_id: str | None = None,
    ):
        """Committed Site/line GxP list; no ORM cache or operator draft writes.

        The selected canonical line is site-owned. Each Certificate, latest
        Version, linked Case and canonical ProductionLine is read from one
        persisted row, so filter matching and projection cannot disagree.
        """
        normalized_line_code = self._normalize_line_code(line_code)
        with session.no_autoflush:
            # Preflight includes historical rows independently of GxP/line
            # filtering. Only exact witnessed source anomalies are excluded.
            quarantined_ids, quarantined_legacy_ids = (
                self._quarantined_historical_search_certificates(
                    session, site_id=site_id,
                )
            )
            if session.scalar(select(Site.id).where(Site.id == site_id)) is None:
                raise HTTPException(status_code=404, detail="Site not found.")
            selected = None
            if production_line_id is not None:
                selected = session.execute(
                    select(
                        ProductionLine.id, ProductionLine.site_id,
                        ProductionLine.code,
                    ).where(ProductionLine.id == production_line_id)
                ).one_or_none()
            lines = (
                {
                    production_line_id: SimpleNamespace(
                        id=selected[0], site_id=selected[1], code=selected[2],
                    )
                }
                if selected is not None else {}
            )
            selected_line_id, selected_line_code, identity_state = self._line_identity(
                site_id=site_id,
                production_line_id=production_line_id,
                raw_line_code=normalized_line_code,
                lines=lines,
            )
            if (
                production_line_id is not None
                and normalized_line_code is not None
                and normalized_line_code != selected_line_code
            ):
                raise HTTPException(
                    status_code=422,
                    detail="line_code does not match the selected canonical ProductionLine.",
                )
            source = (
                select(
                    Certificate.id.label("cert_id"),
                    Certificate.site_id.label("cert_site_id"),
                    Certificate.case_id.label("cert_case_id"),
                    Certificate.certificate_type.label("cert_type"),
                    Certificate.production_line_id.label("cert_line_id"),
                    Certificate.line_code.label("cert_line_text"),
                    Certificate.latest_flag.label("cert_latest_flag"),
                    CertificateVersion.id.label("version_id"),
                    CertificateVersion.certificate_number.label("version_number"),
                    CertificateVersion.issue_date.label("version_issue_date"),
                    CertificateVersion.expiry_date.label("version_expiry_date"),
                    CertificateVersion.applicable_standard.label("version_standard"),
                    CertificateVersion.issuing_authority.label("version_authority"),
                    Case.id.label("linked_case_id"),
                    Case.site_id.label("linked_case_site_id"),
                    Case.gxp_type.label("linked_case_type"),
                    Case.scope_code.label("linked_case_scope"),
                    ProductionLine.id.label("linked_line_id"),
                    ProductionLine.site_id.label("linked_line_site_id"),
                    ProductionLine.code.label("linked_line_code"),
                )
                .select_from(Certificate)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .outerjoin(Case, Case.id == Certificate.case_id)
                .outerjoin(
                    ProductionLine,
                    ProductionLine.id == Certificate.production_line_id,
                )
                .where(
                    Certificate.site_id == site_id,
                    Certificate.id.not_in(quarantined_ids),
                    *([Certificate.certificate_type == gxp_type] if gxp_type else []),
                )
            )
            rows = session.execute(source).mappings().all()

        certificate_ids = [row["cert_id"] for row in rows]
        if len(certificate_ids) != len(set(certificate_ids)):
            raise HTTPException(
                status_code=409,
                detail="Certificate has ambiguous latest CertificateVersion identity.",
            )
        items = []
        for row in rows:
            if row["cert_case_id"] is not None and (
                row["linked_case_id"] != row["cert_case_id"]
                or row["linked_case_site_id"] != row["cert_site_id"]
                or row["linked_case_type"] != row["cert_type"]
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Certificate references an invalid linked Case.",
                )
            if row["cert_line_id"] is not None:
                if row["linked_line_id"] != row["cert_line_id"]:
                    raise HTTPException(
                        status_code=409,
                        detail="Canonical ProductionLine reference is missing.",
                    )
                if row["linked_line_site_id"] != row["cert_site_id"]:
                    raise HTTPException(
                        status_code=409,
                        detail="Canonical ProductionLine reference belongs to a different site.",
                    )
            certificate = SimpleNamespace(
                site_id=row["cert_site_id"],
                case_id=row["cert_case_id"],
                certificate_type=row["cert_type"],
                production_line_id=row["cert_line_id"],
                line_code=row["cert_line_text"],
                latest_flag=row["cert_latest_flag"],
            )
            linked_case = (
                SimpleNamespace(scope_code=row["linked_case_scope"])
                if row["linked_case_id"] is not None else None
            )
            resolved_line_code = self._certificate_line_code(certificate, linked_case)
            cert_line_id, cert_line_code, cert_identity = self._line_identity(
                site_id=certificate.site_id,
                production_line_id=certificate.production_line_id,
                raw_line_code=resolved_line_code,
                lines=(
                    {
                        row["linked_line_id"]: SimpleNamespace(
                            id=row["linked_line_id"],
                            site_id=row["linked_line_site_id"],
                            code=row["linked_line_code"],
                        )
                    }
                    if row["linked_line_id"] is not None else {}
                ),
            )
            if identity_state == "canonical" and not (
                cert_line_id == selected_line_id
                or cert_identity == "facility_wide"
            ):
                continue
            if identity_state == "legacy_unlinked" and not (
                cert_identity == "facility_wide"
                or (
                    cert_line_id is None
                    and cert_identity == "legacy_unlinked"
                    and cert_line_code == selected_line_code
                )
            ):
                continue
            if identity_state == "facility_wide" and cert_identity != "facility_wide":
                continue
            display_line_code = (
                cert_line_code if cert_identity == "canonical"
                else resolved_line_code
            )
            context_match_kind = (
                "exact_line"
                if identity_state == "canonical" and cert_line_id == selected_line_id
                else "facility_wide"
                if identity_state == "canonical" and cert_identity == "facility_wide"
                else self._normalize_match_kind(normalized_line_code, display_line_code)
            )
            version = SimpleNamespace(
                expiry_date=row["version_expiry_date"],
                issue_date=row["version_issue_date"],
            )
            items.append({
                "certificate_id": row["cert_id"],
                "site_id": row["cert_site_id"],
                "case_id": row["cert_case_id"],
                "certificate_type": row["cert_type"],
                "line_code": display_line_code,
                "production_line_id": cert_line_id,
                "production_line_code": cert_line_code,
                "production_line_identity_state": cert_identity,
                "context_match_kind": context_match_kind,
                "latest_flag": row["cert_latest_flag"],
                "certificate_number": row["version_number"],
                "issue_date": row["version_issue_date"],
                "expiry_date": row["version_expiry_date"],
                "applicable_standard": row["version_standard"],
                "issuing_authority": row["version_authority"],
                "status": self._derive_certificate_status(
                    CertificateContextRow(
                        certificate=certificate,
                        version=version,
                        line_code=resolved_line_code,
                        scope_summary=None,
                    )
                ),
            })
        items.sort(
            key=lambda item: (
                0 if item["context_match_kind"] == "exact_line"
                else 1 if item["context_match_kind"] == "facility_wide" else 2,
                -(item["issue_date"].toordinal())
                if item["issue_date"] is not None else float("inf"),
                -(item["expiry_date"].toordinal())
                if item["expiry_date"] is not None else float("inf"),
                item["certificate_number"] or "",
                item["certificate_id"],
            )
        )
        return {
            "items": items,
            "quarantined_historical_certificate_legacy_ids": quarantined_legacy_ids,
        }

    def get_gxp_certificate_version_history(
        self,
        session: Session,
        *,
        certificate_id: str,
    ) -> dict[str, object]:
        """Committed Certificate/Case/Line, Version and Scope in one read snapshot.

        A Session may hold a cached or locally dirty Certificate, Case,
        ProductionLine, Version or Scope. Recovery/history GET must not flush
        those drafts, refresh them, or combine separate READ COMMITTED SQL
        snapshots from concurrent owner and version updates.
        """
        with session.no_autoflush:
            snapshot = session.execute(
                select(
                    Certificate.id.label("root_id"),
                    Certificate.site_id.label("root_site_id"),
                    Certificate.case_id.label("root_case_id"),
                    Certificate.certificate_type.label("root_type"),
                    Certificate.issuance_basis.label("root_issuance_basis"),
                    Certificate.latest_flag.label("root_latest_flag"),
                    Certificate.production_line_id.label("root_line_id"),
                    Case.id.label("linked_case_id"),
                    Case.site_id.label("linked_case_site_id"),
                    Case.gxp_type.label("linked_case_type"),
                    ProductionLine.id.label("linked_line_id"),
                    ProductionLine.site_id.label("linked_line_site_id"),
                    CertificateVersion.id.label("version_id"),
                    CertificateVersion.version_no,
                    CertificateVersion.row_version,
                    CertificateVersion.is_latest_version,
                    CertificateVersion.lifecycle_state,
                    CertificateVersion.certificate_number,
                    CertificateVersion.issue_date,
                    CertificateVersion.expiry_date,
                    CertificateVersion.applicable_standard,
                    CertificateVersion.issuing_authority,
                    CertificateScope.id.label("scope_id"),
                    CertificateScope.scope_key,
                    CertificateScope.scope_text,
                    CertificateScope.language_code,
                    CertificateScope.sort_order,
                    CertificateScope.created_at.label("scope_created_at"),
                )
                .select_from(Certificate)
                .outerjoin(Case, Case.id == Certificate.case_id)
                .outerjoin(
                    ProductionLine, ProductionLine.id == Certificate.production_line_id,
                )
                .outerjoin(
                    CertificateVersion,
                    CertificateVersion.certificate_id == Certificate.id,
                )
                .outerjoin(
                    CertificateScope,
                    CertificateScope.certificate_version_id == CertificateVersion.id,
                )
                .where(Certificate.id == certificate_id)
                .order_by(
                    CertificateVersion.version_no.desc(),
                    CertificateVersion.id.asc(),
                    CertificateScope.sort_order.asc(),
                    CertificateScope.created_at.asc(),
                    CertificateScope.id.asc(),
                )
            ).mappings().all()
        if not snapshot:
            raise HTTPException(status_code=404, detail="Certificate not found")
        root = snapshot[0]
        # Preserve canonical linked Case and ProductionLine integrity gates.
        # Evaluate against the committed root and its joined owners, never
        # against ORM identity-map instances from an older transaction.
        if root["root_case_id"] is not None and (
            root["linked_case_id"] != root["root_case_id"]
            or root["linked_case_site_id"] != root["root_site_id"]
            or root["linked_case_type"] != root["root_type"]
        ):
            raise HTTPException(
                status_code=409, detail="Certificate references an invalid linked Case.",
            )
        if root["root_line_id"] is not None and (
            root["linked_line_id"] != root["root_line_id"]
            or root["linked_line_site_id"] != root["root_site_id"]
        ):
            raise HTTPException(
                status_code=409,
                detail="Certificate references an invalid canonical ProductionLine.",
            )

        versions: dict[str, dict[str, object]] = {}
        scoped: dict[str, list[SimpleNamespace]] = defaultdict(list)
        for row in snapshot:
            version_id = row["version_id"]
            # Outer join retains Certificate root with no versions.
            if version_id is None:
                continue
            if version_id not in versions:
                versions[version_id] = {
                    "certificate_version_id": version_id,
                    "version_no": row["version_no"],
                    "row_version": row["row_version"],
                    "is_latest_version": row["is_latest_version"],
                    # NULL lifecycle means unproven imported legacy grant.
                    "lifecycle_state": row["lifecycle_state"],
                    "certificate_number": row["certificate_number"],
                    "issue_date": row["issue_date"],
                    "expiry_date": row["expiry_date"],
                    "applicable_standard": row["applicable_standard"],
                    "issuing_authority": row["issuing_authority"],
                }
            if row["scope_id"] is not None:
                scoped[version_id].append(SimpleNamespace(
                    id=row["scope_id"],
                    scope_key=row["scope_key"],
                    scope_text=row["scope_text"],
                    language_code=row["language_code"],
                    sort_order=row["sort_order"],
                    created_at=row["scope_created_at"],
                ))
        latest_ids = [
            version_id for version_id, version in versions.items()
            if version["is_latest_version"]
        ]
        if len(latest_ids) > 1:
            raise HTTPException(
                status_code=409,
                detail="Certificate has ambiguous latest CertificateVersion identity.",
            )
        return {
            "certificate_id": root["root_id"],
            "site_id": root["root_site_id"],
            "case_id": root["root_case_id"],
            "certificate_type": root["root_type"],
            "issuance_basis": root["root_issuance_basis"],
            "aggregate_latest_flag": root["root_latest_flag"],
            "latest_version_id": latest_ids[0] if latest_ids else None,
            "versions": [
                {
                    **version,
                    "scope_summary": self._build_certificate_scope_summary(scoped[version_id]),
                    "scopes": [
                        {
                            "id": scope.id,
                            "scope_key": scope.scope_key,
                            "scope_text": scope.scope_text,
                            "language_code": scope.language_code,
                            "sort_order": scope.sort_order,
                        }
                        for scope in scoped[version_id]
                    ],
                }
                for version_id, version in versions.items()
            ],
        }

    def get_gxp_certificate_detail(self, session: Session, *, certificate_id: str):
        """Read one committed Certificate detail and its exact latest Scope owner.

        Keep the API's existing projection while avoiding ORM autoflush, dirty
        identity-map reuse, and mixed READ COMMITTED snapshots across root,
        Case, Site/Company, canonical line, latest Version, Scope and inspection
        timing. This is a read-only owner boundary, not version issuance proof.
        """
        last_inspection_event = (
            select(func.max(InspectionEvent.occurred_at))
            .where(
                InspectionEvent.case_id == Certificate.case_id,
                InspectionEvent.event_type == InspectionEventType.INSPECTION_EXECUTED,
            )
            .correlate(Certificate)
            .scalar_subquery()
        )
        with session.no_autoflush:
            snapshot = session.execute(
                select(
                    Certificate.id.label("cert_id"),
                    Certificate.row_version.label("cert_row_version"),
                    Certificate.site_id.label("cert_site_id"),
                    Certificate.case_id.label("cert_case_id"),
                    Certificate.certificate_type.label("cert_type"),
                    Certificate.line_code.label("cert_line_code"),
                    Certificate.issuance_basis.label("cert_issuance_basis"),
                    Certificate.latest_flag.label("cert_latest_flag"),
                    Certificate.production_line_id.label("cert_line_id"),
                    Case.id.label("case_id"),
                    Case.site_id.label("case_site_id"),
                    Case.gxp_type.label("case_gxp_type"),
                    Case.scope_code.label("case_scope_code"),
                    Case.legacy_inspection_code.label("case_inspection_code"),
                    Site.id.label("site_id"),
                    Site.company_id.label("site_company_id"),
                    Site.site_name.label("site_name"),
                    Site.site_address.label("site_address"),
                    Company.id.label("company_id"),
                    Company.legal_name.label("company_legal_name"),
                    Company.legal_address.label("company_legal_address"),
                    ProductionLine.id.label("line_id"),
                    ProductionLine.site_id.label("line_site_id"),
                    ProductionLine.code.label("line_code"),
                    CertificateVersion.id.label("version_id"),
                    CertificateVersion.certificate_number.label("version_number"),
                    CertificateVersion.issue_date.label("version_issue_date"),
                    CertificateVersion.expiry_date.label("version_expiry_date"),
                    CertificateVersion.applicable_standard.label("version_standard"),
                    CertificateVersion.issuing_authority.label("version_authority"),
                    CertificateScope.id.label("scope_id"),
                    CertificateScope.scope_key,
                    CertificateScope.scope_text,
                    CertificateScope.language_code,
                    CertificateScope.sort_order,
                    CertificateScope.created_at.label("scope_created_at"),
                    InspectionOutcome.inspected_on.label("outcome_inspected_on"),
                    InspectionOutcome.inspected_to_on.label("outcome_inspected_to_on"),
                    last_inspection_event.label("event_inspected_at"),
                )
                .select_from(Certificate)
                .outerjoin(Case, Case.id == Certificate.case_id)
                .outerjoin(Site, Site.id == Certificate.site_id)
                .outerjoin(Company, Company.id == Site.company_id)
                .outerjoin(
                    ProductionLine, ProductionLine.id == Certificate.production_line_id,
                )
                .outerjoin(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .outerjoin(
                    CertificateScope,
                    CertificateScope.certificate_version_id == CertificateVersion.id,
                )
                .outerjoin(
                    InspectionOutcome, InspectionOutcome.case_id == Certificate.case_id,
                )
                .where(Certificate.id == certificate_id)
                .order_by(
                    CertificateVersion.id.asc(),
                    CertificateScope.sort_order.asc(),
                    CertificateScope.created_at.asc(),
                    CertificateScope.id.asc(),
                )
            ).mappings().all()

        if not snapshot:
            raise HTTPException(status_code=404, detail="Certificate not found")
        root = snapshot[0]
        if root["cert_case_id"] is not None and (
            root["case_id"] != root["cert_case_id"]
            or root["case_site_id"] != root["cert_site_id"]
            or root["case_gxp_type"] != root["cert_type"]
        ):
            raise HTTPException(
                status_code=409, detail="Certificate references an invalid linked Case.",
            )
        if root["cert_line_id"] is not None:
            if root["line_id"] != root["cert_line_id"]:
                raise HTTPException(
                    status_code=409,
                    detail="Canonical ProductionLine reference is missing.",
                )
            if root["line_site_id"] != root["cert_site_id"]:
                raise HTTPException(
                    status_code=409,
                    detail="Canonical ProductionLine reference belongs to a different site.",
                )
        if root["site_id"] is None:
            raise HTTPException(status_code=404, detail="Site not found")
        if root["company_id"] is None:
            raise HTTPException(status_code=404, detail="Company not found")

        current_version_ids = {
            row["version_id"] for row in snapshot if row["version_id"] is not None
        }
        if not current_version_ids:
            raise HTTPException(status_code=404, detail="Certificate latest version not found")
        if len(current_version_ids) != 1:
            raise HTTPException(
                status_code=409,
                detail="Certificate has ambiguous latest CertificateVersion identity.",
            )
        certificate = SimpleNamespace(
            id=root["cert_id"],
            row_version=root["cert_row_version"],
            site_id=root["cert_site_id"],
            case_id=root["cert_case_id"],
            certificate_type=root["cert_type"],
            line_code=root["cert_line_code"],
            issuance_basis=root["cert_issuance_basis"],
            latest_flag=root["cert_latest_flag"],
            production_line_id=root["cert_line_id"],
        )
        linked_case = (
            SimpleNamespace(
                id=root["case_id"],
                gxp_type=root["case_gxp_type"],
                scope_code=root["case_scope_code"],
                legacy_inspection_code=root["case_inspection_code"],
            )
            if root["case_id"] is not None else None
        )
        site = SimpleNamespace(
            id=root["site_id"],
            company_id=root["site_company_id"],
            site_name=root["site_name"],
            site_address=root["site_address"],
        )
        company = SimpleNamespace(
            id=root["company_id"],
            legal_name=root["company_legal_name"],
            legal_address=root["company_legal_address"],
        )
        version = SimpleNamespace(
            certificate_number=root["version_number"],
            issue_date=root["version_issue_date"],
            expiry_date=root["version_expiry_date"],
            applicable_standard=root["version_standard"],
            issuing_authority=root["version_authority"],
        )
        scope_rows = [
            SimpleNamespace(
                id=row["scope_id"],
                scope_key=row["scope_key"],
                scope_text=row["scope_text"],
                language_code=row["language_code"],
                sort_order=row["sort_order"],
                created_at=row["scope_created_at"],
            )
            for row in snapshot if row["scope_id"] is not None
        ]
        inspected_on = root["outcome_inspected_to_on"] or root["outcome_inspected_on"]
        if inspected_on is None and root["event_inspected_at"] is not None:
            inspected_on = root["event_inspected_at"].date()

        scope_summary = self._build_certificate_scope_summary(scope_rows)
        context = CertificateContextRow(
            certificate=certificate,
            version=version,
            line_code=self._certificate_line_code(certificate, linked_case),
            scope_summary=scope_summary,
        )
        payload = self._serialize_gxp_certificate_detail(
            certificate=certificate,
            version=version,
            linked_case=linked_case,
            site=site,
            company=company,
            scope_summary=scope_summary,
            scope_rows=scope_rows,
            inspected_on=inspected_on,
        )
        lines = (
            {
                root["line_id"]: SimpleNamespace(
                    id=root["line_id"],
                    site_id=root["line_site_id"],
                    code=root["line_code"],
                )
            }
            if root["line_id"] is not None else {}
        )
        production_line_id, production_line_code, identity_state = self._line_identity(
            site_id=certificate.site_id,
            production_line_id=certificate.production_line_id,
            raw_line_code=context.line_code,
            lines=lines,
        )
        payload.update({
            "production_line_id": production_line_id,
            "production_line_code": production_line_code,
            "production_line_identity_state": identity_state,
            "line_code": production_line_code if identity_state == "canonical" else context.line_code,
        })
        return payload

    def list_site_business_eligibility_certificates(
        self,
        session: Session,
        *,
        site_id: str,
        user: AuthenticatedUser | None = None,
    ):
        self.get_site(session, site_id)
        latest_version_sq = self._build_latest_business_eligibility_version_subquery()
        rows = list(
            session.execute(
                select(BusinessEligibilityCertificate, BusinessEligibilityVersion)
                .join(
                    latest_version_sq,
                    latest_version_sq.c.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                )
                .join(
                    BusinessEligibilityVersion,
                    and_(
                        BusinessEligibilityVersion.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                        BusinessEligibilityVersion.version_no == latest_version_sq.c.max_version_no,
                    ),
                )
                .where(BusinessEligibilityCertificate.site_id == site_id)
            ).all()
        )
        items = [
            {
                "business_eligibility_certificate_id": certificate.id,
                "site_id": certificate.site_id,
                "company_id": certificate.company_id,
                "latest_flag": certificate.latest_flag,
                "certificate_number": version.certificate_number,
                "issued_on": version.issued_on,
                "issuance_sequence_text": version.issuance_sequence_text,
                "current_status_text": version.current_status_text,
            }
            for certificate, version in rows
        ]
        items.sort(
            key=lambda item: (
                -(item["issued_on"].toordinal()) if item["issued_on"] is not None else float("inf"),
                item["issuance_sequence_text"] or "",
                item["certificate_number"] or "",
                item["business_eligibility_certificate_id"],
            )
        )
        issue_readiness = (
            None
            if user is None
            else CaseWorkflowService().get_business_eligibility_issue_readiness(
                session,
                site_id=site_id,
                user=user,
            )
        )
        return {"items": items, "issue_readiness": issue_readiness}

    def get_business_eligibility_gxp_source_evidence(
        self,
        session: Session,
        *,
        business_eligibility_certificate_id: str,
    ) -> dict[str, object]:
        """Read a DDK row's original GMP/GLP/GSP/GDP cells without canonical links.

        A stable canonical DDK UUID selects only its own legacy DDK row ID.
        The source Excel worksheet is a *separate* observation: it is not
        evidence of a Certificate link, site coverage, business grant or
        historical version. Do not use ID CC as a canonical UUID.
        """
        certificate = session.get(BusinessEligibilityCertificate, business_eligibility_certificate_id)
        if certificate is None:
            raise HTTPException(status_code=404, detail="Business eligibility certificate not found")

        identity = certificate.legacy_dkkd_id
        result = {
            "business_eligibility_certificate_id": certificate.id,
            "legacy_dkkd_id": identity,
            "source_status": "legacy_identity_missing" if identity is None else "not_in_imported_source",
            "evidence_kind": "original_excel_cells_source_only",
            "canonical_links_included": False,
            "source_workbook_sha256": None,
            "source_sheet_name": None,
            "source_row_number": None,
            "groups": [],
        }
        if identity is None:
            return result

        source_rows = list(session.scalars(
            select(BusinessEligibilityGxpSourceGroup)
            .where(BusinessEligibilityGxpSourceGroup.legacy_dkkd_id == identity)
            .order_by(
                BusinessEligibilityGxpSourceGroup.source_workbook_sha256,
                BusinessEligibilityGxpSourceGroup.source_row_number,
                BusinessEligibilityGxpSourceGroup.id_cc_excel_column,
            )
        ))
        if not source_rows:
            return result

        # One canonical legacy DDK ID can map to exactly one original physical
        # workbook row. Refuse multiple original row keys, rather than mixing
        # cells from separate physical DDKs or separate workbook snapshots.
        source_origins = {
            (
                group.source_workbook_sha256,
                group.source_sheet_name,
                group.source_row_number,
            )
            for group in source_rows
        }
        if len(source_origins) != 1:
            raise HTTPException(
                status_code=409,
                detail="Multiple physical source DDK row identities match this legacy DDK ID.",
            )
        roles = {group.source_group for group in source_rows}
        if (
            len(source_rows) != 4
            or roles != {"GMP", "GLP", "GSP", "GDP"}
            or len({group.id_cc_excel_column for group in source_rows}) != 4
        ):
            raise HTTPException(
                status_code=409,
                detail="Original DDK source row has incomplete or duplicate GxP physical groups.",
            )

        refs_by_group: dict[str, list[dict[str, object]]] = defaultdict(list)
        for reference in session.scalars(
            select(BusinessEligibilityGxpReferenceEvidence)
            .where(BusinessEligibilityGxpReferenceEvidence.source_group_id.in_(
                [group.id for group in source_rows]
            ))
            .order_by(
                BusinessEligibilityGxpReferenceEvidence.source_group_id,
                BusinessEligibilityGxpReferenceEvidence.token_index,
            )
        ):
            refs_by_group[reference.source_group_id].append({
                "source_reference_id": reference.id,
                "token_index": reference.token_index,
                "raw_token": reference.raw_token,
                "parsed_legacy_certificate_id": reference.parsed_legacy_certificate_id,
            })
        # Preserve all four distinct original cells and token ordinal order;
        # especially do not discard scope/activity when ID CC is empty.
        result["source_status"] = "available"
        first = source_rows[0]
        result["source_workbook_sha256"] = first.source_workbook_sha256
        result["source_sheet_name"] = first.source_sheet_name
        result["source_row_number"] = first.source_row_number
        result["groups"] = [{
            "source_group_id": group.id,
            "source_group": group.source_group,
            "id_cc_excel_column": group.id_cc_excel_column,
            "certificate_scope_excel_column": group.certificate_scope_excel_column,
            "applicable_standard_excel_column": group.applicable_standard_excel_column,
            "business_activity_excel_column": group.business_activity_excel_column,
            "id_cc_raw": group.id_cc_raw,
            "certificate_scope_raw": group.certificate_scope_raw,
            "applicable_standard_raw": group.applicable_standard_raw,
            "business_activity_raw": group.business_activity_raw,
            "source_values_sha256": group.source_values_sha256,
            "reference_tokens": refs_by_group[group.id],
        } for group in source_rows]
        return result

    def get_business_eligibility_version_history(
        self,
        session: Session,
        *,
        business_eligibility_certificate_id: str,
    ) -> dict[str, object]:
        """Return saved DDK versions without manufacturing legacy history.

        For ĐĐK, "latest" is max persisted version_no, not a per-version
        is_latest flag. Version-specific FK link rows are *recorded facts*,
        not approvals or inferred source ID CC/cross-site validity.
        """
        certificate = session.get(
            BusinessEligibilityCertificate, business_eligibility_certificate_id,
        )
        if certificate is None:
            raise HTTPException(status_code=404, detail="Business eligibility certificate not found")
        versions = list(session.scalars(
            select(BusinessEligibilityVersion)
            .where(
                BusinessEligibilityVersion.business_eligibility_certificate_id == certificate.id,
            )
            .order_by(
                BusinessEligibilityVersion.version_no.desc(),
                BusinessEligibilityVersion.id.asc(),
            )
        ))
        links_by_version: dict[str, list[dict[str, object]]] = defaultdict(list)
        if versions:
            links = session.scalars(
                select(BusinessEligibilityCertificateLink)
                .where(
                    BusinessEligibilityCertificateLink.business_eligibility_version_id.in_(
                        [version.id for version in versions],
                    )
                )
                .order_by(
                    BusinessEligibilityCertificateLink.business_eligibility_version_id,
                    BusinessEligibilityCertificateLink.certificate_id,
                    BusinessEligibilityCertificateLink.id,
                )
            )
            for link in links:
                links_by_version[link.business_eligibility_version_id].append({
                    "link_id": link.id,
                    "certificate_id": link.certificate_id,
                    "link_role": link.link_role,
                })
        # Every value here is stored on its own version. In particular,
        # issuance_history_text is an original text field, NOT extra versions.
        historical_fields = (
            "certificate_number", "issued_on", "expires_on",
            "professional_responsible_person_name", "quality_assurance_person_name",
            "professional_qualification_text", "professional_license_number",
            "professional_license_issued_on", "professional_license_issuer",
            "responsible_license_issued_on", "responsible_license_issuer",
            "decision_reference", "issuance_sequence_text", "issuance_history_text",
            "business_activity_text", "current_status_text", "handled_by_name",
            "application_dossier_reference", "notes",
        )
        return {
            "business_eligibility_certificate_id": certificate.id,
            "legacy_dkkd_id": certificate.legacy_dkkd_id,
            "site_id": certificate.site_id,
            "company_id": certificate.company_id,
            "aggregate_latest_flag": certificate.latest_flag,
            "latest_version_id": versions[0].id if versions else None,
            "latest_selection_method": "max_persisted_version_no",
            "gxp_source_tokens_included": False,
            "canonical_link_status": "stored_fk_only_not_validated",
            "versions": [
                {
                    "business_eligibility_version_id": version.id,
                    "version_no": version.version_no,
                    "row_version": version.row_version,
                    **{key: getattr(version, key) for key in historical_fields},
                    "stored_link_records": links_by_version[version.id],
                }
                for version in versions
            ],
        }

    def get_business_eligibility_detail(
        self,
        session: Session,
        *,
        business_eligibility_certificate_id: str,
        user: AuthenticatedUser | None = None,
    ):
        certificate = session.get(BusinessEligibilityCertificate, business_eligibility_certificate_id)
        if certificate is None:
            raise HTTPException(status_code=404, detail="Business eligibility certificate not found")
        site = self.get_site(session, certificate.site_id)
        company = self.get_company(session, certificate.company_id)
        latest_version_sq = self._build_latest_business_eligibility_version_subquery()
        version = session.scalar(
            select(BusinessEligibilityVersion)
            .join(
                latest_version_sq,
                and_(
                    latest_version_sq.c.business_eligibility_certificate_id == BusinessEligibilityVersion.business_eligibility_certificate_id,
                    latest_version_sq.c.max_version_no == BusinessEligibilityVersion.version_no,
                ),
            )
            .where(BusinessEligibilityVersion.business_eligibility_certificate_id == certificate.id)
        )
        if version is None:
            raise HTTPException(status_code=404, detail="Business eligibility latest version not found")

        linked_rows = list(
            session.execute(
                select(BusinessEligibilityCertificateLink, Certificate, CertificateVersion)
                .join(Certificate, Certificate.id == BusinessEligibilityCertificateLink.certificate_id)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(BusinessEligibilityCertificateLink.business_eligibility_version_id == version.id)
            ).all()
        )
        linked_gxp_certificates = [
            {
                "certificate_id": linked_certificate.id,
                "certificate_type": linked_certificate.certificate_type,
                "line_code": CaseWorkflowService._certificate_line_identity(session, linked_certificate)["production_line_code"],
                "certificate_number": linked_version.certificate_number,
                "issue_date": linked_version.issue_date,
                "link_role": link.link_role,
            }
            for link, linked_certificate, linked_version in linked_rows
        ]
        linked_gxp_certificates.sort(
            key=lambda item: (
                item["certificate_type"],
                item["line_code"] or "",
                -(item["issue_date"].toordinal()) if item["issue_date"] is not None else float("inf"),
                item["certificate_number"] or "",
                item["certificate_id"],
            )
        )

        replacement_map: dict[int, str | None] = {}
        replacement_ids = [value for value in [certificate.replaces_legacy_dkkd_id, certificate.replaced_by_legacy_dkkd_id] if value is not None]
        if replacement_ids:
            latest_versions_by_legacy_id = {
                legacy_id: number
                for legacy_id, number in session.execute(
                    select(BusinessEligibilityCertificate.legacy_dkkd_id, BusinessEligibilityVersion.certificate_number)
                    .join(
                        latest_version_sq,
                        latest_version_sq.c.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                    )
                    .join(
                        BusinessEligibilityVersion,
                        and_(
                            BusinessEligibilityVersion.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                            BusinessEligibilityVersion.version_no == latest_version_sq.c.max_version_no,
                        ),
                    )
                    .where(BusinessEligibilityCertificate.legacy_dkkd_id.in_(replacement_ids))
                )
            }
            replacement_map.update(latest_versions_by_legacy_id)

        action_readiness = (
            []
            if user is None
            else CaseWorkflowService().get_business_eligibility_action_readiness(
                session,
                business_eligibility_certificate_id=certificate.id,
                user=user,
            )
        )
        return self._serialize_business_eligibility_detail(
            certificate=certificate,
            version=version,
            site=site,
            company=company,
            linked_gxp_certificates=linked_gxp_certificates,
            replacement_map=replacement_map,
            action_readiness=action_readiness,
        )

    def get_case_workspace(self, session: Session, *, case_id: str, user: AuthenticatedUser):
        case = self.get_case(session, case_id)
        self._assert_certificate_links_valid(session, site_id=case.site_id)
        site = self.get_site(session, case.site_id)
        company = self.get_company(session, site.company_id)

        application = session.scalar(select(CaseApplication).where(CaseApplication.case_id == case.id))
        assessment = session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == case.id))
        plan = session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case.id))
        team = session.scalar(select(InspectionTeam).where(InspectionTeam.case_id == case.id))
        team_members = [] if team is None else list(
            session.scalars(
                select(InspectionTeamMember)
                .where(InspectionTeamMember.team_id == team.id)
                .order_by(InspectionTeamMember.sort_order.asc(), InspectionTeamMember.id.asc())
            )
        )
        team_identity_state = (
            None
            if team is None
            else inspection_team_existing_identity_state(session, members=team_members)
        )
        team_round_trip_safe = team is None or bool(team_identity_state["round_trip_safe"])
        team_blocked_reason = (
            None if team_identity_state is None else team_identity_state["blocked_reason_code"]
        )
        serialized_team_members: list[dict[str, object]] = []
        for member in team_members:
            member_state = team_identity_state["member_states"][member.id]
            serialized_team_members.append({
                "id": member.id,
                "inspector_profile_id": member.inspector_profile_id,
                "person_id": member.person_id,
                "display_name": member.display_name or member_state["display_name"],
                "identity_kind": member.identity_kind,
                "participant_catalog_id": member.participant_catalog_id,
                "legacy_source_token": member.legacy_source_token,
                "role_code": member.role_code,
                "role_label": member.role_label,
                "sort_order": member.sort_order,
                "identity_status": member_state["identity_status"],
            })
        permissions = self._effective_permissions(user)
        outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case.id))
        period_segments = [] if outcome is None else list(session.scalars(
            select(InspectionPeriodSegment)
            .where(InspectionPeriodSegment.inspection_outcome_id == outcome.id)
            .order_by(InspectionPeriodSegment.ordinal.asc(), InspectionPeriodSegment.id.asc())
        ))
        approval_submissions = list(session.scalars(
            select(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.case_id == case.id)
            .order_by(InspectionApprovalSubmission.stage.asc(), InspectionApprovalSubmission.round_no.asc())
            .execution_options(populate_existing=True)
        ))
        events = list(
            session.scalars(
                select(InspectionEvent)
                .where(InspectionEvent.case_id == case.id)
                .order_by(InspectionEvent.occurred_at.asc(), InspectionEvent.created_at.asc(), InspectionEvent.id.asc())
            )
        )
        capa_cycles = list(
            session.scalars(
                select(CapaCycle)
                .where(CapaCycle.case_id == case.id)
                .order_by(CapaCycle.round_no.asc(), CapaCycle.created_at.asc(), CapaCycle.id.asc())
            )
        )

        terminal_case = case.state in {CaseState.CLOSED, CaseState.CANCELLED}
        inspection_permission = "inspection.edit"
        from backend.app.services.workflow import (
            ALLOWED_CASE_TRANSITIONS,
            case_transition_eligibility_reason,
            inspection_period_edit_readiness,
            inspection_team_edit_readiness,
        )
        # Read-only projection of the three existing Case stage editors.
        # Their mutations share the Case owner lock and accept a nullable
        # stage-specific expected_version. No state-based UI guesswork:
        # only permission and terminal status block those service methods.
        stage_edit_actions = [
            {
                "action_key": action_key,
                "label": label,
                "available": permission in permissions and not terminal_case,
                "reason_code": (
                    "missing_permission" if permission not in permissions
                    else "terminal_case" if terminal_case else None
                ),
                "required_permissions": [permission],
                "expected_version": None if stage is None else stage.row_version,
            }
            for action_key, label, permission, stage in (
                ("edit_case_application", "Cập nhật hồ sơ đăng ký", "case.edit", application),
                ("edit_case_assessment", "Cập nhật thẩm định hồ sơ", "case.edit", assessment),
                ("edit_inspection_plan", "Cập nhật kế hoạch kiểm tra", "inspection.edit", plan),
            )
        ]
        # The existing inspection-outcome mutation accepts a nullable child
        # expected_version. It permits metadata-only edits on nonterminal Cases;
        # period-specific writes still have their separate source-owned guard.
        outcome_edit_reason = (
            "missing_permission" if inspection_permission not in permissions
            else "terminal_case" if terminal_case
            else None
        )
        outcome_edit_readiness = {
            "action_key": "edit_inspection_outcome",
            "label": "Cập nhật kết quả kiểm tra",
            "available": outcome_edit_reason is None,
            "reason_code": outcome_edit_reason,
            "required_permissions": [inspection_permission],
            "expected_version": None if outcome is None else outcome.row_version,
        }
        period_edit_readiness = inspection_period_edit_readiness(outcome=outcome, terminal_case=terminal_case)
        if inspection_permission not in permissions:
            period_edit_readiness = {**period_edit_readiness, "available": False, "reason_code": "missing_permission"}
        team_edit_readiness = inspection_team_edit_readiness(
            team=team,
            terminal_case=terminal_case,
            round_trip_safe=team_round_trip_safe,
            blocked_reason_code=team_blocked_reason,
        )
        if inspection_permission not in permissions:
            team_edit_readiness = {**team_edit_readiness, "available": False, "reason_code": "missing_permission"}
        final_evaluation_reason = None
        if inspection_permission not in permissions:
            final_evaluation_reason = "missing_permission"
        elif terminal_case:
            final_evaluation_reason = "terminal_case"
        elif outcome is None:
            final_evaluation_reason = "outcome_missing"
        elif outcome.final_evaluation is not None:
            final_evaluation_reason = "already_finalized"
        elif capa_cycles and capa_cycles[-1].status != "accepted":
            final_evaluation_reason = "latest_capa_not_accepted"
        final_evaluation_readiness = {
            "action_key": "finalize_inspection_outcome",
            "label": "Chốt đánh giá cuối cùng",
            "available": final_evaluation_reason is None,
            "reason_code": final_evaluation_reason,
            "required_permissions": [inspection_permission],
            "expected_version": None if outcome is None else outcome.row_version,
        }
        approval_actions: list[dict[str, object]] = []
        if inspection_permission not in permissions:
            approval_reason = "missing_permission"
        elif terminal_case:
            approval_reason = "terminal_case"
        else:
            approval_reason = None
        for stage in ("PCT", "CT"):
            stage_reason = approval_reason
            if stage_reason is None and stage == "CT":
                if not any(item.stage == "PCT" and item.completed_on is not None for item in approval_submissions):
                    stage_reason = "completed_pct_required"
            approval_actions.append({
                "action_key": f"create_approval_{stage.lower()}",
                "label": f"Tạo trình {stage}",
                "available": stage_reason is None,
                "reason_code": stage_reason,
                "required_permissions": [inspection_permission],
                "expected_version": None,
            })
        for submission in approval_submissions:
            complete_reason = approval_reason or ("already_completed" if submission.completed_on is not None else None)
            approval_actions.append({
                "action_key": f"complete_approval:{submission.id}",
                "label": f"Hoàn tất {submission.stage} lần {submission.round_no}",
                "available": complete_reason is None,
                "reason_code": complete_reason,
                "required_permissions": [inspection_permission],
                "expected_version": submission.row_version,
            })
        transition_actions: list[dict[str, object]] = []
        transition_permission = "case.edit"
        # Use the service-owned transition eligibility predicate, not a UI copy.
        for target in sorted(ALLOWED_CASE_TRANSITIONS.get(case.state, set()), key=lambda value: value.value):
            reason = None if transition_permission in permissions else "missing_permission"
            if reason is None:
                latest = capa_cycles[-1] if capa_cycles else None
                reason = case_transition_eligibility_reason(
                    current_state=case.state,
                    target_state=target,
                    latest_capa_status=None if latest is None else latest.status,
                    nonissuance_decision_recorded=(
                        CaseWorkflowService().get_case_nonissuance_decision(
                            session, case_id=case.id,
                        )["decision"] is not None
                    ),
                )
            transition_actions.append({
                "action_key": f"transition:{target.value}",
                "label": target.value,
                "available": reason is None,
                "reason_code": reason,
                "required_permissions": [transition_permission],
                "expected_version": case.row_version,
                "target_state": target.value,
            })

        latest_capa = capa_cycles[-1] if capa_cycles else None
        create_capa_reason = None
        if "capa.edit" not in permissions:
            create_capa_reason = "missing_permission"
        elif terminal_case:
            create_capa_reason = "terminal_case"
        elif case.state != CaseState.INSPECTION_COMPLETED:
            create_capa_reason = "invalid_case_state"
        elif latest_capa is not None and latest_capa.status != "rejected":
            create_capa_reason = "latest_cycle_not_rejected"
        capa_actions = [
            {
                "action_key": "create_capa_cycle",
                "label": "Thêm vòng khắc phục",
                "available": create_capa_reason is None,
                "reason_code": create_capa_reason,
                "required_permissions": ["capa.edit"],
                "expected_version": case.row_version,
            }
        ]
        for cycle in capa_cycles:
            for action_key, permission, allowed in (
                ("update_capa_cycle", "capa.edit", {"requested", "rejected"}),
                ("submit_capa_cycle", "capa.edit", {"requested", "rejected"}),
                ("assess_capa_cycle", "capa.assess", {"submitted"}),
            ):
                latest_cycle = capa_cycles[-1] if capa_cycles else None
                is_latest = latest_cycle is not None and latest_cycle.id == cycle.id
                available = permission in permissions and not terminal_case and is_latest and cycle.status in allowed
                capa_actions.append({
                    "action_key": f"{action_key}:{cycle.id}",
                    "label": action_key,
                    "available": available,
                    "reason_code": None if available else ("missing_permission" if permission not in permissions else ("historical_cycle" if not is_latest else "invalid_cycle_state")),
                    "required_permissions": [permission],
                    "expected_version": cycle.row_version,
                })

        gxp_certificate_rows = list(
            session.execute(
                select(Certificate, CertificateVersion)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(Certificate.case_id == case.id)
                .execution_options(populate_existing=True)
            ).all()
        )
        certificate_ids = [certificate.id for certificate, _ in gxp_certificate_rows]
        version_ids = [version.id for _, version in gxp_certificate_rows]
        scope_rows_by_version_id: dict[str, list[CertificateScope]] = defaultdict(list)
        if version_ids:
            for scope_row in session.scalars(
                select(CertificateScope)
                .where(CertificateScope.certificate_version_id.in_(version_ids))
                .order_by(CertificateScope.sort_order.asc(), CertificateScope.created_at.asc(), CertificateScope.id.asc())
            ):
                scope_rows_by_version_id[scope_row.certificate_version_id].append(scope_row)

        inspected_on = None
        if outcome is not None:
            inspected_on = outcome.inspected_to_on or outcome.inspected_on
        if inspected_on is None:
            executed_event = next(
                (row for row in reversed(events) if row.event_type == InspectionEventType.INSPECTION_EXECUTED and row.occurred_at is not None),
                None,
            )
            if executed_event is not None and executed_event.occurred_at is not None:
                inspected_on = executed_event.occurred_at.date()

        linked_gxp_certificates = []
        for certificate, version in gxp_certificate_rows:
            identity = CaseWorkflowService._certificate_line_identity(session, certificate)
            payload = self._serialize_gxp_certificate_detail(
                certificate=certificate,
                version=version,
                linked_case=case,
                site=site,
                company=company,
                scope_summary=self._build_certificate_scope_summary(scope_rows_by_version_id.get(version.id, [])),
                scope_rows=scope_rows_by_version_id.get(version.id, []),
                inspected_on=inspected_on,
            )
            payload.update(
                {
                    **identity,
                    "line_code": identity["production_line_code"],
                }
            )
            # Reuse Certificate aggregate owner readiness. A Case's GxP
            # issuance action is not authority to promote any linked record.
            # Each action below is bound to payload.certificate_id and the
            # Certificate root row_version, never the Case/version UUID.
            payload["action_readiness"] = CaseWorkflowService().get_certificate_action_readiness(
                session, certificate_id=certificate.id, user=user,
            )
            linked_gxp_certificates.append(payload)
        linked_gxp_certificates.sort(
            key=lambda item: (
                -(item["issue_date"].toordinal()) if item["issue_date"] is not None else float("inf"),
                item["certificate_number"] or "",
                item["certificate_id"],
            )
        )

        # Read-only facts; Case state alone does not prove issuance.
        # A complete record has all promotion-required certificate fields.
        complete_certificates = [
            item for item in linked_gxp_certificates
            if str(item["certificate_number"] or "").strip()
            and item["issue_date"] is not None
            and item["expiry_date"] is not None
        ]
        current_certificates = [
            item for item in complete_certificates if item["latest_flag"] is True
        ]
        # Date-interval integrity is separate from presence-based completeness.
        # Historical Current rows are observed, never silently changed here.
        invalid_interval_certificates = [
            item for item in complete_certificates
            if item["expiry_date"] < item["issue_date"]
        ]
        valid_interval_certificates = [
            item for item in complete_certificates
            if item["expiry_date"] >= item["issue_date"]
        ]
        current_invalid_interval_certificates = [
            item for item in invalid_interval_certificates if item["latest_flag"] is True
        ]
        completed_pct_ids = {
            item.id for item in approval_submissions
            if item.stage == "PCT" and item.completed_on is not None
        }
        completed_cts = [
            item for item in approval_submissions
            if item.stage == "CT" and item.completed_on is not None
        ]
        case_business_evidence = {
            "final_evaluation_recorded": outcome is not None and outcome.final_evaluation is not None,
            "latest_capa_status": None if latest_capa is None else latest_capa.status,
            "completed_pct_count": len(completed_pct_ids),
            "completed_ct_count": len(completed_cts),
            "completed_ct_with_pct_count": sum(
                1 for item in completed_cts if item.pct_submission_id in completed_pct_ids
            ),
            "linked_certificate_count": len(linked_gxp_certificates),
            "complete_certificate_record_count": len(complete_certificates),
            "current_certificate_record_count": len(current_certificates),
            "date_valid_certificate_record_count": len(valid_interval_certificates),
            "invalid_certificate_date_interval_count": len(invalid_interval_certificates),
            "current_invalid_certificate_date_interval_count": len(current_invalid_interval_certificates),
            "certified_case_without_date_valid_certificate_record": (
                case.state in {CaseState.CERTIFIED, CaseState.CLOSED}
                and not valid_interval_certificates
            ),
            "certificate_record_state": (
                "current" if current_certificates
                else "recorded_not_current" if complete_certificates
                else "incomplete" if linked_gxp_certificates else "none"
            ),
            "certified_case_without_complete_certificate_record": (
                case.state in {CaseState.CERTIFIED, CaseState.CLOSED}
                and not complete_certificates
            ),
        }

        latest_version_sq = self._build_latest_business_eligibility_version_subquery()
        linked_business_eligibility_certificates: list[dict[str, object]] = []
        if certificate_ids:
            linked_be_rows = list(
                session.execute(
                    select(BusinessEligibilityCertificate, BusinessEligibilityVersion)
                    .join(
                        latest_version_sq,
                        latest_version_sq.c.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                    )
                    .join(
                        BusinessEligibilityVersion,
                        and_(
                            BusinessEligibilityVersion.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                            BusinessEligibilityVersion.version_no == latest_version_sq.c.max_version_no,
                        ),
                    )
                    .join(
                        BusinessEligibilityCertificateLink,
                        BusinessEligibilityCertificateLink.business_eligibility_version_id == BusinessEligibilityVersion.id,
                    )
                    .where(BusinessEligibilityCertificateLink.certificate_id.in_(certificate_ids))
                ).all()
            )
            deduped_be_rows: dict[str, tuple[BusinessEligibilityCertificate, BusinessEligibilityVersion]] = {}
            for certificate_row, version_row in linked_be_rows:
                deduped_be_rows[certificate_row.id] = (certificate_row, version_row)

            be_rows = list(deduped_be_rows.values())
            be_version_ids = [version.id for _, version in be_rows]
            linked_basis_rows = list(
                session.execute(
                    select(BusinessEligibilityCertificateLink, Certificate, CertificateVersion)
                    .join(Certificate, Certificate.id == BusinessEligibilityCertificateLink.certificate_id)
                    .join(
                        CertificateVersion,
                        and_(
                            CertificateVersion.certificate_id == Certificate.id,
                            CertificateVersion.is_latest_version.is_(True),
                        ),
                    )
                    .where(BusinessEligibilityCertificateLink.business_eligibility_version_id.in_(be_version_ids))
                ).all()
            ) if be_version_ids else []

            linked_basis_by_version_id: dict[str, list[dict[str, object]]] = defaultdict(list)
            for link, linked_certificate, linked_version in linked_basis_rows:
                linked_basis_by_version_id[link.business_eligibility_version_id].append(
                    {
                        "certificate_id": linked_certificate.id,
                        "certificate_type": linked_certificate.certificate_type,
                        "line_code": CaseWorkflowService._certificate_line_identity(session, linked_certificate)["production_line_code"],
                        "certificate_number": linked_version.certificate_number,
                        "issue_date": linked_version.issue_date,
                        "link_role": link.link_role,
                    }
                )
            for payloads in linked_basis_by_version_id.values():
                payloads.sort(
                    key=lambda item: (
                        item["certificate_type"],
                        item["line_code"] or "",
                        -(item["issue_date"].toordinal()) if item["issue_date"] is not None else float("inf"),
                        item["certificate_number"] or "",
                        item["certificate_id"],
                    )
                )

            replacement_ids = [
                legacy_id
                for certificate_row, _ in be_rows
                for legacy_id in [certificate_row.replaces_legacy_dkkd_id, certificate_row.replaced_by_legacy_dkkd_id]
                if legacy_id is not None
            ]
            replacement_map: dict[int, str | None] = {}
            if replacement_ids:
                replacement_map.update(
                    {
                        legacy_id: number
                        for legacy_id, number in session.execute(
                            select(BusinessEligibilityCertificate.legacy_dkkd_id, BusinessEligibilityVersion.certificate_number)
                            .join(
                                latest_version_sq,
                                latest_version_sq.c.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                            )
                            .join(
                                BusinessEligibilityVersion,
                                and_(
                                    BusinessEligibilityVersion.business_eligibility_certificate_id == BusinessEligibilityCertificate.id,
                                    BusinessEligibilityVersion.version_no == latest_version_sq.c.max_version_no,
                                ),
                            )
                            .where(BusinessEligibilityCertificate.legacy_dkkd_id.in_(replacement_ids))
                        )
                    }
                )

            # Case context determines which GxP certificates are relevant,
            # not the ownership metadata of a linked ĐĐK. A legacy link can
            # cross Sites; never label that certificate with the Case's
            # facility/company merely because its basis GxP belongs here.
            be_sites = {
                item.id: item
                for item in session.scalars(
                    select(Site).where(Site.id.in_({
                        certificate_row.site_id for certificate_row, _ in be_rows
                    }))
                )
            }
            be_companies = {
                item.id: item
                for item in session.scalars(
                    select(Company).where(Company.id.in_({
                        certificate_row.company_id for certificate_row, _ in be_rows
                    }))
                )
            }
            linked_business_eligibility_certificates = [
                self._serialize_business_eligibility_detail(
                    certificate=certificate_row,
                    version=version_row,
                    site=be_sites[certificate_row.site_id],
                    company=be_companies[certificate_row.company_id],
                    linked_gxp_certificates=linked_basis_by_version_id.get(version_row.id, []),
                    replacement_map=replacement_map,
                )
                for certificate_row, version_row in be_rows
            ]
            linked_business_eligibility_certificates.sort(
                key=lambda item: (
                    -(item["issued_on"].toordinal()) if item["issued_on"] is not None else float("inf"),
                    item["issuance_sequence_text"] or "",
                    item["certificate_number"] or "",
                    item["business_eligibility_certificate_id"],
                )
            )

        # Reuse the canonical Case checklist once for both the document panel
        # and per-stage documentary visibility. Never infer a round binding.
        case_document_checklist = self._build_case_document_checklist(
            session, case_id=case.id, capa_cycles=capa_cycles,
        )
        # Explicit link facts are resolved through both canonical parents.
        # An orphan/cross-Case/mis-staged link is a data-integrity conflict,
        # never proof that the document belongs to the viewed submission.
        linked_rows = list(session.execute(
            select(InspectionApprovalDocumentLink, InspectionApprovalSubmission, Document)
            .join(
                InspectionApprovalSubmission,
                InspectionApprovalSubmission.id == InspectionApprovalDocumentLink.approval_submission_id,
            )
            .join(Document, Document.id == InspectionApprovalDocumentLink.document_id)
            .where(InspectionApprovalSubmission.case_id == case.id)
            .order_by(
                InspectionApprovalSubmission.stage.asc(),
                InspectionApprovalSubmission.round_no.asc(),
                InspectionApprovalDocumentLink.created_at.asc(),
                InspectionApprovalDocumentLink.id.asc(),
            )
            .execution_options(populate_existing=True)
        ).all())
        approval_document_links = []
        for link, submission, document in linked_rows:
            expected_family = "INSPECTION_PT_PCT" if submission.stage == "PCT" else "INSPECTION_PT_CT"
            if (
                submission.stage not in {"PCT", "CT"}
                or document.case_id != case.id
                or document.family_code != expected_family
                or any(parent is not None for parent in (
                    document.capa_cycle_id, document.certificate_id,
                    document.business_eligibility_certificate_id, document.change_request_id,
                ))
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Approval document link violates canonical Case/stage ownership.",
                )
            approval_document_links.append({
                "approval_submission_id": submission.id,
                "document_id": document.id,
                "binding_id": link.id,
                "stage": submission.stage,
                "round_no": submission.round_no,
            })
        approval_document_evidence = self._build_approval_document_evidence(
            approval_submissions=approval_submissions,
            document_checklist=case_document_checklist,
            linked_submission_ids={item["approval_submission_id"] for item in approval_document_links},
        )
        approval_document_candidates, approval_document_bind_readiness = (
            self._build_approval_document_candidates(
                session,
                case_id=case.id,
                approval_submissions=approval_submissions,
                approval_document_links=approval_document_links,
                permissions=permissions,
                terminal_case=terminal_case,
            )
        )
        return {
            "case_summary": {
                "id": case.id,
                "row_version": case.row_version,
                "legacy_inspection_id": case.legacy_inspection_id,
                "legacy_inspection_code": case.legacy_inspection_code,
                "site_id": case.site_id,
                "legacy_site_id": site.legacy_site_id,
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "gxp_type": case.gxp_type,
                "scope_code": case.scope_code,
                **dict(zip(("production_line_id", "production_line_code", "production_line_identity_state"), self._line_identity(
                    site_id=case.site_id, production_line_id=case.production_line_id,
                    raw_line_code=case.scope_code,
                    lines={line.id: line for line in session.scalars(select(ProductionLine).where(ProductionLine.site_id == case.site_id))},
                ))),
                "applicable_standard": case.applicable_standard,
                "inspection_type": case.inspection_type,
                "state": case.state.value,
                "opened_year": case.opened_year,
            },
            "application": {
                "row_version": None if application is None else application.row_version,
                "submitted_on": None if application is None else application.submitted_on,
                "dossier_code": None if application is None else application.dossier_code,
                "dossier_reference": None if application is None else application.dossier_reference,
                "applicant_name": None if application is None else application.applicant_name,
                "assigned_specialist": company.assigned_specialist_text,
                "assigned_specialist_source": None if company.assigned_specialist_text is None else "company_master",
            },
            "inspection": {
                "plan_row_version": None if plan is None else plan.row_version,
                "plan_decision_reference": None if plan is None else plan.decision_reference,
                "plan_decision_date": None if plan is None else plan.decision_date,
                "outcome_decision_reference_compatibility": None if outcome is None else outcome.decision_reference,
                "decision_document_hint": None if plan is None else plan.decision_document_hint,
                "plan_start_on": None if plan is None else plan.plan_start_on,
                "plan_end_on": None if plan is None else plan.plan_end_on,
                "planning_sheet_name": None if plan is None else plan.planning_sheet_name,
                "outcome_row_version": None if outcome is None else outcome.row_version,
                "outcome_edit_readiness": outcome_edit_readiness,
                "inspected_on": None if outcome is None else outcome.inspected_on,
                "inspected_to_on": None if outcome is None else outcome.inspected_to_on,
                "inspection_period_state": None if outcome is None else outcome.inspection_period_state,
                "inspection_period_edit_readiness": {
                    "action_key": "edit_inspection_period",
                    "label": "Sửa các đợt kiểm tra",
                    "required_permissions": [inspection_permission],
                    **period_edit_readiness,
                },
                "inspection_period_segments": [
                    {"id": item.id, "ordinal": item.ordinal, "started_on": item.started_on, "ended_on": item.ended_on}
                    for item in period_segments
                ],
                "executed_on": next(
                    (
                        row.occurred_at
                        for row in reversed(events)
                        if row.event_type == InspectionEventType.INSPECTION_EXECUTED and row.occurred_at is not None
                    ),
                    None,
                ),
                "bbkt_reference": None if outcome is None else outcome.bbkt_reference,
                "outcome_result": None if outcome is None else outcome.outcome_result,
                "final_evaluation": None if outcome is None else outcome.final_evaluation,
                "minutes_recorded_on": None if outcome is None else outcome.minutes_recorded_on,
                "minutes_recorded_time": None if outcome is None else outcome.minutes_recorded_time,
                "compliance_due_on": None if outcome is None else outcome.compliance_due_on,
                "final_evaluation_readiness": final_evaluation_readiness,
                "approval_actions": approval_actions,
                "approval_document_evidence": approval_document_evidence,
                "approval_document_links": approval_document_links,
                "approval_document_candidates": approval_document_candidates,
                "approval_document_bind_readiness": approval_document_bind_readiness,
                "approval_submissions": [
                    {"approval_submission_id": item.id, "case_id": item.case_id, "stage": item.stage, "round_no": item.round_no,
                     "reference": item.reference, "submitted_on": item.submitted_on, "submitted_time": item.submitted_time,
                     "completed_on": item.completed_on, "completed_time": item.completed_time,
                     "pct_submission_id": item.pct_submission_id, "row_version": item.row_version}
                    for item in approval_submissions
                ],
                "team_display_text": None if team is None else team.display_text,
                "team": None if team is None else {
                    "team_id": team.id,
                    "row_version": team.row_version,
                    "display_text": team.display_text,
                    "members": serialized_team_members,
                    "round_trip_safe": team_round_trip_safe,
                    "blocked_reason_code": None if team_round_trip_safe else ("contains_legacy_person" if any(member.identity_kind == "LEGACY_PERSON" for member in team_members) else "unresolved_member_identity"),
                },
                "team_edit_readiness": {
                    "action_key": "edit_inspection_team",
                    "label": "Sửa đoàn kiểm tra",
                    "required_permissions": ["inspection.edit"],
                    **team_edit_readiness,
                },
            },
            "remediation": {
                "cycles": [
                    {
                        "capa_cycle_id": row.id,
                        "row_version": row.row_version,
                        "round_no": row.round_no,
                        "requested_on": row.requested_on,
                        "incoming_reference": row.incoming_reference,
                        "submitted_on": row.submitted_on,
                        "assessed_on": row.assessed_on,
                        "assessor_name": row.assessor_name,
                        "result": row.result,
                        "status": row.status,
                        "notes": row.notes,
                    }
                    for row in capa_cycles
                ],
                "actions": capa_actions,
            },
            "processing": {
                "row_version": None if assessment is None else assessment.row_version,
                "assessed_on": None if assessment is None else assessment.assessed_on,
                "assessor_name": None if assessment is None else assessment.assessor_name,
                "assessment_result": None if assessment is None else assessment.assessment_result,
                "notes": None if assessment is None else assessment.notes,
                "events": [
                    {
                        "event_type": row.event_type.value,
                        "occurred_at": row.occurred_at,
                        "payload": row.payload,
                    }
                    for row in events
                    if row.event_type
                    in {
                        InspectionEventType.APPLICATION_SUBMITTED,
                        InspectionEventType.ASSESSMENT_COMPLETED,
                        InspectionEventType.PLAN_CREATED,
                        InspectionEventType.DECISION_ISSUED,
                        InspectionEventType.INSPECTION_EXECUTED,
                        InspectionEventType.OUTCOME_RECORDED,
                        InspectionEventType.CERTIFICATE_ISSUED,
                    }
                ],
            },
            "evaluation_scope": self._serialize_evaluation_scope(session, case=case),
            "documents": case_document_checklist,
            "contextual_document_actions": self._build_case_contextual_document_actions(
                session,
                case_id=case.id,
                capa_cycles=capa_cycles,
                user=user,
            ),
            "nonissuance_decision": CaseWorkflowService().get_case_nonissuance_decision(
                session, case_id=case.id,
            ),
            "nonissuance_record_readiness": CaseWorkflowService().get_case_nonissuance_record_readiness(
                session, case_id=case.id, user=user,
            ),
            "certificate_issue_readiness": CaseWorkflowService().get_case_certificate_issue_readiness(
                session,
                case_id=case.id,
                user=user,
            ),
            "linked_gxp_certificates": linked_gxp_certificates,
            "linked_business_eligibility_certificates": linked_business_eligibility_certificates,
            "stage_edit_actions": stage_edit_actions,
            "business_evidence": case_business_evidence,
            "transition_actions": transition_actions,
        }

    def get_change_request_workspace(self, session: Session, *, change_request_id: str, user: AuthenticatedUser | None = None) -> dict[str, object]:
        # Re-read the canonical workspace owner, not an identity-map copy
        # that predates another Session's committed transition/edit.
        change_request = session.scalars(
            select(ChangeRequest).where(ChangeRequest.id == change_request_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
        if change_request is None:
            raise HTTPException(status_code=404, detail="Change request not found.")

        site = session.scalars(
            select(Site).where(Site.id == change_request.site_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
        if site is None:
            raise HTTPException(status_code=404, detail="Facility not found for change request.")
        company = session.scalars(
            select(Company).where(Company.id == site.company_id)
            .execution_options(populate_existing=True)
        ).one_or_none()
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found for change request.")

        approval = session.scalars(
            select(ChangeApproval)
            .where(ChangeApproval.change_request_id == change_request.id)
            .order_by(
                ChangeApproval.handled_on.is_(None),
                ChangeApproval.handled_on.desc(),
                ChangeApproval.created_at.desc(),
                ChangeApproval.id.desc(),
            )
            .execution_options(populate_existing=True)
        ).first()
        details = list(
            session.scalars(
                select(ChangeRequestDetail)
                .where(ChangeRequestDetail.change_request_id == change_request.id)
                .order_by(
                    ChangeRequestDetail.classification_label.is_(None),
                    ChangeRequestDetail.classification_label.asc(),
                    ChangeRequestDetail.legacy_change_detail_id.is_(None),
                    ChangeRequestDetail.legacy_change_detail_id.asc(),
                    ChangeRequestDetail.id.asc(),
                )
                .execution_options(populate_existing=True)
            )
        )

        affected_links = list(
            session.scalars(
                select(ChangeRequestAffectedArtifact)
                .where(ChangeRequestAffectedArtifact.change_request_id == change_request.id)
                .order_by(ChangeRequestAffectedArtifact.id.asc())
                .execution_options(populate_existing=True)
            )
        )
        issued_links = list(
            session.scalars(
                select(ChangeRequestIssuedArtifact)
                .where(ChangeRequestIssuedArtifact.change_request_id == change_request.id)
                .order_by(ChangeRequestIssuedArtifact.id.asc())
                .execution_options(populate_existing=True)
            )
        )
        workflow_service = CaseWorkflowService()
        for link in affected_links:
            workflow_service._validate_change_request_artifact_target(
                session,
                site=site,
                certificate_id=link.certificate_id,
                business_eligibility_certificate_id=link.business_eligibility_certificate_id,
            )
        affected_link_ids = {link.id for link in affected_links}
        for link in issued_links:
            workflow_service._validate_change_request_artifact_target(
                session,
                site=site,
                certificate_id=link.certificate_id,
                business_eligibility_certificate_id=link.business_eligibility_certificate_id,
            )
            if (
                link.source_affected_artifact_id is not None
                and link.source_affected_artifact_id not in affected_link_ids
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Change request issued artifact references an affected-artifact "
                        "link outside the owning change request."
                    ),
                )

        return {
            "id": change_request.id,
            "row_version": change_request.row_version,
            "legacy_change_request_id": change_request.legacy_change_request_id,
            "site_id": change_request.site_id,
            "facility_name": site.site_name,
            "company_name": company.legal_name,
            "scope_label": change_request.scope_label,
            "description": change_request.description,
            "submitted_on": change_request.submitted_on,
            "requester_name": change_request.requester_name,
            "state": change_request.state.value,
            "handled_on": None if approval is None else approval.handled_on,
            "handled_by_name": None if approval is None else approval.handled_by_name,
            "result_label": None if approval is None else approval.result_label,
            "effective_on": None if approval is None else approval.effective_on,
            "approval_reference": None if approval is None else approval.approval_reference,
            "documents": self._build_change_request_document_checklist(
                session,
                change_request_id=change_request.id,
            ),
            "details": [
                {
                    "change_detail_id": row.id,
                    "legacy_change_detail_id": row.legacy_change_detail_id,
                    "classification_id": row.classification_id,
                    "classification_label": row.classification_label,
                    "approval_status": row.approval_status,
                    "old_value": row.old_value,
                    "new_value": row.new_value,
                    "note": row.note,
                }
                for row in details
            ],
            "affected_artifacts": [
                workflow_service._serialize_change_request_artifact_link(link)
                for link in affected_links
            ],
            "issued_artifacts": [
                workflow_service._serialize_change_request_artifact_link(link)
                for link in issued_links
            ],
            "action_readiness": (
                []
                if user is None
                else CaseWorkflowService().get_change_request_action_readiness(
                    session,
                    change_request_id=change_request.id,
                    user=user,
                )
            ),
        }
