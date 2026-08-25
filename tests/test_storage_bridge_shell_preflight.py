from __future__ import annotations

from pathlib import Path
import os
import shlex
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _to_bash_path(path: Path) -> str:
    resolved = path.resolve()
    if resolved.as_posix().startswith("/"):
        return resolved.as_posix()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{tail}"


def _mock_bin_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    _write_executable(
        bin_dir / "gcloud",
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            import sys

            args = sys.argv[1:]
            active_account = os.environ.get("MOCK_ACTIVE_ACCOUNT", "operator@example.com")
            service_account = os.environ.get(
                "MOCK_SERVICE_ACCOUNT",
                "gxp-storage-bridge@gxp-qlcl.iam.gserviceaccount.com",
            )
            active_member = (
                f"serviceAccount:{active_account}"
                if active_account.endswith(".gserviceaccount.com")
                else f"user:{active_account}"
            )

            def emit_policy(mode: str, member: str, role: str) -> int:
                if mode == "query_fail":
                    sys.stderr.write("mock iam query failed\\n")
                    return 1
                if mode == "empty":
                    sys.stdout.write("")
                    return 0
                if mode == "malformed":
                    sys.stdout.write("{")
                    return 0
                bindings = []
                if mode == "present":
                    bindings.append({"role": role, "members": [member]})
                else:
                    bindings.append({"role": role, "members": ["user:someone-else@example.com"]})
                sys.stdout.write(json.dumps({"bindings": bindings}))
                return 0

            if args[:3] == ["config", "get-value", "account"]:
                sys.stdout.write(active_account + "\\n")
                raise SystemExit(0)
            if args[:3] == ["artifacts", "repositories", "describe"]:
                raise SystemExit(0)
            if args[:3] == ["iam", "service-accounts", "describe"]:
                raise SystemExit(0)
            if args[:2] == ["secrets", "describe"]:
                raise SystemExit(0)
            if args[:2] == ["secrets", "get-iam-policy"]:
                raise SystemExit(
                    emit_policy(
                        os.environ.get("MOCK_SECRET_POLICY_MODE", "present"),
                        f"serviceAccount:{service_account}",
                        "roles/secretmanager.secretAccessor",
                    )
                )
            if args[:3] == ["iam", "service-accounts", "get-iam-policy"]:
                raise SystemExit(
                    emit_policy(
                        os.environ.get("MOCK_TOKEN_POLICY_MODE", "present"),
                        active_member,
                        "roles/iam.serviceAccountTokenCreator",
                    )
                )
            if args[:2] == ["auth", "print-identity-token"]:
                sys.stdout.write("mock-token\\n")
                raise SystemExit(0)

            sys.stderr.write(f"unexpected gcloud args: {args!r}\\n")
            raise SystemExit(2)
            """
        ),
    )

    _write_executable(
        bin_dir / "curl",
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import hashlib
            import json
            import os
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            url = args[-1] if args else ""
            state_dir = Path(os.environ["MOCK_STATE_DIR"])
            state_dir.mkdir(parents=True, exist_ok=True)
            payload_path = state_dir / "smoke_payload.bin"

            if "/bridge/storage/write" in url:
                payload_path.write_bytes(sys.stdin.buffer.read())
                raise SystemExit(0)
            if "/bridge/storage/read" in url:
                if payload_path.exists():
                    sys.stdout.buffer.write(payload_path.read_bytes())
                raise SystemExit(0)
            if "/bridge/storage/checksum" in url:
                payload = payload_path.read_bytes() if payload_path.exists() else b""
                sys.stdout.write(json.dumps({"checksum_sha256": hashlib.sha256(payload).hexdigest()}))
                raise SystemExit(0)
            raise SystemExit(0)
            """
        ),
    )

    return bin_dir


def _shell_env(tmp_path: Path, bin_dir: Path, **extra: str) -> dict[str, str]:
    env = os.environ.copy()
    return env


def _bash_exports(values: dict[str, str]) -> str:
    statements: list[str] = []
    for key, value in values.items():
        if key == "PATH" and value.endswith(":$PATH"):
            prefix = value[: -len(":$PATH")]
            statements.append(f"export PATH={shlex.quote(prefix)}:\"$PATH\"")
        else:
            statements.append(f"export {key}={shlex.quote(value)}")
    return "; ".join(statements)


