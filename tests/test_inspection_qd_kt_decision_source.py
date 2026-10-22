"""Offline QĐKT source selection; never render or write a document."""
from dataclasses import replace
from datetime import date, datetime

import pytest

from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionSourceBlocked,
    QdKtSourceDecision,
    require_unique_qdkt_source,
)

DAY = date(2026, 10, 20)
SOURCE = QdKtSourceDecision(
    id="decision-1", ordinal=1, reference="42/QĐ-KT",
    decision_on=DAY, legacy_raw="42/QĐ-KT 20/10/2026",
    relation_type=None, related_decision_id=None,
)


def select(decisions=(SOURCE,), **override):
    values = {
        "plan_decision_reference": SOURCE.reference,
        "plan_decision_date": SOURCE.decision_on,
        "plan_decision_legacy_raw": SOURCE.legacy_raw,
    }
    values.update(override)
    return require_unique_qdkt_source(decisions, **values)


def test_one_source_matching_scalar_projection_is_only_admitted_case():
    atoms = select()
    assert (atoms.source_decision_id, atoms.reference, atoms.decision_on, atoms.legacy_raw) == (
        SOURCE.id, SOURCE.reference, DAY, SOURCE.legacy_raw
    )


@pytest.mark.parametrize("decisions", [
    (),
    (SOURCE, replace(SOURCE, id="decision-2", ordinal=2)),
    (replace(SOURCE, id="",),),
    (replace(SOURCE, ordinal=2),),
    (replace(SOURCE, reference=" 42/QĐ-KT"),),
    (replace(SOURCE, reference=""),),
    (replace(SOURCE, legacy_raw=" "),),
    (replace(SOURCE, decision_on=datetime(2026, 10, 20, 0, 0)),),
    (replace(SOURCE, relation_type="REPLACES", related_decision_id="earlier"),),
    (replace(SOURCE, related_decision_id="earlier"),),
])
def test_incomplete_ambiguous_or_replacement_source_fails_closed(decisions):
    with pytest.raises(QdKtDecisionSourceBlocked):
        select(decisions)


@pytest.mark.parametrize("override", [
    {"plan_decision_reference": None},
    {"plan_decision_reference": "43/QĐ-KT"},
    {"plan_decision_date": None},
    {"plan_decision_date": date(2026, 10, 21)},
    {"plan_decision_legacy_raw": None},
    {"plan_decision_legacy_raw": "changed source"},
])
def test_missing_or_stale_scalar_projection_never_silently_falls_back(override):
    with pytest.raises(QdKtDecisionSourceBlocked, match="DECISION_PROJECTION_MISMATCH"):
        select(**override)
