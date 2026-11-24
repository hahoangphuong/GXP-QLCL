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
        # A single statement gives one PostgreSQL MVCC snapshot even under
        # READ COMMITTED. Separate Case/Plan/Decision SELECTs could mix states
        # across a concurrent plan creation or decision append.
        rows = session.execute(
            select(
                Case.id,
                InspectionPlan.id,
                InspectionDecision.id,
                InspectionDecision.ordinal,
                InspectionDecision.reference,
                InspectionDecision.decision_on,
                InspectionDecision.legacy_raw,
                InspectionDecision.relation_type,
                InspectionDecision.related_decision_id,
            )
            .outerjoin(InspectionPlan, InspectionPlan.case_id == Case.id)
            .outerjoin(
                InspectionDecision,
                InspectionDecision.inspection_plan_id == InspectionPlan.id,
            )
            .where(Case.id == case_id)
            .order_by(InspectionDecision.ordinal.asc(), InspectionDecision.id.asc())
        ).all()
        if not rows:
            raise HTTPException(status_code=404, detail="Case not found.")
        plans = {row[1] for row in rows if row[1] is not None}
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
        plan_id = next(iter(plans))
        decisions = [QdKtSourceDecision(*row[2:]) for row in rows if row[2] is not None]
        status = "NO_DECISIONS"
        blocked_reason = None
        latest_id = None
        if decisions:
            try:
                latest_id = require_latest_qdkt_reference(decisions).source_decision_id
                status = "EXPLICIT_REPLACEMENT_CHAIN"
            except QdKtDecisionSourceBlocked as exc:
                # Explicit AMENDS is valid chronology, but is not a
                # replacement chain and supplies no single effective
                # source for a downstream renderer/related form.
                try:
                    from backend.app.document.inspection_qd_kt_decision_source import (
                        require_ordered_qdkt_recording_predecessor,
                    )
                    require_ordered_qdkt_recording_predecessor(decisions)
                    if any(item.relation_type == "AMENDS" for item in decisions):
                        status = "EXPLICIT_AMENDMENT_CHAIN_REQUIRES_REVIEW"
                        blocked_reason = "AMENDMENT_HAS_NO_SINGLE_EFFECTIVE_SOURCE"
                    else:
                        status = "LINEAGE_BLOCKED"
                        blocked_reason = str(exc)
                except QdKtDecisionSourceBlocked:
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
