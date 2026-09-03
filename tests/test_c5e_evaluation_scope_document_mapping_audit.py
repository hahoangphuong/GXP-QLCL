from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_c5e_mapping_audit_fails_closed_before_production_integration():
    proc = subprocess.run([sys.executable, "tools/audit_c5e_evaluation_scope_document_mapping.py"], cwd=ROOT, capture_output=True, text=True, check=True)
    assert "STATUS=BLOCKED_FOR_PRODUCTION_DOCUMENT_SCOPE_MAPPING" in proc.stdout
    payload = json.loads((ROOT / "artifacts/legacy_audit/c5e_evaluation_scope_document_mapping.json").read_text(encoding="utf-8"))
    codes = {row["code"] for row in payload["blockers"]}
    assert "BRANCH_FLATTENING_FALSE_POSITIVES" in codes
    assert "COMMENTED_VBA_COUNTED_AS_ACTIVE" in codes
    assert "CERTIFICATE_DETAIL_PATH_NOT_COMPACT_SUMMARY" in codes
    assert payload["compact_summary_reuse_authorized"] is False


def test_c5e_source_derived_branch_contracts_are_not_collapsed():
    from tools.audit_c5e_evaluation_scope_document_mapping import EXPECTED
    assert EXPECTED["INSPECTION_QD_KT"]["active"] == {}
    assert set(EXPECTED["INSPECTION_KE_HOACH_KT"]["active"]) == {"Daychuyen", "GioiHanPvi"}
    assert set(EXPECTED["INSPECTION_BB_KT"]["active"]) == {"Daychuyen", "GhPviDG", "GhPviCN"}
    assert EXPECTED["CERTIFICATE_DECISION"]["active"] == {}
    assert "Daychuyen" in EXPECTED["CERTIFICATE_DECISION"]["commented_only"]
