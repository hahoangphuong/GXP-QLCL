from __future__ import annotations

"""C.5e DB-backed evaluation-scope input and scalar payload enrichment.

The generic Phase 5 payload registry remains an inventory for non-scope fields.
Evaluation-scope bookmark values are owned by the branch-aware C.5e projection
and are appended after generic registry validation. Legacy ``unkeyed_entries``
are never queried or passed into any C.5e projection boundary.

The canonical scope loader in this module is shared by:
- scalar document-scope projection; and
- certificate-detail ``Input_DC_to_CC`` semantic projection.

This keeps canonical DB access in one owner and prevents duplicate query logic.
"""

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import (
    Case,
    CaseEvaluationScope,
    CaseEvaluationScopeBlock,
    CaseEvaluationScopeSelection,
    EvaluationScopeTaxonomyNode,
)
from backend.app.domain.evaluation_scope_document_projection import (
    DOCUMENT_SCOPE_BRANCHES,
    project_vba_document_scope_fields,
)
from backend.app.document.payload_builders import (
    DocumentPayloadBuildError,
    PayloadBuildResult,
)
from backend.app.document.service_contract import DocumentPayloadField


C5E_SCOPE_FIELD_NAMES = frozenset(
    {
        "Daychuyen",
        "DayChuyen",
        "Daychuyen2",
        "GhPviDG",
        "GhPviCN",
        "GioiHanPvi",
        "GioihanPvi",
    }
)
C5E_SCOPE_FAMILIES = frozenset(DOCUMENT_SCOPE_BRANCHES)
C5E_SCOPE_PROJECTION_SOURCE = "C5e.project_vba_document_scope_fields"


@dataclass(frozen=True)
class C5EEvaluationScopeProjectionInput:
    blocks: tuple[dict[str, Any], ...]
    taxonomy_nodes: tuple[dict[str, Any], ...]
    limitation_text: str | None
    gxp_type: str


def _family_emits_scalar_scope_fields(family_code: str, *, copy_pt: bool) -> bool:
    if family_code in {"INSPECTION_QD_KT", "CERTIFICATE_DECISION"}:
        return False
    if family_code == "INSPECTION_PT_CT" and copy_pt:
        return False
    return family_code in C5E_SCOPE_FAMILIES


def assert_no_c5e_scope_field_override(*, family_code: str, values: dict[str, str]) -> None:
    if family_code not in C5E_SCOPE_FAMILIES:
        return
    overridden = sorted(set(values) & C5E_SCOPE_FIELD_NAMES)
    if overridden:
        raise DocumentPayloadBuildError(
            "C.5e evaluation-scope document fields are generated from canonical scope and cannot be supplied "
            f"by the caller for family_code={family_code!r}: {', '.join(overridden)}"
        )


