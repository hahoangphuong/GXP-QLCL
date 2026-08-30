from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from tools import build_phase5_final_closeout as phase5


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8", newline="\n")
    return sha256(encoded.encode("utf-8")).hexdigest()


def _patch_phase5_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(phase5, "PHASE5_DIR", tmp_path)
    monkeypatch.setattr(phase5, "AUDIT_PATH", tmp_path / "template_compatibility_audit.json")
    monkeypatch.setattr(phase5, "RECON_PATH", tmp_path / "template_contract_reconciled.json")
    monkeypatch.setattr(phase5, "DDKD_VARIANTS_PATH", tmp_path / "dkkd_template_variants.json")
    monkeypatch.setattr(phase5, "BBTD_VARIANTS_PATH", tmp_path / "bbtd_template_variants.json")
    monkeypatch.setattr(phase5, "DDKD_APPENDIX_PATH", tmp_path / "ddkd_appendix_field_adjudication.json")
    monkeypatch.setattr(phase5, "JSON_OUT", tmp_path / "phase5_final_closeout.json")
    monkeypatch.setattr(phase5, "MD_OUT", tmp_path / "phase5_final_closeout.md")


def _write_valid_phase5_inputs(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "template_compatibility_audit.json",
        {
            "registry_family_count": 26,
            "matched_family_count": 26,
            "active_file_count": 91,
        },
    )
    _write_json(
        tmp_path / "template_contract_reconciled.json",
        {
            "families": [
                {"family_code": "DDKD_CERTIFICATE"},
                {"family_code": "INSPECTION_BBTD_HOSO_DK"},
                {"family_code": "DDKD_APPENDIX_OR_DECISION"},
                {"family_code": "INSPECTION_CAPA_LAN_1"},
                {"family_code": "INSPECTION_CAPA_LAN_2"},
            ]
        },
    )
    _write_json(
        tmp_path / "dkkd_template_variants.json",
        {
            "family_code": "DDKD_CERTIFICATE",
            "variants": [{"variant_key": "ddkd_certificate_new"}],
        },
    )
    _write_json(
        tmp_path / "bbtd_template_variants.json",
        {
            "family_code": "INSPECTION_BBTD_HOSO_DK",
            "variants": [{"variant_key": "bbtd_hoso_dk_all_lines"}],
        },
    )
    _write_json(
        tmp_path / "ddkd_appendix_field_adjudication.json",
        {
            "family_code": "DDKD_APPENDIX_OR_DECISION",
            "recommended_next_state": {
                "promotable_now": ["All"],
                "still_blocked": ["GCN_GMP", "QD_GMP"],
            },
        },
    )


def test_build_summary_records_authoritative_phase5_provenance(tmp_path: Path, monkeypatch) -> None:
    _patch_phase5_paths(monkeypatch, tmp_path)
    _write_valid_phase5_inputs(tmp_path)

    summary = phase5.build_summary()

    assert summary["phase5_status"] == "closed"
    assert summary["validation_errors"] == []
    assert summary["document_generation_baseline"]["registry_family_count"] == 26
    assert summary["document_generation_baseline"]["matched_family_count"] == 26
    assert summary["document_generation_baseline"]["active_template_file_count"] == 91
    assert summary["artifact_sources"]["template_compatibility_audit"]["path"] == tmp_path.joinpath(
        "template_compatibility_audit.json"
    ).as_posix()
    assert summary["artifact_sources"]["ddkd_template_variants"]["path"] == tmp_path.joinpath(
        "dkkd_template_variants.json"
    ).as_posix()


def test_build_summary_fails_closed_when_upstream_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase5_paths(monkeypatch, tmp_path)
    _write_valid_phase5_inputs(tmp_path)
    (tmp_path / "bbtd_template_variants.json").unlink()

    try:
        phase5.build_summary()
    except RuntimeError as exc:
        assert "bbtd_template_variants.json" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for missing authoritative Phase 5 artifact")


def test_repo_phase5_closeout_matches_current_authoritative_inputs() -> None:
    summary = phase5.build_summary()

    assert summary["phase5_status"] == "closed"
    assert summary["validation_errors"] == []
    assert summary["document_generation_baseline"]["registry_family_count"] == 26
    assert summary["document_generation_baseline"]["matched_family_count"] == 26
    assert summary["document_generation_baseline"]["active_template_file_count"] == 91
    assert summary["artifact_sources"]["ddkd_template_variants"]["path"] == "artifacts/phase5/dkkd_template_variants.json"
