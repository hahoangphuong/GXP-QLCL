"""The dossier code and date share a legacy row but have distinct columns."""
import json
from pathlib import Path

import pytest

from backend.app.document.inspection_qd_kt_dossier_legacy_pair import (
    inspect_qdkt_dossier_legacy_pair,
)

SOURCE = Path(__file__).resolve().parents[1] / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"


def test_pair_is_same_row_with_different_columns_and_not_render_ready():
    row = inspect_qdkt_dossier_legacy_pair()
    assert row.same_legacy_row_proven is True
    assert (row.code_column_offset, row.date_column_offset) == (1, 0)
    assert row.code_expression == "s_MaHsDk"
    assert row.date_expression == 'Replace(s_NgaynopHsDk, "-", "/")'
    assert row.modern_owner_verified is False
    assert row.ready_to_render is False


@pytest.mark.parametrize(("which", "modify"), [
    ("HsDK", lambda x: x.update(source_semantic_endpoint="db.ktra row, ColDB_HSDK_Ktra")),
    ("NgaynopHsDK", lambda x: x.update(owner_classification="OWNER_PROVEN")),
    ("HsDK", lambda x: x["provenance_chain"][0]["steps"][0].update(code="Other variable")),
    ("NgaynopHsDK", lambda x: x["vba_rendered_operations"][0].update(expression="CDate(s_NgaynopHsDk)")),
])
def test_legacy_assignment_or_owner_drift_is_blocked(tmp_path, which, modify):
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    modify(data["fields"][which])
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="QDKT_DOSSIER"):
        inspect_qdkt_dossier_legacy_pair(provenance_path=path)


def test_source_sha_drift_is_blocked(tmp_path):
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    data["source_zip_sha256"] = "0" * 64
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="QDKT_DOSSIER_SOURCE_ZIP_DRIFT"):
        inspect_qdkt_dossier_legacy_pair(provenance_path=path)
