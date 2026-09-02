from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import and_, cast, func, or_, select, String, union_all
from sqlalchemy.orm import Session, aliased

from backend.app.auth import AuthenticatedUser
from backend.app.db.enums import CaseState, ChangeRequestState
from backend.app.document.contextual_actions import (
    build_case_contextual_document_specs,
    build_document_action_states,
    get_case_document_context_spec,
    list_case_document_labels,
)
from backend.app.rbac import ROLE_PERMISSIONS
from backend.app.document.service_contract import load_default_registry
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
    ChangeRequestDetail,
    Company,
    Document,
    DocumentVariant,
    DocumentVersion,
    InspectionEvent,
    InspectionPlan,
    InspectionOutcome,
    InspectionTeam,
    Site,
    EvaluationScopeTaxonomyNode,
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

        prose_only = scope.source_classification == "PROSE_ONLY"
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
            "limitation_text": scope.limitation_text,
            "editable": not terminal and not prose_only and not has_unkeyed_entries and scope.source_classification == "STRUCTURED_VALID",
            "read_only_reason": read_only_reason,
            "taxonomy_version_id": scope.taxonomy_version_id,
            "gxp_type": case.gxp_type,
            "blocks": [
                {
                    "id": block.id,
                    "ordinal": block.ordinal,
                    "name": block.name,
                    "note": block.note,
                    "selections": selections_by_block[block.id],
                    "unkeyed_entries": unkeyed_by_block[block.id],
                }
                for block in blocks
            ],
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
    @lru_cache(maxsize=1)
    def _document_registry_labels() -> dict[str, str]:
        labels: dict[str, str] = {}
        for entry in load_default_registry():
            labels.setdefault(entry.family_code, entry.logical_name)
        labels.update(CASE_DOCUMENT_FAMILY_LABELS)
        labels.update(CHANGE_REQUEST_DOCUMENT_FAMILY_LABELS)
        return labels

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
                "readiness": spec.readiness,
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
            contextual_items.append(
                {
                    **item,
                    "workflow_step": spec["workflow_step"],
                    "actions": build_document_action_states(
                        open_available=bool(item["open_available"]),
                        history_available=bool(item["detail_available"]),
                        readiness=spec["readiness"],
                        permissions=permissions,
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
            "limitation_text": None,
            "source_description": self._describe_certificate_source(
                certificate=certificate,
                linked_case=linked_case,
                inspected_on=inspected_on,
            ),
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
    ) -> dict[str, object]:
        return {
            "business_eligibility_certificate_id": certificate.id,
            "site_id": certificate.site_id,
            "company_id": certificate.company_id,
            "latest_flag": certificate.latest_flag,
            "certificate_number": version.certificate_number,
            "issued_on": version.issued_on,
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
        distinct_contexts = select(
            unioned_contexts.c.site_id,
            unioned_contexts.c.legacy_site_id,
            unioned_contexts.c.site_name,
            unioned_contexts.c.gxp_type,
            unioned_contexts.c.line_code,
        ).distinct()
        contexts = distinct_contexts.subquery("search_contexts_distinct")
        non_null_peer = contexts.alias("search_contexts_non_null_peer")
        suppressed_contexts_stmt = select(
            contexts.c.site_id,
            contexts.c.legacy_site_id,
            contexts.c.site_name,
            contexts.c.gxp_type,
            contexts.c.line_code,
        ).where(
            ~and_(
                contexts.c.line_code.is_(None),
                select(non_null_peer.c.site_id)
                .where(non_null_peer.c.site_id == contexts.c.site_id)
                .where(
                    or_(
                        non_null_peer.c.gxp_type == contexts.c.gxp_type,
                        and_(non_null_peer.c.gxp_type.is_(None), contexts.c.gxp_type.is_(None)),
                    )
                )
                .where(non_null_peer.c.line_code.is_not(None))
                .correlate(contexts)
                .exists(),
            )
        )
        contexts = suppressed_contexts_stmt.subquery("search_contexts_filtered")
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

    def list_site_gxp_certificates(self, session: Session, *, site_id: str, gxp_type: str | None, line_code: str | None):
        self.get_site(session, site_id)
        normalized_line_code = self._normalize_line_code(line_code)
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
            if normalized_line_code is not None and resolved_line_code not in {normalized_line_code, None}:
                continue
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
                    "line_code": resolved_line_code,
                    "context_match_kind": self._normalize_match_kind(normalized_line_code, resolved_line_code),
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
        return self._serialize_gxp_certificate_detail(
            certificate=certificate,
            version=version,
            linked_case=linked_case,
            site=site,
            company=company,
            scope_summary=context.scope_summary,
            inspected_on=inspected_on,
        )

    def list_site_business_eligibility_certificates(self, session: Session, *, site_id: str):
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
        return {"items": items}

    def get_business_eligibility_detail(self, session: Session, *, business_eligibility_certificate_id: str):
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
        linked_cases = {
            row.id: row
            for row in session.scalars(
                select(Case).where(Case.id.in_([certificate_row.case_id for _, certificate_row, _ in linked_rows if certificate_row.case_id]))
            )
        } if linked_rows else {}
        linked_gxp_certificates = [
            {
                "certificate_id": linked_certificate.id,
                "certificate_type": linked_certificate.certificate_type,
                "line_code": self._certificate_line_code(
                    linked_certificate,
                    None if linked_certificate.case_id is None else linked_cases.get(linked_certificate.case_id),
                ),
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

        return self._serialize_business_eligibility_detail(
            certificate=certificate,
            version=version,
            site=site,
            company=company,
            linked_gxp_certificates=linked_gxp_certificates,
            replacement_map=replacement_map,
        )

    def get_case_workspace(self, session: Session, *, case_id: str, user: AuthenticatedUser):
        case = self.get_case(session, case_id)
        site = self.get_site(session, case.site_id)
        company = self.get_company(session, site.company_id)

        application = session.scalar(select(CaseApplication).where(CaseApplication.case_id == case.id))
        assessment = session.scalar(select(CaseAssessment).where(CaseAssessment.case_id == case.id))
        plan = session.scalar(select(InspectionPlan).where(InspectionPlan.case_id == case.id))
        team = session.scalar(select(InspectionTeam).where(InspectionTeam.case_id == case.id))
        outcome = session.scalar(select(InspectionOutcome).where(InspectionOutcome.case_id == case.id))
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

        linked_gxp_certificates = [
            self._serialize_gxp_certificate_detail(
                certificate=certificate,
                version=version,
                linked_case=case,
                site=site,
                company=company,
                scope_summary=self._build_certificate_scope_summary(scope_rows_by_version_id.get(version.id, [])),
                inspected_on=inspected_on,
            )
            for certificate, version in gxp_certificate_rows
        ]
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

            linked_cases = (
                {
                    linked_case.id: linked_case
                    for linked_case in session.scalars(
                        select(Case).where(Case.id.in_([certificate_row.case_id for _, certificate_row, _ in linked_basis_rows if certificate_row.case_id]))
                    )
                }
                if linked_basis_rows
                else {}
            )

            linked_basis_by_version_id: dict[str, list[dict[str, object]]] = defaultdict(list)
            for link, linked_certificate, linked_version in linked_basis_rows:
                linked_basis_by_version_id[link.business_eligibility_version_id].append(
                    {
                        "certificate_id": linked_certificate.id,
                        "certificate_type": linked_certificate.certificate_type,
                        "line_code": self._certificate_line_code(
                            linked_certificate,
                            None if linked_certificate.case_id is None else linked_cases.get(linked_certificate.case_id),
                        ),
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
                "facility_name": site.site_name,
                "company_name": company.legal_name,
                "gxp_type": case.gxp_type,
                "scope_code": case.scope_code,
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
                "decision_reference": None if outcome is None else outcome.decision_reference,
                "decision_document_hint": None if plan is None else plan.decision_document_hint,
                "plan_start_on": None if plan is None else plan.plan_start_on,
                "plan_end_on": None if plan is None else plan.plan_end_on,
                "planning_sheet_name": None if plan is None else plan.planning_sheet_name,
                "outcome_row_version": None if outcome is None else outcome.row_version,
                "inspected_on": None if outcome is None else outcome.inspected_on,
                "inspected_to_on": None if outcome is None else outcome.inspected_to_on,
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
                "team_display_text": None if team is None else team.display_text,
            },
            "remediation": {
                "cycles": [
                    {
                        "capa_cycle_id": row.id,
                        "row_version": row.row_version,
                        "round_no": row.round_no,
                        "requested_on": row.requested_on,
                        "submitted_on": row.submitted_on,
                        "assessed_on": row.assessed_on,
                        "assessor_name": row.assessor_name,
                        "result": row.result,
                        "status": row.status,
                        "notes": row.notes,
                    }
                    for row in capa_cycles
                ]
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
            "linked_gxp_certificates": linked_gxp_certificates,
            "linked_business_eligibility_certificates": linked_business_eligibility_certificates,
        }

    def get_change_request_workspace(self, session: Session, *, change_request_id: str) -> dict[str, object]:
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

        return {
            "id": change_request.id,
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
        }
