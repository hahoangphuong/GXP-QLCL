from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_c5e_scalar_projection_contract_gate_is_ready_and_certificate_detail_stays_separate():
    proc = subprocess.run(
        [sys.executable, "tools/audit_c5e_evaluation_scope_document_projection.py"],
        cwd=ROOT,
        env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=SCALAR_PROJECTION_CONTRACT_READY" in proc.stdout
    assert "BLOCKERS=0" in proc.stdout
    payload = json.loads(
        (ROOT / "artifacts/legacy_audit/c5e_evaluation_scope_document_projection.json").read_text(encoding="utf-8")
    )
    assert payload["branch_contract_count"] == 9
    assert payload["branch_contract_mismatches"] == []
    assert payload["compact_summary_reuse_authorized"] is False
    assert payload["historical_prose_oracle_authorized"] is False
    assert payload["unkeyed_entries_semantic_input_authorized"] is False
    assert payload["deferred_separate_path"]["status"] == "NOT_IMPLEMENTED_IN_SCALAR_CONTRACT"
