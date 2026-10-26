"""QĐKT cross-system identity must not be established by column-name similarity."""
import json
from pathlib import Path

import pytest

from backend.app.document.inspection_qd_kt_cross_system_identity_evidence import (
    inspect_qdkt_cross_system_identity,
)

SOURCE = Path(__file__).resolve().parents[1] / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
CANDIDATES = {
    "HsDK": "CaseApplication.dossier_code",
    "NgaynopHsDK": "CaseApplication.submitted_on",
    "Tencoso": "Site.site_name",
}


def test_candidate_labels_do_not_prove_record_identity_or_rendering():
    rows = inspect_qdkt_cross_system_identity(proposed_mapping=CANDIDATES)
    assert {row.logical_name for row in rows} == set(CANDIDATES)
    for row in rows:
        assert row.modern_candidate == CANDIDATES[row.logical_name]
        assert row.legacy_source
        assert row.legacy_row_identity_verified is False
        assert row.canonical_case_identity_verified is False
        assert row.record_selection_rule_verified is False
        assert row.value_semantics_verified is False
        assert row.modern_owner_verified is False
        assert row.ready_to_render is False


def test_even_different_proposed_owner_does_not_prove_parity():
    proposed = dict(CANDIDATES, HsDK="Unverified.external_column")
    rows = inspect_qdkt_cross_system_identity(proposed_mapping=proposed)
    assert all(not row.modern_owner_verified for row in rows)


@pytest.mark.parametrize("change", [
    {"HsDK": "OWNER_PROVEN"},
    {"NgaynopHsDK": "OWNER_PROVEN"},
    {"Tencoso": "OWNER_PROVEN"},
])
def test_source_owner_promotion_fails_closed(tmp_path, change):
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    for key, status in change.items():
        data["fields"][key]["owner_classification"] = status
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="QDKT_CROSS_SYSTEM_SOURCE_OR_OWNER_DRIFT"):
        inspect_qdkt_cross_system_identity(provenance_path=path)


def test_missing_mapping_or_blank_candidate_is_rejected():
    with pytest.raises(ValueError, match="QDKT_CROSS_SYSTEM_MAPPING_INCOMPLETE"):
        inspect_qdkt_cross_system_identity(proposed_mapping={"HsDK": "X"})
    with pytest.raises(ValueError, match="QDKT_CROSS_SYSTEM_MAPPING_INVALID"):
        inspect_qdkt_cross_system_identity(proposed_mapping=dict(CANDIDATES, HsDK=" "))
