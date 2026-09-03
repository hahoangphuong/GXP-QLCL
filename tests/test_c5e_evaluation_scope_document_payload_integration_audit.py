from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "artifacts/legacy_audit/c5e_evaluation_scope_document_payload_integration.json"


def test_c5e_scalar_payload_integration_gate_is_ready_without_pythonpath_dependency():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "tools/audit_c5e_evaluation_scope_document_payload_integration.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "STATUS=SCALAR_PAYLOAD_INTEGRATION_READY" in proc.stdout
    assert "BLOCKERS=0" in proc.stdout
    report = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert report["blockers"] == []
    assert all(row["status"] == "PASS" for row in report["checks"].values())
    assert report["generic_registry_scope_semantic_owner"] is False
    assert report["caller_scope_override_authorized"] is False
    assert report["unkeyed_entries_semantic_input_authorized"] is False
    assert report["deferred_separate_path"]["name"] == "Input_DC_to_CC certificate detail"
