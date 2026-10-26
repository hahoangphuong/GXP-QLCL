"""Legacy provenance operation keys are not literal physical bookmark inventories."""
import json
from pathlib import Path

from backend.app.document.inspection_qd_kt_provenance_gate import (
    EXPECTED_FIELDS,
    inspect_qdkt_source_provenance,
)

ROOT = Path(__file__).resolve().parents[1]


def test_source_gate_keys_are_logical_operations_not_word_bookmark_names():
    observed = json.loads(
        (ROOT / "tests/fixtures/inspection_qd_kt_observed_template_binaries.json").read_text(encoding="utf-8")
    )
    assert len(EXPECTED_FIELDS) == 14
    assert {"Tencoso", "HsDK", "NgaynopHsDK"}.issubset(EXPECTED_FIELDS)
    for row in observed["templates"]:
        physical = set(row["bookmark_names"])
        assert "Tencoso" not in physical
        assert {"Tencoso1", "Tencoso2", "Tencoso3"}.issubset(physical)
        assert "HsDK" not in physical
        assert "NgaynopHsDK" not in physical
    decision = inspect_qdkt_source_provenance()
    assert len(decision.blocked_fields) == 8
    assert len(decision.partial_fields) == 6
    assert decision.proven_fields == ()
    assert decision.ready_for_typed_payload is False
