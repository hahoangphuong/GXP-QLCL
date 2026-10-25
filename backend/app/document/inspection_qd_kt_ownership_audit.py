"""Read-only assessment of persisted QĐKT decision/team/document ownership.

Do not mistake Case-scoped inspection teams or Case documents for a
decision-specific approved roster or an immutable draft snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy import func, select

from backend.app.db.models.phase1 import (
    Case, InspectionPlan, InspectionDecision, InspectionTeam,
    Document, DocumentVariant, DocumentVersion,
)


@dataclass(frozen=True)
class CaseQdKtOwnershipAudit:
    case_id: str
    inspection_plan_id: str | None
    decision_ids: tuple[str, ...]
    current_case_team_id: str | None
    case_qdkt_document_ids: tuple[str, ...]
    case_qdkt_document_version_count: int
    decision_team_links_proven: bool
    draft_snapshot_links_proven: bool
    blockers: tuple[str, ...]


def inspect_case_qdkt_ownership(session, *, case_id: str) -> CaseQdKtOwnershipAudit:
    """Read only canonical identifiers and counts, no personal roster content.

    The present ORM has one InspectionTeam per Case and decisions per plan.
    DocumentVersion belongs to DocumentVariant, not InspectionDecision.
    Consequently even existence of QĐKT versions cannot prove which draft
    or approved roster belongs to a particular decision.
    """
    if not isinstance(case_id, str) or not case_id.strip() or case_id != case_id.strip():
        raise ValueError("CASE_ID_INVALID")
    with session.no_autoflush:
        if session.get(Case, case_id) is None:
            raise ValueError("CASE_NOT_FOUND")
        plans = session.scalars(
            select(InspectionPlan).where(InspectionPlan.case_id == case_id)
        ).all()
        teams = session.scalars(
            select(InspectionTeam).where(InspectionTeam.case_id == case_id)
        ).all()
        if len(plans) > 1 or len(teams) > 1:
            raise ValueError("CASE_OWNER_NOT_UNIQUE")
        plan_id = plans[0].id if plans else None
        decisions = (session.scalars(
            select(InspectionDecision)
            .where(InspectionDecision.inspection_plan_id == plan_id)
            .order_by(InspectionDecision.ordinal, InspectionDecision.id)
        ).all() if plan_id else [])
        documents = session.scalars(
            select(Document).where(
                Document.case_id == case_id,
                Document.family_code == "INSPECTION_QD_KT",
            ).order_by(Document.id)
        ).all()
        document_ids = tuple(row.id for row in documents)
        versions = (session.scalar(
            select(func.count(DocumentVersion.id))
            .select_from(DocumentVersion)
            .join(DocumentVariant, DocumentVersion.document_variant_id == DocumentVariant.id)
            .where(DocumentVariant.document_id.in_(document_ids))
        ) if document_ids else 0)
    blockers = (
        "DECISION_SPECIFIC_TEAM_LINK_NOT_MODELED",
        "DRAFT_TEAM_SNAPSHOT_PERSISTENCE_NOT_MODELED",
        "DOCUMENT_VERSION_DECISION_LINK_NOT_MODELED",
    )
    return CaseQdKtOwnershipAudit(
        case_id=case_id,
        inspection_plan_id=plan_id,
        decision_ids=tuple(row.id for row in decisions),
        current_case_team_id=teams[0].id if teams else None,
        case_qdkt_document_ids=document_ids,
        case_qdkt_document_version_count=int(versions or 0),
        decision_team_links_proven=False,
        draft_snapshot_links_proven=False,
        blockers=blockers,
    )
