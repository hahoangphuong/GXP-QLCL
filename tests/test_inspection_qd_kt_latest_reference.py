"""Explicit QĐKT reference-selection lineage tests (related documents only)."""
from dataclasses import replace
from datetime import date

import pytest

from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionSourceBlocked,
    QdKtSourceDecision,
    require_latest_qdkt_reference,
)

D1 = QdKtSourceDecision(
    id="d1", ordinal=1, reference="01/QD", decision_on=date(2025, 2, 1),
    legacy_raw="01/QD 01/02/2025", relation_type=None, related_decision_id=None,
)
D2 = QdKtSourceDecision(
    id="d2", ordinal=2, reference="02/QD", decision_on=date(2025, 3, 1),
    legacy_raw="02/QD 01/03/2025", relation_type="REPLACES", related_decision_id="d1",
)
D3 = QdKtSourceDecision(
    id="d3", ordinal=3, reference="03/QD", decision_on=date(2025, 4, 1),
    legacy_raw="03/QD 01/04/2025", relation_type="REPLACES", related_decision_id="d2",
)


def test_single_original_is_latest_reference():
    assert require_latest_qdkt_reference([D1]).source_decision_id == "d1"


def test_explicit_replacement_chain_uses_latest_and_not_input_order():
    out = require_latest_qdkt_reference([D3, D1, D2])
    assert (out.source_decision_id, out.reference, out.decision_on) == (
        "d3", "03/QD", date(2025, 4, 1)
    )


@pytest.mark.parametrize("items", [
    [],
    [D1, D1],
    [replace(D1, ordinal=2)],
    [D1, replace(D2, ordinal=3)],
    [replace(D1, relation_type="REPLACES", related_decision_id="d2"), D2],
    [D1, replace(D2, related_decision_id="missing")],
    [D1, replace(D2, relation_type=None, related_decision_id=None)],
    [D1, replace(D2, decision_on=date(2025, 1, 1))],
    [D1, D2, replace(D3, related_decision_id="d1")],
    [D1, replace(D2, reference=" ")],
    [D1, replace(D2, legacy_raw="")],
    [D1, replace(D2, id="d1")],
])
def test_missing_or_ambiguous_replacement_history_blocks(items):
    with pytest.raises(QdKtDecisionSourceBlocked):
        require_latest_qdkt_reference(items)
