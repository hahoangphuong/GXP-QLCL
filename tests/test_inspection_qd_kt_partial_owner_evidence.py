"""QĐKT owner evidence must never be promoted by physical bookmark parity."""
import json
from pathlib import Path

import pytest

from backend.app.document.inspection_qd_kt_partial_owner_evidence import (
    inspect_qdkt_partial_owner_evidence,
)

PROVENANCE = Path(__file__).resolve().parents[1] / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"


@pytest.mark.parametrize("gxp", ["GLP", "GMP", "GMPbb", "GSP"])
def test_all_six_partial_owners_remain_blocked_from_rendering(gxp):
    rows = {item.logical_name: item for item in inspect_qdkt_partial_owner_evidence(gxp)}
    assert set(rows) == {"Tencoso", "HsDK", "NgaynopHsDK", "TT3x", "TT3Del", "TTx"}
    assert rows["Tencoso"].target_names == ("Tencoso1", "Tencoso2", "Tencoso3")
    assert rows["Tencoso"].target_resolution_proven is True
    assert rows["TT3Del"].target_names == ("TT3Del",)
    assert rows["TT3x"].target_names == ("TT3x",)
    assert rows["TTx"].target_names == ("TT1x", "TT2x")
    for name in ("HsDK", "NgaynopHsDK"):
        assert rows[name].target_names == ()
        assert rows[name].target_resolution_proven is False
    for row in rows.values():
        assert row.owner_classification == "OWNER_PARTIAL"
        assert row.source_owner_verified is False
        assert row.ready_to_render is False
        assert row.source_semantic_endpoint
        assert row.blocker


def test_source_owner_promotions_are_refused(tmp_path):
    source = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    source["fields"]["HsDK"]["owner_classification"] = "OWNER_PROVEN"
    file = tmp_path / "modified.json"
    file.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="QDKT_PARTIAL_OWNER_PREMATURELY_PROMOTED"):
        inspect_qdkt_partial_owner_evidence("GMP", provenance_path=file)


def test_invalid_gxp_fails_closed():
    with pytest.raises(ValueError):
        inspect_qdkt_partial_owner_evidence("GMPNN")