def _run_bootstrap(tmp_path: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    bin_dir = _mock_bin_dir(tmp_path)
    defaults = {
        "PATH": _to_bash_path(bin_dir) + ":$PATH",
        "DRY_RUN": "1",
        "MOCK_SECRET_POLICY_MODE": "present",
        "MOCK_TOKEN_POLICY_MODE": "present",
        "MOCK_STATE_DIR": _to_bash_path(tmp_path / "state"),
        "MOCK_ACTIVE_ACCOUNT": "operator@example.com",
        "MOCK_SERVICE_ACCOUNT": "gxp-storage-bridge@gxp-qlcl.iam.gserviceaccount.com",
    }
    defaults.update(extra_env)
    env = _shell_env(tmp_path, bin_dir, **defaults)
    return subprocess.run(
        ["bash", "-c", f"{_bash_exports(defaults)}; ./infra/cloudrun/bootstrap_storage_bridge.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_smoke(tmp_path: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    bin_dir = _mock_bin_dir(tmp_path)
    defaults = {
        "PATH": _to_bash_path(bin_dir) + ":$PATH",
        "BRIDGE_URL": "https://bridge.example",
        "TEST_INSPECTION_RELATIVE_PATH": "2026/TEST_STORAGE",
        "MOCK_TOKEN_POLICY_MODE": "present",
        "MOCK_STATE_DIR": _to_bash_path(tmp_path / "state"),
        "MOCK_ACTIVE_ACCOUNT": "operator@example.com",
        "MOCK_SERVICE_ACCOUNT": "gxp-storage-bridge@gxp-qlcl.iam.gserviceaccount.com",
    }
    defaults.update(extra_env)
    env = _shell_env(tmp_path, bin_dir, **defaults)
    return subprocess.run(
        ["bash", "-c", f"{_bash_exports(defaults)}; ./infra/cloudrun/smoke_test_storage_bridge.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_bootstrap_preflight_passes_when_secret_accessor_and_token_creator_are_present(tmp_path: Path):
    completed = _run_bootstrap(tmp_path)

    assert completed.returncode == 0
    assert "DRY RUN PASS" in completed.stdout
    assert "JSONDecodeError" not in completed.stderr


def test_bootstrap_preflight_reports_actionable_secret_accessor_missing(tmp_path: Path):
    completed = _run_bootstrap(tmp_path, MOCK_SECRET_POLICY_MODE="absent")

    assert completed.returncode == 1
    assert "missing Secret Manager access for 'gxp-tailscale-auth-key'" in completed.stderr
    assert "gcloud secrets add-iam-policy-binding gxp-tailscale-auth-key" in completed.stderr
    assert "JSONDecodeError" not in completed.stderr


def test_bootstrap_preflight_reports_iam_query_failure_for_secret_policy(tmp_path: Path):
    completed = _run_bootstrap(tmp_path, MOCK_SECRET_POLICY_MODE="query_fail")

    assert completed.returncode == 1
    assert "Failed to query IAM policy for secret 'gxp-tailscale-auth-key'." in completed.stderr
    assert "mock iam query failed" in completed.stderr
    assert "missing Secret Manager access" not in completed.stderr


def test_bootstrap_preflight_reports_actionable_token_creator_missing(tmp_path: Path):
    completed = _run_bootstrap(tmp_path, MOCK_TOKEN_POLICY_MODE="absent")

    assert completed.returncode == 1
    assert "cannot impersonate 'gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com'" in completed.stderr
    assert "roles/iam.serviceAccountTokenCreator" in completed.stderr
    assert "JSONDecodeError" not in completed.stderr


def test_bootstrap_preflight_reports_parse_error_for_empty_secret_policy_json(tmp_path: Path):
    completed = _run_bootstrap(tmp_path, MOCK_SECRET_POLICY_MODE="empty")

    assert completed.returncode == 1
    assert "Failed to parse IAM policy JSON for secret 'gxp-tailscale-auth-key'." in completed.stderr
    assert "JSONDecodeError" in completed.stderr
    assert "missing Secret Manager access" not in completed.stderr


def test_smoke_test_passes_when_token_creator_is_present(tmp_path: Path):
    completed = _run_smoke(tmp_path)

    assert completed.returncode == 0
    assert "Storage bridge smoke test passed." in completed.stdout
    assert "JSONDecodeError" not in completed.stderr


def test_smoke_test_reports_actionable_token_creator_missing(tmp_path: Path):
    completed = _run_smoke(tmp_path, MOCK_TOKEN_POLICY_MODE="absent")

    assert completed.returncode == 1
    assert "cannot impersonate 'gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com'" in completed.stderr
    assert "roles/iam.serviceAccountTokenCreator" in completed.stderr
    assert "JSONDecodeError" not in completed.stderr


def test_smoke_test_reports_parse_error_for_malformed_token_policy_json(tmp_path: Path):
    completed = _run_smoke(tmp_path, MOCK_TOKEN_POLICY_MODE="malformed")

    assert completed.returncode == 1
    assert "Failed to parse IAM policy JSON for service account 'gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com'." in completed.stderr
    assert "JSONDecodeError" in completed.stderr
    assert "cannot impersonate" not in completed.stderr