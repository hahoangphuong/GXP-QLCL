from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_c5e_certificate_detail_gate_blocks_without_exact_active_vba_and_template_evidence():
    proc = subprocess.run(
        [sys.executable, "tools/audit_c5e_certificate_detail_readiness.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=BLOCKED_PENDING_EXACT_VBA_AND_TEMPLATE_EVIDENCE" in proc.stdout
    report = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_certificate_detail_readiness.json").read_text(encoding="utf-8")
    )
    codes = {item["code"] for item in report["blockers"]}
    assert "ACTIVE_INPUT_DC_TO_CC_BODY_NOT_DURABLY_CAPTURED" in codes
    assert "CERTIFICATE_DETAIL_TEMPLATE_REGIONS_NOT_PROVEN" in codes
    assert "INPUT_DC_TO_CC_RENDER_CONTRACT_NOT_IMPLEMENTED" in codes


def test_c5e_certificate_detail_gate_forbids_summary_scalar_and_unkeyed_substitution():
    from tools.audit_c5e_certificate_detail_readiness import audit

    report = audit()
    assert report["compact_summary_substitution_authorized"] is False
    assert report["scalar_projection_substitution_authorized"] is False
    assert report["historical_prose_oracle_authorized"] is False
    assert report["unkeyed_entries_semantic_input_authorized"] is False
    assert report["commented_Input_DC_to_CC2_as_active_oracle_authorized"] is False
