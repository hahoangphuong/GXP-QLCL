"""Four uploaded DOTX observations are evidence, not template-to-VBA parity."""
import json
from pathlib import Path

from backend.app.document.inspection_qd_kt_template_asset_contract import (
    load_inspection_qd_kt_template_assets,
)
from backend.app.document.inspection_qd_kt_provenance_gate import EXPECTED_FIELDS


OBSERVATIONS = (
    Path(__file__).resolve().parents[1]
    / "artifacts/legacy_audit/inspection_qd_kt_observed_template_binaries.json"
)


def test_uploaded_template_observations_match_pinned_manifest_identifiers():
    source = json.loads(OBSERVATIONS.read_text(encoding="utf-8"))
    assert source["schema_version"] == "inspection-qd-kt-observed-dotx-binaries/v1"
    assets = {asset.gxp_type: asset for asset in load_inspection_qd_kt_template_assets()}
    rows = source["templates"]
    assert {row["gxp_type"] for row in rows} == set(assets)
    assert len(rows) == 4
    expected_counts = {"GLP": 22, "GMP": 22, "GMPbb": 14, "GSP": 11}
    for row in rows:
        asset = assets[row["gxp_type"]]
        assert row["sha256"] == asset.checksum_sha256
        assert row["checksum_matches_manifest"] is True
        assert row["dotx_main_part_verified"] is True
        assert row["bookmark_count"] == expected_counts[row["gxp_type"]]
        assert len(row["bookmark_names"]) == len(set(row["bookmark_names"]))
        assert len(row["bookmark_names"]) == row["bookmark_count"]
        assert row["exact_trace_symbol_matches"] == [
            name for name in source["active_i2_trace_symbols"]
            if name in row["bookmark_names"]
        ]
        assert row["exact_trace_symbol_absences"] == [
            name for name in source["active_i2_trace_symbols"]
            if name not in row["bookmark_names"]
        ]
        assert row["bookmark_owner_parity_verified"] is False
        assert row["ready_to_render"] is False
    assert set(source["active_i2_trace_symbols"]) == EXPECTED_FIELDS
    assert source["ready_to_render"] is False


def test_exact_name_differences_do_not_silently_promote_mapping():
    rows = {
        row["gxp_type"]: row
        for row in json.loads(OBSERVATIONS.read_text(encoding="utf-8"))["templates"]
    }
    for kind in ("GLP", "GMP", "GMPbb", "GSP"):
        names = set(rows[kind]["bookmark_names"])
        assert {"TT1x", "TT2x", "TT3x", "TT3Del"} <= names
        assert "Tencoso" not in names
        assert {"Tencoso1", "Tencoso2", "Tencoso3"} <= names
        assert "TTx" not in names
        assert rows[kind]["bookmark_owner_parity_verified"] is False
    assert "VKN" not in rows["GSP"]["bookmark_names"]
    assert "VKNx" not in rows["GSP"]["bookmark_names"]
