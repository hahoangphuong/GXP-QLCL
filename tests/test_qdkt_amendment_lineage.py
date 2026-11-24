"""Explicit Process B chronology never conflates AMENDS with REPLACES."""
from datetime import date
import pytest

from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtSourceDecision, QdKtDecisionSourceBlocked,
    require_ordered_qdkt_recording_predecessor, require_latest_qdkt_reference,
)


DAY = date(2026, 11, 24)


def row(key, ordinal, relation=None, prior=None, on=DAY):
    return QdKtSourceDecision(
        id=key, ordinal=ordinal, reference=f"QDKT-{key}",
        decision_on=on, legacy_raw=f"verbatim {key}",
        relation_type=relation, related_decision_id=prior,
    )


def test_amendment_is_ordered_but_not_an_effective_replacement_source():
    initial = row("A", 1)
    amendment = row("B", 2, "AMENDS", "A")
    replacement = row("C", 3, "REPLACES", "B")
    assert require_ordered_qdkt_recording_predecessor([]) is None
    assert require_ordered_qdkt_recording_predecessor([initial]) == initial
    assert require_ordered_qdkt_recording_predecessor([replacement, initial, amendment]) == replacement
    with pytest.raises(QdKtDecisionSourceBlocked, match="DECISION_REPLACEMENT_LINEAGE_AMBIGUOUS"):
        require_latest_qdkt_reference([initial, amendment, replacement])


@pytest.mark.parametrize("rows", [
    [row("A", 1), row("B", 2, "AMENDS", "UNRELATED")],
    [row("A", 1), row("B", 3, "AMENDS", "A")],
    [row("A", 1, "AMENDS", "B")],
    [row("A", 1), row("B", 2, "REPLACES", "A"),
     row("C", 3, "AMENDS", "A")],
    [row("A", 1, on=date(2026, 11, 24)),
     row("B", 2, "AMENDS", "A", date(2026, 11, 23))],
])
def test_invalid_amendment_or_replacement_chronology_is_blocked(rows):
    with pytest.raises(QdKtDecisionSourceBlocked):
        require_ordered_qdkt_recording_predecessor(rows)
