"""Conservative, read-only selection of QĐKT source decision atoms.

This is not a rendering or approval API. It intentionally admits only one
unambiguous source decision whose structured scalar projection agrees with
the source record. Replacement chains and multiple decisions need an explicit
lifecycle rule before QĐKT can be rendered.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


class QdKtDecisionSourceBlocked(ValueError):
    """No unambiguous QĐKT source has been established."""


@dataclass(frozen=True)
class QdKtSourceDecision:
    id: str
    ordinal: int
    reference: str
    decision_on: date
    legacy_raw: str
    relation_type: str | None
    related_decision_id: str | None


@dataclass(frozen=True)
class QdKtDecisionAtoms:
    source_decision_id: str
    reference: str
    decision_on: date
    legacy_raw: str


def require_unique_qdkt_source(
    decisions: Iterable[QdKtSourceDecision],
    *,
    plan_decision_reference: str | None,
    plan_decision_date: date | None,
    plan_decision_legacy_raw: str | None,
) -> QdKtDecisionAtoms:
    """Return decision atoms only where exactly one ordered source is proven.

    This conservative gate does not infer which decision supersedes another.
    In particular it never trusts a scalar projection in the absence of its
    independently persisted InspectionDecision source record.
    """
    items = tuple(decisions)
    if len(items) != 1:
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_CARDINALITY_UNPROVEN")
    item = items[0]
    if (
        not item.id
        or item.ordinal != 1
        or not item.reference
        or item.reference != item.reference.strip()
        or not isinstance(item.decision_on, date)
        or isinstance(item.decision_on, datetime)
        or not item.legacy_raw
        or not item.legacy_raw.strip()
    ):
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_INCOMPLETE")
    if item.relation_type is not None or item.related_decision_id is not None:
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_LINEAGE_UNRESOLVED")
    if (
        plan_decision_reference != item.reference
        or plan_decision_date != item.decision_on
        or plan_decision_legacy_raw != item.legacy_raw
    ):
        raise QdKtDecisionSourceBlocked("DECISION_PROJECTION_MISMATCH")
    return QdKtDecisionAtoms(
        source_decision_id=item.id,
        reference=item.reference,
        decision_on=item.decision_on,
        legacy_raw=item.legacy_raw,
    )


def read_unique_qdkt_source_for_plan(session, plan) -> QdKtDecisionAtoms:
    """Read the existing source rows for one persisted InspectionPlan.

    The query is read-only and prevents a pending unrelated ORM change from
    being flushed implicitly by this preflight. Callers still need separate
    evidence gates for template, place, authority and inspector bookmarks.
    """
    from sqlalchemy import select
    from backend.app.db.models.phase1 import InspectionDecision

    if not getattr(plan, "id", None):
        raise QdKtDecisionSourceBlocked("INSPECTION_PLAN_ID_MISSING")
    with session.no_autoflush:
        source_rows = session.scalars(
            select(InspectionDecision)
            .where(InspectionDecision.inspection_plan_id == plan.id)
            .order_by(InspectionDecision.ordinal, InspectionDecision.id)
        ).all()
    return require_unique_qdkt_source(
        (
            QdKtSourceDecision(
                id=row.id,
                ordinal=row.ordinal,
                reference=row.reference,
                decision_on=row.decision_on,
                legacy_raw=row.legacy_raw,
                relation_type=row.relation_type,
                related_decision_id=row.related_decision_id,
            )
            for row in source_rows
        ),
        plan_decision_reference=plan.decision_reference,
        plan_decision_date=plan.decision_date,
        plan_decision_legacy_raw=plan.decision_legacy_raw,
    )
