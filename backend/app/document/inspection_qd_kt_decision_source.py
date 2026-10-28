"""Conservative, read-only selection of QĐKT source decision atoms.

This is not a rendering or approval API. A unique-source projection gate and
an explicit REPLACES-chain reference gate are distinct. Neither proves external
legal issuance or supplies a reference/date to a Process A draft.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
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
    # Populated only by the persisted reader; a pure chain has no Case proof.
    case_id: str | None = None
    inspection_plan_id: str | None = None

    @property
    def legal_issuance_verified(self) -> bool:
        return False


def _checked_items(decisions):
    try:
        items = tuple(decisions)
    except TypeError as exc:
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_INCOMPLETE") from exc
    for item in items:
        # Validate before sorting, hashing, stripping or comparing. Python bool
        # and float ordinals otherwise compare equal to integer positions.
        if type(item) is not QdKtSourceDecision or any(
            type(value) is not str or not value.strip()
            for value in (item.id, item.reference, item.legacy_raw)
        ):
            raise QdKtDecisionSourceBlocked("SOURCE_DECISION_INCOMPLETE")
        if (item.id != item.id.strip() or item.reference != item.reference.strip()
            or type(item.ordinal) is not int or item.ordinal < 1
            or type(item.decision_on) is not date
            or type(item.relation_type) not in (str, type(None))
            or type(item.related_decision_id) not in (str, type(None))):
            raise QdKtDecisionSourceBlocked("SOURCE_DECISION_INCOMPLETE")
    return items


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
    items = _checked_items(decisions)
    if len(items) != 1:
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_CARDINALITY_UNPROVEN")
    item = items[0]
    if (
        not item.id
        or item.ordinal != 1
        or not item.reference
        or item.reference != item.reference.strip()
        or type(item.decision_on) is not date
        or not item.legacy_raw
        or not item.legacy_raw.strip()
    ):
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_INCOMPLETE")
    if item.relation_type is not None or item.related_decision_id is not None:
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_LINEAGE_UNRESOLVED")
    if (type(plan_decision_reference) is not str or type(plan_decision_date) is not date
        or type(plan_decision_legacy_raw) is not str or
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
    from sqlalchemy import inspect, select
    from backend.app.db.models.phase1 import InspectionPlan

    if type(plan) is not InspectionPlan:
        raise QdKtDecisionSourceBlocked("INSPECTION_PLAN_ID_MISSING")
    state = inspect(plan)
    if not state.persistent or state.session is not session or not state.identity:
        raise QdKtDecisionSourceBlocked("INSPECTION_PLAN_ID_MISSING")
    if any(state.attrs[name].history.has_changes() for name in ("id", "case_id")):
        raise QdKtDecisionSourceBlocked("INSPECTION_PLAN_IDENTITY_PENDING")
    if any(state.attrs[name].history.has_changes() for name in ("decision_reference", "decision_date", "decision_legacy_raw")):
        raise QdKtDecisionSourceBlocked("DECISION_PROJECTION_MISMATCH")
    with session.no_autoflush:
        owner = session.execute(select(InspectionPlan.case_id).where(InspectionPlan.id == state.identity[0])).scalar_one_or_none()
        if owner is None:
            raise QdKtDecisionSourceBlocked("INSPECTION_PLAN_ID_MISSING")
        snapshot = _read_case_plan(session, owner)
        if snapshot[1] != state.identity[0]:
            raise QdKtDecisionSourceBlocked("CASE_INSPECTION_PLAN_NOT_UNIQUE")
        return _unique_from_snapshot(session, snapshot)


def read_unique_qdkt_source_for_case(session, *, case_id: str) -> QdKtDecisionAtoms:
    """Bind the read-only decision gate to one persisted Case identity.

    This is intentionally an internal owner boundary, not a write/render API.
    It cannot borrow another Case's InspectionPlan or fabricate a missing plan.
    """
    with session.no_autoflush:
        return _unique_from_snapshot(session, _read_case_plan(session, case_id))


def _read_case_plan(session, case_id):
    from sqlalchemy import select
    from backend.app.db.models.phase1 import Case, InspectionPlan
    if type(case_id) is not str or not case_id.strip() or case_id != case_id.strip():
        raise QdKtDecisionSourceBlocked("CASE_ID_MISSING")
    rows = session.execute(select(
        Case.id, InspectionPlan.id, InspectionPlan.case_id,
        InspectionPlan.decision_reference, InspectionPlan.decision_date, InspectionPlan.decision_legacy_raw,
    ).outerjoin(InspectionPlan, InspectionPlan.case_id == Case.id).where(Case.id == case_id)).all()
    if not rows:
        raise QdKtDecisionSourceBlocked("CASE_NOT_FOUND")
    if len(rows) != 1 or rows[0][1] is None:
        raise QdKtDecisionSourceBlocked("CASE_INSPECTION_PLAN_NOT_UNIQUE")
    if rows[0][0] != case_id or rows[0][2] != case_id:
        raise QdKtDecisionSourceBlocked("QDKT_DECISION_CASE_OWNERSHIP_MISMATCH")
    return rows[0]


def _read_decisions(session, plan_id, case_id):
    from sqlalchemy import select
    from backend.app.db.models.phase1 import Case, InspectionPlan, InspectionDecision as D
    rows = session.execute(select(D.id, D.ordinal, D.reference, D.decision_on, D.legacy_raw,
        D.relation_type, D.related_decision_id)
        .join(InspectionPlan, D.inspection_plan_id == InspectionPlan.id)
        .join(Case, InspectionPlan.case_id == Case.id)
        .where(D.inspection_plan_id == plan_id, Case.id == case_id)).all()
    return tuple(QdKtSourceDecision(*row) for row in rows)


def _unique_from_snapshot(session, snapshot):
    atoms = require_unique_qdkt_source(_read_decisions(session, snapshot[1], snapshot[0]),
        plan_decision_reference=snapshot[3], plan_decision_date=snapshot[4], plan_decision_legacy_raw=snapshot[5])
    return replace(atoms, case_id=snapshot[0], inspection_plan_id=snapshot[1])


def require_latest_qdkt_reference(
    decisions: Iterable[QdKtSourceDecision],
) -> QdKtDecisionAtoms:
    """Resolve the newest explicit REPLACES chain for related-form references.

    A single root decision is allowed. A successor must explicitly reference
    the preceding decision; ambiguous, branched or incomplete histories fail
    closed. This does NOT change the draft QĐKT template or populate its date.
    """
    items = _checked_items(decisions)
    if not items:
        raise QdKtDecisionSourceBlocked("SOURCE_DECISION_CARDINALITY_UNPROVEN")
    by_id = {item.id: item for item in items}
    if len(by_id) != len(items) or any(not item.id for item in items):
        raise QdKtDecisionSourceBlocked("DECISION_IDENTITY_AMBIGUOUS")
    ordinals = [item.ordinal for item in items]
    if sorted(ordinals) != list(range(1, len(items) + 1)):
        raise QdKtDecisionSourceBlocked("DECISION_ORDER_UNPROVEN")
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
    with session.no_autoflush:
        snapshot = _read_case_plan(session, case_id)
        atoms = require_latest_qdkt_reference(_read_decisions(session, snapshot[1], snapshot[0]))
    return replace(atoms, case_id=snapshot[0], inspection_plan_id=snapshot[1])
