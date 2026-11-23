"""Case-owned QĐKT decision-source timeline, for operator review only.

These rows are historical/persisted source assertions, not external legal
issuance evidence. Never use the timeline to render/issue a draft or to
infer AMENDS/SUPPLEMENTS, a missing reference or a latest decision by date.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from backend.app.db.models.phase1 import Case, InspectionDecision, InspectionPlan
from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionSourceBlocked,
    QdKtSourceDecision,
    require_latest_qdkt_reference,
)


def read_case_qdkt_decision_history(session, *, case_id: str) -> dict[str, object]:
    """Persisted scalar SELECTs preserve caller drafts; no Session mutation."""
    with session.no_autoflush:
        if type(case_id) is not str or not case_id.strip() or case_id != case_id.strip():
            raise HTTPException(status_code=404, detail="Case not found.")
        # Case is the only authorization-scoped owner. Never accept Plan ID
        # or decision ID from the caller to cross-link another Case.
        if session.scalar(select(Case.id).where(Case.id == case_id)) is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        plans = session.execute(
            select(InspectionPlan.id).where(InspectionPlan.case_id == case_id)
        ).scalars().all()
        if not plans:
            return {
                "case_id": case_id,
                "inspection_plan_id": None,
                "source_status": "NO_INSPECTION_PLAN",
                "blocked_reason": None,
                "latest_source_decision_id": None,
                "legal_issuance_verified": False,
                "ready_to_render": False,
                "decisions": [],
            }
        if len(plans) != 1:
            # Defensive against nonstandard imported schemas / damaged sources.
            return {
                "case_id": case_id,
                "inspection_plan_id": None,
                "source_status": "LINEAGE_BLOCKED",
                "blocked_reason": "CASE_INSPECTION_PLAN_NOT_UNIQUE",
                "latest_source_decision_id": None,
                "legal_issuance_verified": False,
                "ready_to_render": False,
                "decisions": [],
            }
        plan_id = plans[0]
        rows = session.execute(
            select(
                InspectionDecision.id,
                InspectionDecision.ordinal,
                InspectionDecision.reference,
                InspectionDecision.decision_on,
                InspectionDecision.legacy_raw,
                InspectionDecision.relation_type,
                InspectionDecision.related_decision_id,
            )
            .join(InspectionPlan, InspectionDecision.inspection_plan_id == InspectionPlan.id)
            .where(InspectionPlan.case_id == case_id, InspectionPlan.id == plan_id)
            .order_by(InspectionDecision.ordinal.asc(), InspectionDecision.id.asc())
        ).all()
        decisions = [QdKtSourceDecision(*row) for row in rows]
        status = "NO_DECISIONS"
        blocked_reason = None
        latest_id = None
        if decisions:
            try:
                latest_id = require_latest_qdkt_reference(decisions).source_decision_id
                status = "EXPLICIT_REPLACEMENT_CHAIN"
            except QdKtDecisionSourceBlocked as exc:
                status = "LINEAGE_BLOCKED"
                blocked_reason = str(exc)
        return {
            "case_id": case_id,
            "inspection_plan_id": plan_id,
            "source_status": status,
            "blocked_reason": blocked_reason,
            "latest_source_decision_id": latest_id,
            "legal_issuance_verified": False,
            "ready_to_render": False,
            "decisions": [
                {
                    "decision_id": row.id,
                    "ordinal": row.ordinal,
                    "reference": row.reference,
                    "decision_on": row.decision_on,
                    "legacy_raw": row.legacy_raw,
                    "relation_type": row.relation_type,
                    "related_decision_id": row.related_decision_id,
                }
                for row in decisions
            ],
        }
