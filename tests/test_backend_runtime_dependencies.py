from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_runtime_manifests_declare_google_oidc_requests_transport_dependencies_explicitly() -> None:
    runtime_requirements = _read_lines(ROOT / "backend" / "requirements.runtime.txt")
    runtime_vm_requirements = _read_lines(ROOT / "backend" / "requirements.runtime.vm.txt")

    for requirements in (runtime_requirements, runtime_vm_requirements):
        assert "google-auth" in requirements
        assert "requests" in requirements


def test_runtime_lockfiles_pin_requests_for_backend_release_envs() -> None:
    for path in [
        ROOT / "backend" / "requirements.runtime.lock.txt",
        ROOT / "backend" / "requirements.runtime.vm.lock.txt",
        ROOT / "backend" / "requirements.dev.lock.txt",
    ]:
        text = path.read_text(encoding="utf-8")
        assert "requests==" in text
        assert "urllib3==" in text
        assert "certifi==" in text
        assert "charset-normalizer==" in text


def test_ci_verifies_vm_runtime_lock_freshness_and_auth_transport_installability() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Verify backend VM runtime lock freshness" in text
    assert "backend/requirements.runtime.vm.lock.ci.txt" in text
    assert "backend/requirements.runtime.vm.txt" in text
    assert "Verify backend VM runtime lock installs with auth transport imports" in text
    assert "python -m pip install --no-cache-dir -r backend/requirements.runtime.vm.lock.txt" in text
    assert "import requests" in text
    assert "from google.auth.transport.requests import Request as GoogleAuthRequest" in text
    assert "from google.oauth2 import id_token" in text
