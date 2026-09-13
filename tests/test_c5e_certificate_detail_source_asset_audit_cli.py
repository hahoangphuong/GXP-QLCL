from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_cli_bootstrap_imports_backend(tmp_path):
    proc = subprocess.run(
        [
            sys.executable,
            "tools/audit_c5e_certificate_detail_source_asset_registry.py",
            "--source-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    # Empty temp directory intentionally produces six missing-asset blockers.
    # The regression target is direct CLI import/bootstrap behavior.
    assert proc.returncode == 1
    assert "ModuleNotFoundError" not in proc.stderr
    assert "STATUS=SOURCE_ASSET_REGISTRY_BLOCKED" in proc.stdout
    assert "ASSETS=6" in proc.stdout
    assert "VERIFIED=0" in proc.stdout
    assert "BLOCKERS=6" in proc.stdout