from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_c5e_certificate_detail_gate_blocks_only_on_remaining_durable_evidence_gaps():
    proc = subprocess.run(
        [sys.executable, "tools/audit_c5e_certificate_detail_readiness.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=SOURCE_CONTRACT_IMPLEMENTED_LIVE_NOT_VERIFIED" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_readiness.json").read_text(encoding="utf-8")
    )
    codes = {item["code"] for item in report["blockers"]}
    assert "ACTIVE_INPUT_DC_TO_CC_BODY_NOT_DURABLY_CAPTURED" not in codes
    assert "CERTIFICATE_DETAIL_TEMPLATE_REGIONS_NOT_PROVEN" not in codes
    assert not codes
    assert "INPUT_DC_TO_CC_RENDER_CONTRACT_NOT_IMPLEMENTED" not in codes
    assert "SCALAR_DETAIL_BOUNDARY_VIOLATION" not in codes

    checks = {item["code"]: item for item in report["checks"]}
    assert all(item["pass"] is True for item in checks.values())
    assert checks["DURABLE_VBA_EVIDENCE"]["evidence"][
        "exact_active_Input_DC_to_CC_body_retained"
    ] is True
    assert checks["CERTIFICATE_DETAIL_TEMPLATE_CONTRACT"]["evidence"][
        "dedicated_captured_destinations"
    ] == ["GLP", "GMP"]
    assert checks["CERTIFICATE_DETAIL_TEMPLATE_CONTRACT"]["evidence"][
        "source_asset_registry_complete"
    ] is True
    assert report["schema_version"] == "c5e-certificate-detail-readiness/v3"
    for key in (
        "runtime_storage_source_assets_verified",
        "runtime_storage_destination_assets_verified",
        "authenticated_real_case_docx_render_verified",
        "gsp_destination_supported",
        "deployment_authorized",
    ):
        assert report[key] is False


def test_c5e_certificate_detail_gate_forbids_summary_scalar_and_unkeyed_substitution():
    from tools.audit_c5e_certificate_detail_readiness import audit

    report = audit()
    assert report["compact_summary_substitution_authorized"] is False
    assert report["scalar_projection_substitution_authorized"] is False
    assert report["historical_prose_oracle_authorized"] is False
    assert report["unkeyed_entries_semantic_input_authorized"] is False
    assert report["commented_Input_DC_to_CC2_as_active_oracle_authorized"] is False


def test_readiness_gate_fails_closed_if_captured_active_vba_is_missing(monkeypatch, tmp_path):
    from tools import audit_c5e_certificate_detail_readiness as owner

    monkeypatch.setattr(owner, "ACTIVE_VBA", tmp_path / "not-captured.bas")
    monkeypatch.setattr(owner, "OUTPUT", tmp_path / "readiness.json")
    report = owner.audit()
    assert report["status"] == "SOURCE_CONTRACT_EVIDENCE_INCOMPLETE"
    assert "ACTIVE_INPUT_DC_TO_CC_BODY_NOT_DURABLY_CAPTURED" in {
        item["code"] for item in report["blockers"]
    }
    assert report["deployment_authorized"] is False


def test_readiness_gate_fails_closed_if_dedicated_template_evidence_disappears(
    monkeypatch, tmp_path,
):
    from tools import audit_c5e_certificate_detail_readiness as owner

    monkeypatch.setattr(
        owner, "CAPTURED_DESTINATION_STRUCTURE_ROOT",
        tmp_path / "absent-destination-structures",
    )
    monkeypatch.setattr(owner, "OUTPUT", tmp_path / "readiness.json")
    report = owner.audit()
    assert report["status"] == "SOURCE_CONTRACT_EVIDENCE_INCOMPLETE"
    assert "CERTIFICATE_DETAIL_TEMPLATE_REGIONS_NOT_PROVEN" in {
        item["code"] for item in report["blockers"]
    }
    assert report["authenticated_real_case_docx_render_verified"] is False
