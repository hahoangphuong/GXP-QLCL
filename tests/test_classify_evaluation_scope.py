from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.app.domain.evaluation_scope import build_taxonomy_artifact, parse_legacy_evaluation_scope
from tools import classify_evaluation_scope


def _taxonomy() -> dict[str, object]:
    return build_taxonomy_artifact(
        workbook_name="fixture.xlsb",
        workbook_sha256="a" * 64,
        ranges={
            "PVCN_GMP": {"sheet_name": "Phạm vi CN", "start_row": 4, "values": [["1", "GMP root"], ["1.1", "GMP leaf"]]},
            "PVCN_GLP": {"sheet_name": "Phạm vi CN", "start_row": 124, "values": [["1", "GLP root"]]},
            "PVCN_GSP": {"sheet_name": "Phạm vi CN", "start_row": 370, "values": [["1", "GSP root"]]},
        },
    )


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    snapshot_path = tmp_path / "snapshot.json"
    taxonomy_path = tmp_path / "taxonomy.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "db.ktra": [
                    {"ID": "1", "Mã hồ sơ": "HS-1", "LOẠI KT": "GMP", "PHẠM VI KIỂM TRA": "Rendered\r\n(*Limit*)\r\n{Line A¶1: Custom¿Note§Line B¶1.1:}*"},
                    {"ID": "2", "LOẠI KT": "GMP", "PHẠM VI KIỂM TRA": "R{9: Unknown}*"},
                    {"ID": "3", "LOẠI KT": "GDP", "PHẠM VI KIỂM TRA": "R{1: Distribution}*"},
                    {"ID": "4", "LOẠI KT": "GLP", "PHẠM VI KIỂM TRA": "Historic prose only"},
                    {"ID": "5", "LOẠI KT": "GMP", "PHẠM VI KIỂM TRA": "R{1: truncated"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    taxonomy_path.write_text(json.dumps(_taxonomy(), ensure_ascii=False), encoding="utf-8")
    return snapshot_path, taxonomy_path


def test_cli_writes_deterministic_taxonomy_validated_report(monkeypatch, tmp_path: Path):
    snapshot_path, taxonomy_path = _write_inputs(tmp_path)
    output_path = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["classify_evaluation_scope.py", "--snapshot", str(snapshot_path), "--taxonomy", str(taxonomy_path), "--output", str(output_path)])

    assert classify_evaluation_scope.main() == 0
    first = output_path.read_bytes()
    assert classify_evaluation_scope.main() == 0
    assert output_path.read_bytes() == first
    report = json.loads(first.decode("utf-8"))
    assert report["taxonomy_validation_available"] is True
    assert report["counts"] == {"PROSE_ONLY": 1, "STRUCTURED_MALFORMED": 1, "STRUCTURED_PARTIAL": 1, "STRUCTURED_VALID": 2}
    assert report["selected_node_status_counts"] == {"KNOWN_NODE": 2, "TAXONOMY_UNAVAILABLE": 1, "UNKNOWN_NODE": 1}
    assert report["unknown_key_analysis"]["records"][0]["legacy_inspection_id"] == "2"
    assert report["unknown_key_analysis"]["records"][0]["raw_value"] == "R{9: Unknown}*"
    assert report["multi_scope_statistics"] == {"cases_with_limitation": 1, "cases_with_multiple_scope_blocks": 1, "named_scope_blocks": 2, "scope_notes": 1, "unkeyed_entries": 0}
    assert report["custom_description_counts"] == {"blank_custom_description": 1, "changed_custom_description": 1}
    assert report["importability_counts"] == {"CANONICALIZABLE": 1, "PARTIAL_REVIEW_REQUIRED": 1, "RAW_ONLY_MALFORMED": 1, "RAW_ONLY_PROSE": 1, "TAXONOMY_UNAVAILABLE": 1}
    assert report["taxonomy_statistics"]["GMP"]["source_row_count"] == 2


def test_cli_rejects_taxonomy_hash_mismatch_and_missing_taxonomy(tmp_path: Path):
    snapshot_path, taxonomy_path = _write_inputs(tmp_path)
    broken = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    broken["taxonomy_content_sha256"] = "0" * 64
    taxonomy_path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="semantic hash"):
        classify_evaluation_scope.build_report(snapshot_path, taxonomy_path)
    with pytest.raises(FileNotFoundError):
        classify_evaluation_scope.build_report(snapshot_path, tmp_path / "missing.json")


def test_runtime_synthetic_key_uses_only_vba_proven_shape():
    parsed = parse_legacy_evaluation_scope("R{1.1.1+: Runtime value}*", gxp_type="GMP", taxonomy=_taxonomy())
    assert parsed["classification"] == "STRUCTURED_VALID"
    assert parsed["scopes"][0]["selected_nodes"][0]["taxonomy_status"] == "RUNTIME_SYNTHETIC_NODE"
    assert parsed["scopes"][0]["selected_nodes"][0]["runtime_parent_key"] == "1.1"


def test_gmpbb_is_not_aliased_to_gmp_taxonomy():
    parsed = parse_legacy_evaluation_scope("R{1: GMPbb text}*", gxp_type="GMPbb", taxonomy=_taxonomy())
    assert parsed["classification"] == "STRUCTURED_VALID"
    assert parsed["taxonomy_validation"]["status"] == "unavailable"
    assert parsed["scopes"][0]["selected_nodes"][0]["taxonomy_status"] == "TAXONOMY_UNAVAILABLE"