def load_c5e_evaluation_scope_projection_input(
    session: Session,
    *,
    case_id: str,
) -> C5EEvaluationScopeProjectionInput:
    """Load the canonical structured scope used by all C.5e projections.

    The loader deliberately reads only the case, canonical structured scope,
    exact-version taxonomy nodes, ordered blocks, and ordered keyed selections.
    Historical ``unkeyed_entries`` remain outside this boundary by design.
    """

    case = session.get(Case, case_id)
    if case is None:
        raise DocumentPayloadBuildError(f"C.5e evaluation-scope projection case was not found: {case_id}")

    scope = session.scalar(select(CaseEvaluationScope).where(CaseEvaluationScope.case_id == case.id))
    if scope is None:
        raise DocumentPayloadBuildError(
            f"C.5e document scope projection requires canonical evaluation scope for case_id={case.id}."
        )
    if scope.source_classification != "STRUCTURED_VALID" or scope.taxonomy_version_id is None:
        raise DocumentPayloadBuildError(
            "C.5e document scope projection requires STRUCTURED_VALID canonical scope with a persisted taxonomy version."
        )

    taxonomy_rows = list(
        session.scalars(
            select(EvaluationScopeTaxonomyNode)
            .where(
                EvaluationScopeTaxonomyNode.taxonomy_version_id == scope.taxonomy_version_id,
                EvaluationScopeTaxonomyNode.gxp_type == case.gxp_type,
            )
            .order_by(EvaluationScopeTaxonomyNode.source_order.asc(), EvaluationScopeTaxonomyNode.id.asc())
        )
    )
    if not taxonomy_rows:
        raise DocumentPayloadBuildError(
            f"C.5e document scope projection found no taxonomy nodes for case GxP family {case.gxp_type!r}."
        )

    node_key_by_id = {row.id: row.node_key for row in taxonomy_rows}
    taxonomy_nodes = tuple(
        {
            "id": row.id,
            "key": row.node_key,
            "parent_id": row.parent_node_id,
            "description": row.description,
            "hint": row.hint,
            "main_topic": row.main_topic,
            "short_render": row.short_render,
            "no_expand": row.no_expand,
            "source_order": row.source_order,
        }
        for row in taxonomy_rows
    )

    blocks = list(
        session.scalars(
            select(CaseEvaluationScopeBlock)
            .where(CaseEvaluationScopeBlock.case_evaluation_scope_id == scope.id)
            .order_by(CaseEvaluationScopeBlock.ordinal.asc(), CaseEvaluationScopeBlock.id.asc())
        )
    )
    block_ids = [row.id for row in blocks]
    selections_by_block: dict[str, list[dict[str, Any]]] = {row.id: [] for row in blocks}
    if block_ids:
        for selection in session.scalars(
            select(CaseEvaluationScopeSelection)
            .where(CaseEvaluationScopeSelection.block_id.in_(block_ids))
            .order_by(CaseEvaluationScopeSelection.block_id.asc(), CaseEvaluationScopeSelection.source_order.asc())
        ):
            node_key = node_key_by_id.get(selection.taxonomy_node_id)
            if node_key is None:
                raise DocumentPayloadBuildError(
                    "C.5e document scope projection found a selection outside the case taxonomy version/GxP family: "
                    f"taxonomy_node_id={selection.taxonomy_node_id}."
                )
            selections_by_block[selection.block_id].append(
                {
                    "taxonomy_node_id": selection.taxonomy_node_id,
                    "key": node_key,
                    "custom_description": selection.custom_description,
                    "source_order": selection.source_order,
                }
            )

    projection_blocks = tuple(
        {
            "id": block.id,
            "ordinal": block.ordinal,
            "name": block.name,
            "note": block.note,
            "selections": tuple(selections_by_block[block.id]),
        }
        for block in blocks
    )

    return C5EEvaluationScopeProjectionInput(
        blocks=projection_blocks,
        taxonomy_nodes=taxonomy_nodes,
        limitation_text=scope.limitation_text,
        gxp_type=case.gxp_type,
    )


def _load_projection_input(
    session: Session,
    *,
    case_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None, str]:
    """Backward-compatible private adapter for existing scalar callers/tests."""

    projection_input = load_c5e_evaluation_scope_projection_input(
        session,
        case_id=case_id,
    )
    return (
        list(projection_input.blocks),
        list(projection_input.taxonomy_nodes),
        projection_input.limitation_text,
        projection_input.gxp_type,
    )


def enrich_payload_result_with_c5e_scope(
    session: Session,
    *,
    family_code: str,
    case_id: str | None,
    copy_pt: bool,
    payload_result: PayloadBuildResult,
) -> PayloadBuildResult:
    """Append branch-owned scope fields without mutating the generic registry.

    Scope-like registry fields are removed from ``missing_registry_fields`` for
    C.5e families because the generic inventory is explicitly not their semantic
    owner. Families/branches with no active scalar scope writes do not require
    a canonical scope row.
    """
    if family_code not in C5E_SCOPE_FAMILIES:
        return payload_result

    missing = tuple(
        field_name
        for field_name in payload_result.missing_registry_fields
        if field_name not in C5E_SCOPE_FIELD_NAMES
    )

    if not _family_emits_scalar_scope_fields(family_code, copy_pt=copy_pt):
        return replace(payload_result, missing_registry_fields=missing)

    if case_id is None:
        raise DocumentPayloadBuildError(
            f"C.5e document scope projection requires case_id for family_code={family_code!r}."
        )

    projection_input = load_c5e_evaluation_scope_projection_input(
        session,
        case_id=case_id,
    )
    try:
        projection = project_vba_document_scope_fields(
            family_code=family_code,
            blocks=projection_input.blocks,
            taxonomy_nodes=projection_input.taxonomy_nodes,
            limitation_text=projection_input.limitation_text,
            gxp_type=projection_input.gxp_type,
            copy_pt=copy_pt,
        )
    except (AssertionError, ValueError) as exc:
        raise DocumentPayloadBuildError(str(exc)) from exc

    generated_fields = tuple(
        DocumentPayloadField(
            field_name=field_name,
            value=value,
            source=f"{C5E_SCOPE_PROJECTION_SOURCE}:{projection.vba_branch}",
            is_sensitive=False,
        )
        for field_name, value in projection.fields.items()
    )
    generated_names = tuple(field.field_name for field in generated_fields)
    envelope = replace(
        payload_result.envelope,
        fields=payload_result.envelope.fields + generated_fields,
    )
    return PayloadBuildResult(
        envelope=envelope,
        used_fields=tuple(sorted(set(payload_result.used_fields) | set(generated_names))),
        missing_registry_fields=missing,
        unexpected_input_fields=payload_result.unexpected_input_fields,
    )
