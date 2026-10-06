from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from backend.app.auth import AuthenticatedUser
from backend.app.domain.evaluation_scope_vba_renderer import compile_vba_readable_scope
from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.document.contextual_actions import (
    build_case_contextual_document_specs,
    build_document_action_states,
    get_case_document_context_spec,
    list_case_document_labels,
)
from backend.app.rbac import ROLE_PERMISSIONS
from backend.app.document.service_contract import load_default_registry
from backend.app.document.inspection_ke_hoach_kt_template_asset_contract import (
    INSPECTION_KE_HOACH_KT_FAMILY,
    get_inspection_ke_hoach_kt_output_filename,
)
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    BusinessEligibilityCertificateLink,
    BusinessEligibilityVersion,
    Case,
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
                row.is_current,
                row.issued_on or row.created_at,
                row.version_no,
                row.id,
            ),
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
                    "open_available": (
                        best_version is not None
                        and best_version.storage_root is not None
                        and best_version.storage_relative_path is not None
                    ),
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
                    "open_available": (
                        best_version is not None
                        and best_version.storage_root is not None
                        and best_version.storage_relative_path is not None
                    ),
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
        return {"items": self._serialize_document_checklist_items(session, definitions=definitions)}

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
                create_contract = {
                    "create_gxp_type": case.gxp_type,
                    "create_storage_scope": "inspection_folder",
                    "create_output_filename": get_inspection_ke_hoach_kt_output_filename(case.gxp_type),
                }
                if item["status"] == "available":
                    effective_create_readiness = "READY_OPEN_HISTORY"
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

        lines = {row.id: row for row in session.scalars(select(ProductionLine))}

        queue = []
        for case, site, company in queue_rows:
            line_id, line_code, identity_state = self._line_identity(
                site_id=case.site_id,
                production_line_id=case.production_line_id,
                raw_line_code=case.scope_code,
                lines=lines,
            )
            queue.append({
                "case_id": case.id,
                "site_id": site.id,
                "result_key": self._build_search_result_key(
                    site.id,
                    gxp_type=case.gxp_type,
                    identity_state=identity_state,
                    production_line_id=line_id,
                    line_code=line_code,
                ),
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "gxp_type": case.gxp_type,
                "state": case.state.value,
                "reference_code": case.legacy_inspection_code,
                "opened_year": case.opened_year,
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
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, object]:
        return self._search_facilities_by_production_line(
            session,
            q=q,
            facility_name=facility_name,
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
        self._assert_certificate_links_valid(session)
        sites = list(session.scalars(select(Site).order_by(Site.legacy_site_id, Site.id)))
        companies = {row.id: row for row in session.scalars(select(Company))}
        lines = {row.id: row for row in session.scalars(select(ProductionLine))}
        cases = list(session.scalars(select(Case)))
        outcomes_by_case_id = {row.case_id: row for row in session.scalars(select(InspectionOutcome))}
        inspection_event_dates_by_case_id = {
            case_id: occurred_at.date()
            for case_id, occurred_at in session.execute(
                select(InspectionEvent.case_id, func.max(InspectionEvent.occurred_at))
                .where(InspectionEvent.event_type == InspectionEventType.INSPECTION_EXECUTED)
                .group_by(InspectionEvent.case_id)
            )
            if occurred_at is not None
        }
        certificates = list(session.scalars(select(Certificate).where(Certificate.latest_flag.is_(True))))
        change_requests = list(session.scalars(select(ChangeRequest)))
        case_by_id = {row.id: row for row in cases}
        versions = {row.certificate_id: row for row in session.scalars(select(CertificateVersion).where(CertificateVersion.is_latest_version.is_(True)))}
        scopes: dict[str, list[CertificateScope]] = defaultdict(list)
        for scope in session.scalars(select(CertificateScope)):
            scopes[scope.certificate_version_id].append(scope)
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

        results: list[dict[str, object]] = []
        for site in sites:
            company = companies.get(site.company_id)
            if company is None:
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
        return {"items": results[offset : offset + limit], "total_count": len(results), "offset": offset, "limit": limit}

    def get_facility_workspace(self, session: Session, *, site_id: str, gxp_type: str | None, line_code: str | None, production_line_id: str | None = None):
        self._assert_certificate_links_valid(session, site_id=site_id)
        site = self.get_site(session, site_id)
        company = self.get_company(session, site.company_id)
        site_cases = list(session.scalars(select(Case).where(Case.site_id == site_id)))
        normalized_line_code = self._normalize_line_code(line_code)
        lines = {row.id: row for row in session.scalars(select(ProductionLine).where(ProductionLine.site_id == site_id))}
        selected_line_id, selected_line_code, identity_state = self._line_identity(
            site_id=site_id, production_line_id=production_line_id, raw_line_code=normalized_line_code, lines=lines
        )
        if production_line_id is not None and normalized_line_code is not None and selected_line_code != normalized_line_code:
            raise HTTPException(status_code=422, detail="line_code does not match the selected canonical ProductionLine.")
        scoped_cases = [row for row in site_cases if row.gxp_type == gxp_type] if gxp_type else site_cases
        if identity_state == "canonical":
            scoped_cases = [row for row in scoped_cases if row.production_line_id == selected_line_id]
        elif identity_state == "legacy_unlinked":
            scoped_cases = [row for row in scoped_cases if row.production_line_id is None and self._normalize_line_code(row.scope_code) == selected_line_code]
        else:
            scoped_cases = [row for row in scoped_cases if row.production_line_id is None and self._normalize_line_code(row.scope_code) is None]
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

    def list_site_gxp_certificates(self, session: Session, *, site_id: str, gxp_type: str | None, line_code: str | None, production_line_id: str | None = None):
        self._assert_certificate_links_valid(session, site_id=site_id)
        self.get_site(session, site_id)
        normalized_line_code = self._normalize_line_code(line_code)
        lines = {row.id: row for row in session.scalars(select(ProductionLine).where(ProductionLine.site_id == site_id))}
        selected_line_id, selected_line_code, identity_state = self._line_identity(site_id=site_id, production_line_id=production_line_id, raw_line_code=normalized_line_code, lines=lines)
        if production_line_id is not None and normalized_line_code is not None and normalized_line_code != selected_line_code:
            raise HTTPException(status_code=422, detail="line_code does not match the selected canonical ProductionLine.")
        cases = list(session.scalars(select(Case).where(Case.site_id == site_id)))
        case_by_id = {row.id: row for row in cases}
        case_ids = list(case_by_id)
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

        rows = list(
            session.execute(
                select(Certificate, CertificateVersion)
                .join(
                    CertificateVersion,
                    and_(
                        CertificateVersion.certificate_id == Certificate.id,
                        CertificateVersion.is_latest_version.is_(True),
                    ),
                )
                .where(
                    Certificate.site_id == site_id,
                    *( [Certificate.certificate_type == gxp_type] if gxp_type else [] ),
                )
            ).all()
        )
        items = []
        for certificate, version in rows:
            linked_case = None if certificate.case_id is None else case_by_id.get(certificate.case_id)
            resolved_line_code = self._certificate_line_code(certificate, linked_case)
            certificate_line_id, certificate_line_code, certificate_identity_state = self._line_identity(site_id=certificate.site_id, production_line_id=certificate.production_line_id, raw_line_code=resolved_line_code, lines=lines)
            if identity_state == "canonical" and not (
                certificate_line_id == selected_line_id
                or certificate_identity_state == "facility_wide"
            ):
                continue
            if identity_state == "legacy_unlinked" and not (
                certificate_identity_state == "facility_wide"
                or (
                    certificate_line_id is None
                    and certificate_identity_state == "legacy_unlinked"
                    and certificate_line_code == selected_line_code
                )
            ):
                continue
            if identity_state == "facility_wide" and certificate_identity_state != "facility_wide":
                continue
            display_line_code = certificate_line_code if certificate_identity_state == "canonical" else resolved_line_code
            context_match_kind = (
                "exact_line"
                if identity_state == "canonical" and certificate_line_id == selected_line_id
                else "facility_wide"
                if identity_state == "canonical" and certificate_identity_state == "facility_wide"
                else self._normalize_match_kind(normalized_line_code, display_line_code)
            )
            certificate_context = CertificateContextRow(
                certificate=certificate,
                version=version,
                line_code=resolved_line_code,
                scope_summary=None,
            )
            items.append(
                {
                    "certificate_id": certificate.id,
                    "site_id": certificate.site_id,
                    "case_id": certificate.case_id,
                    "certificate_type": certificate.certificate_type,
                    "line_code": display_line_code,
                    "production_line_id": certificate_line_id,
                    "production_line_code": certificate_line_code,
                    "production_line_identity_state": certificate_identity_state,
                    "context_match_kind": context_match_kind,
                    "latest_flag": certificate.latest_flag,
                    "certificate_number": version.certificate_number,
                    "issue_date": version.issue_date,
                    "expiry_date": version.expiry_date,
                    "applicable_standard": version.applicable_standard,
                    "issuing_authority": version.issuing_authority,
                    "status": self._derive_certificate_status(certificate_context),
                }
            )
        items.sort(
            key=lambda item: (
                0 if item["context_match_kind"] == "exact_line" else 1 if item["context_match_kind"] == "facility_wide" else 2,
                -(item["issue_date"].toordinal()) if item["issue_date"] is not None else float("inf"),
                -(item["expiry_date"].toordinal()) if item["expiry_date"] is not None else float("inf"),
                item["certificate_number"] or "",
                item["certificate_id"],
            )
        )
        return {"items": items}

    def get_gxp_certificate_detail(self, session: Session, *, certificate_id: str):
        certificate = session.get(Certificate, certificate_id)
        if certificate is None:
            raise HTTPException(status_code=404, detail="Certificate not found")
        CaseWorkflowService._validate_certificate_linked_case(session, certificate)
        site = self.get_site(session, certificate.site_id)
        company = self.get_company(session, site.company_id)
        version = session.scalar(
            select(CertificateVersion)
            .where(
                CertificateVersion.certificate_id == certificate.id,
                CertificateVersion.is_latest_version.is_(True),
            )
        )
        if version is None:
            raise HTTPException(status_code=404, detail="Certificate latest version not found")
        linked_case = None if certificate.case_id is None else session.get(Case, certificate.case_id)
        scope_rows = list(
            session.scalars(
                select(CertificateScope)
                .where(CertificateScope.certificate_version_id == version.id)
                .order_by(CertificateScope.sort_order.asc(), CertificateScope.created_at.asc(), CertificateScope.id.asc())
            )
        )
        inspected_on = None
        if linked_case is not None:
            outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == linked_case.id))
            if outcome is not None:
                inspected_on = outcome.inspected_to_on or outcome.inspected_on
            if inspected_on is None:
                latest_event = session.scalar(
                    select(func.max(InspectionEvent.occurred_at)).where(
                        InspectionEvent.case_id == linked_case.id,
                        InspectionEvent.event_type == InspectionEventType.INSPECTION_EXECUTED,
                    )
                )
                if latest_event is not None:
                    inspected_on = latest_event.date()
        context = CertificateContextRow(
            certificate=certificate,
            version=version,
            line_code=self._certificate_line_code(certificate, linked_case),
            scope_summary=self._build_certificate_scope_summary(scope_rows),
        )
        payload = self._serialize_gxp_certificate_detail(
            certificate=certificate,
            version=version,
            linked_case=linked_case,
            site=site,
            company=company,
            scope_summary=context.scope_summary,
            scope_rows=scope_rows,
            inspected_on=inspected_on,
        )
        lines = {row.id: row for row in session.scalars(select(ProductionLine).where(ProductionLine.site_id == site.id))}
        production_line_id, production_line_code, identity_state = self._line_identity(
            site_id=certificate.site_id, production_line_id=certificate.production_line_id,
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
            linked_gxp_certificates.append(payload)
        linked_gxp_certificates.sort(
            key=lambda item: (
                -(item["issue_date"].toordinal()) if item["issue_date"] is not None else float("inf"),
                item["certificate_number"] or "",
                item["certificate_id"],
            )
        )

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

            linked_business_eligibility_certificates = [
                self._serialize_business_eligibility_detail(
                    certificate=certificate_row,
                    version=version_row,
                    site=site,
                    company=company,
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
                "approval_submissions": [
                    {"approval_submission_id": item.id, "stage": item.stage, "round_no": item.round_no,
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
            "documents": self._build_case_document_checklist(session, case_id=case.id, capa_cycles=capa_cycles),
            "contextual_document_actions": self._build_case_contextual_document_actions(
                session,
                case_id=case.id,
                capa_cycles=capa_cycles,
                user=user,
            ),
            "certificate_issue_readiness": CaseWorkflowService().get_case_certificate_issue_readiness(
                session,
                case_id=case.id,
                user=user,
            ),
            "linked_gxp_certificates": linked_gxp_certificates,
            "linked_business_eligibility_certificates": linked_business_eligibility_certificates,
            "transition_actions": transition_actions,
        }

    def get_change_request_workspace(self, session: Session, *, change_request_id: str, user: AuthenticatedUser | None = None) -> dict[str, object]:
        change_request = session.get(ChangeRequest, change_request_id)
        if change_request is None:
            raise HTTPException(status_code=404, detail="Change request not found.")

        site = session.get(Site, change_request.site_id)
        if site is None:
            raise HTTPException(status_code=404, detail="Facility not found for change request.")
        company = session.get(Company, site.company_id)
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
            )
        )

        affected_links = list(
            session.scalars(
                select(ChangeRequestAffectedArtifact)
                .where(ChangeRequestAffectedArtifact.change_request_id == change_request.id)
                .order_by(ChangeRequestAffectedArtifact.id.asc())
            )
        )
        issued_links = list(
            session.scalars(
                select(ChangeRequestIssuedArtifact)
                .where(ChangeRequestIssuedArtifact.change_request_id == change_request.id)
                .order_by(ChangeRequestIssuedArtifact.id.asc())
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
