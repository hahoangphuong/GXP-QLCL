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


def read_unique_qdkt_source_for_case(session, *, case_id: str) -> QdKtDecisionAtoms:
    """Bind the read-only decision gate to one persisted Case identity.

    This is intentionally an internal owner boundary, not a write/render API.
    It cannot borrow another Case's InspectionPlan or fabricate a missing plan.
    """
    from sqlalchemy import select
    from backend.app.db.models.phase1 import Case, InspectionPlan

    if not isinstance(case_id, str) or not case_id.strip():
        raise QdKtDecisionSourceBlocked("CASE_ID_MISSING")
    with session.no_autoflush:
        case = session.get(Case, case_id)
        if case is None:
            raise QdKtDecisionSourceBlocked("CASE_NOT_FOUND")
        plans = session.scalars(
            select(InspectionPlan)
            .where(InspectionPlan.case_id == case.id)
        ).all()
        if len(plans) != 1:
            raise QdKtDecisionSourceBlocked("CASE_INSPECTION_PLAN_NOT_UNIQUE")
        return read_unique_qdkt_source_for_plan(session, plans[0])


def require_latest_qdkt_reference(
    decisions: Iterable[QdKtSourceDecision],
) -> QdKtDecisionAtoms:
    """Resolve the newest explicit REPLACES chain for related-form references.

    A single root decision is allowed. A successor must explicitly reference
    the preceding decision; ambiguous, branched or incomplete histories fail
    closed. This does NOT change the draft QĐKT template or populate its date.
    """
    items = tuple(decisions)
    if not items:
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_CARDINALITY_UNPROVEN")
    by_id = {item.id: item for item in items}
    if len(by_id) != len(items) or any(not item.id for item in items):
        raise QdKtDecisionSourceBlocked("DECISION_IDENTITY_AMBIGUOUS")
    ordinals = [item.ordinal for item in items]
    if sorted(ordinals) != list(range(1, len(items) + 1)):
        raise QdKtDecisionSourceBlocked("DECISION_ORDER_UNPROVEN")
    for item in items:
        if (
            not item.reference or item.reference != item.reference.strip()
            or not isinstance(item.decision_on, date)
            or isinstance(item.decision_on, datetime)
            or not item.legacy_raw or not item.legacy_raw.strip()
        ):
            raise QdKtDecisionSourceBlocked("SOURCE_DECISION_INCOMPLETE")
    ordered = sorted(items, key=lambda item: item.ordinal)
    root = ordered[0]
    if root.relation_type is not None or root.related_decision_id is not None:
        raise QdKtDecisionSourceBlocked("DECISION_ROOT_INVALID")
    for prior, current in zip(ordered, ordered[1:]):
        if (
            current.relation_type != "REPLACES"
            or current.related_decision_id != prior.id
            or current.decision_on < prior.decision_on
        ):
            raise QdKtDecisionSourceBlocked("DECISION_REPLACEMENT_LINEAGE_AMBIGUOUS")
    latest = ordered[-1]
    return QdKtDecisionAtoms(
        source_decision_id=latest.id,
        reference=latest.reference,
        decision_on=latest.decision_on,
        legacy_raw=latest.legacy_raw,
    )


def read_latest_qdkt_reference_for_case(session, *, case_id: str) -> QdKtDecisionAtoms:
    """Read an explicit decision-replacement chain owned by one Case.

    Only the ordered source collection is authoritative for this selection.
    The plan's scalar projection is not substituted for a missing row.
    """
    from sqlalchemy import select
    from backend.app.db.models.phase1 import Case, InspectionPlan, InspectionDecision

    if not isinstance(case_id, str) or not case_id.strip():
        raise QdKtDecisionSourceBlocked("CASE_ID_MISSING")
    with session.no_autoflush:
        if session.get(Case, case_id) is None:
            raise QdKtDecisionSourceBlocked("CASE_NOT_FOUND")
        plans = session.scalars(
            select(InspectionPlan).where(InspectionPlan.case_id == case_id)
        ).all()
        if len(plans) != 1:
            raise QdKtDecisionSourceBlocked("CASE_INSPECTION_PLAN_NOT_UNIQUE")
        rows = session.scalars(
            select(InspectionDecision)
            .where(InspectionDecision.inspection_plan_id == plans[0].id)
            .order_by(InspectionDecision.ordinal, InspectionDecision.id)
        ).all()
    return require_latest_qdkt_reference(
        QdKtSourceDecision(
            id=row.id, ordinal=row.ordinal, reference=row.reference,
            decision_on=row.decision_on, legacy_raw=row.legacy_raw,
            relation_type=row.relation_type,
            related_decision_id=row.related_decision_id,
        )
        for row in rows
    )
