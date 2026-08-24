from pathlib import Path
import subprocess
import sys

import yaml

from tools.env_utils import (
    dotenv_to_yaml_env_file,
    parse_env_file,
    parse_systemd_env_file,
    serialize_systemd_environment_file_contents,
    write_systemd_environment_file,
    write_yaml_env_file,
)
from tools.validate_prod_deploy import validate_prod_deploy_env


ROOT = Path(__file__).resolve().parents[1]


def test_storage_bridge_bootstrap_env_yaml_round_trips_with_unc_and_vietnamese(tmp_path: Path):
    source = ROOT / "backend" / ".env.storage_bridge.cloudrun.example"
    output = tmp_path / "bridge-bootstrap.yaml"

    generated = dotenv_to_yaml_env_file(
        source,
        output,
        exclude_keys=("STORAGE_BRIDGE_AUTH_AUDIENCE", "BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH"),
        overrides={"BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH": "1"},
        collapse_escaped_backslashes=True,
    )
    loaded = yaml.safe_load(output.read_text(encoding="utf-8"))

    assert loaded == generated
    assert loaded["STORAGE_INSPECTION_ROOT"] == r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs"
    assert loaded["STORAGE_DKKD_ROOT"] == r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Chứng nhận ĐĐKKDD"
    assert loaded["STORAGE_TEMPLATE_ROOT"] == r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Templates"
    assert loaded["BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH"] == "1"
    assert "STORAGE_BRIDGE_AUTH_AUDIENCE" not in loaded
    assert "TAILSCALE_AUTHKEY" not in loaded
    assert "SMB_USERNAME" not in loaded
    assert "SMB_PASSWORD" not in loaded


def test_storage_bridge_final_env_yaml_round_trips_with_exact_audience(tmp_path: Path):
    source = ROOT / "backend" / ".env.storage_bridge.cloudrun.example"
    output = tmp_path / "bridge-final.yaml"
    audience = "https://gxp-storage-bridge-abcde-uc.a.run.app"

    generated = dotenv_to_yaml_env_file(
        source,
        output,
        exclude_keys=("STORAGE_BRIDGE_AUTH_AUDIENCE", "BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH"),
        overrides={"STORAGE_BRIDGE_AUTH_AUDIENCE": audience},
        collapse_escaped_backslashes=True,
    )
    loaded = yaml.safe_load(output.read_text(encoding="utf-8"))

    assert loaded == generated
    assert "BRIDGE_BOOTSTRAP_ALLOW_UNCONFIGURED_AUTH" not in loaded
    assert loaded["STORAGE_BRIDGE_AUTH_AUDIENCE"] == audience
    assert loaded["STORAGE_INSPECTION_ROOT"] == r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs"


def test_prod_runtime_env_yaml_round_trips_without_secret_values(tmp_path: Path):
    report = validate_prod_deploy_env(
        {
            "PROJECT_ID": "gxp-qlcl",
            "REGION": "asia-southeast1",
            "SQL_INSTANCE": "gxp-db",
            "CLOUD_SQL_CONNECTION_NAME": "gxp-qlcl:asia-southeast1:gxp-db",
            "DB_PASSWORD_SECRET": "gxp-db-password",
            "DEPLOY_GIT_SHA": "abcdef1234567890",
            "DEPLOY_GIT_SHORT_SHA": "abcdef1",
            "DEPLOY_BRANCH": "main",
            "DRY_RUN": "1",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
            "AUTH_IAP_ALLOWED_EMAIL_DOMAIN": "example.com",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.example.internal",
            "STORAGE_BRIDGE_AUTH_AUDIENCE": "https://bridge.example.internal",
        }
    )
    assert report.plan is not None

    output = tmp_path / "runtime-env.yaml"
    write_yaml_env_file(output, report.plan.runtime_env)
    loaded = yaml.safe_load(output.read_text(encoding="utf-8"))

    assert loaded == report.plan.runtime_env
    assert "DB_PASSWORD" not in loaded
    assert loaded["STORAGE_BRIDGE_BASE_URL"] == "https://bridge.example.internal"


def test_parse_env_file_supports_quoted_values_for_runtime_env(tmp_path: Path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "PUBLIC_BASE_URL='https://gxp.example.com'\n"
        "STORAGE_INSPECTION_ROOT='\\\\\\\\100.95.45.127\\\\Hồ sơ nội bộ\\\\01 - Kiểm tra GPs'\n"
        "DB_PASSWORD='pa ss#word'\n",
        encoding="utf-8",
    )

    parsed = parse_env_file(env_file)

    assert parsed["PUBLIC_BASE_URL"] == "https://gxp.example.com"
    assert parsed["STORAGE_INSPECTION_ROOT"] == r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs"
    assert parsed["DB_PASSWORD"] == "pa ss#word"


def test_runtime_env_cli_exports_null_safe_pairs(tmp_path: Path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "PUBLIC_BASE_URL='https://gxp.example.com'\n"
        "DB_PASSWORD='pa ss#word'\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "tools/runtime_env.py", "export-null", str(env_file)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout.split(b"\0")[:-1] == [
        b"PUBLIC_BASE_URL=https://gxp.example.com",
        b"DB_PASSWORD=pa ss#word",
    ]


def test_systemd_runtime_env_round_trips_special_characters(tmp_path: Path):
    values = {
        "PLAIN": "plain",
        "WITH_SPACES": "  with spaces  ",
        "UNC_PATH": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
        "BACKSLASH": r"domain\user",
        "DOUBLE_QUOTE": 'he said "xin chao"',
        "SINGLE_QUOTE": "it's quoted",
        "DOLLAR": "$HOME and $PATH",
        "PERCENT": "%USERPROFILE%",
        "HASH": "abc#def",
        "SEMICOLON": "abc;def",
        "EQUALS": "a=b=c",
        "UNICODE_VI": "Hồ sơ nội bộ",
        "MIXED_PASSWORD": " weird ' \" $HOME \\\\ ; : spaces ",
        "EMPTY": "",
    }
    output = tmp_path / "runtime.systemd.env"

    write_systemd_environment_file(output, values)
    parsed = parse_systemd_env_file(output)

    assert parsed == values
    payload = output.read_text(encoding="utf-8")
    assert "MIXED_PASSWORD" in payload
    assert "Hồ sơ nội bộ" in payload


def test_runtime_env_cli_writes_systemd_safe_env_file(tmp_path: Path):
    source = tmp_path / "runtime.env"
    output = tmp_path / "runtime.systemd.env"
    expected_username = "domain\\user"
    expected_password = " weird ' \" $HOME \\\\ ; : spaces "
    source.write_text(
        f"SMB_USERNAME={expected_username!r}\n"
        f"SMB_PASSWORD={expected_password!r}\n"
        f"PUBLIC_BASE_URL={'https://gxp.example.com'!r}\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "tools/runtime_env.py", "write-systemd", str(source), str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert parse_systemd_env_file(output)["SMB_USERNAME"] == expected_username
    assert parse_systemd_env_file(output)["SMB_PASSWORD"] == expected_password
    assert parse_systemd_env_file(output)["PUBLIC_BASE_URL"] == "https://gxp.example.com"
    assert expected_password not in output.read_text(encoding="utf-8")


def test_systemd_runtime_env_serializer_is_deterministic():
    values = {"B": "two words", "A": "alpha"}
    first = serialize_systemd_environment_file_contents(values)
    second = serialize_systemd_environment_file_contents(values)

    assert first == second


def test_render_vm_runtime_assets_renders_nginx_with_only_nginx_env(tmp_path: Path):
    output = tmp_path / "gxp.conf"
    env = {
        "PUBLIC_BASE_URL": "https://gxp.example.com",
        "GXP_FRONTEND_DIST_ROOT": "/opt/gxp/frontend-dist",
        "VM_TLS_CERT_PATH": "/etc/ssl/certs/gxp.crt",
        "VM_TLS_KEY_PATH": "/etc/ssl/private/gxp.key",
        "APP_PORT": "8000",
    }

    completed = subprocess.run(
        [sys.executable, "tools/render_vm_runtime_assets.py", "nginx", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = output.read_text(encoding="utf-8")
    assert "server_name gxp.example.com;" in rendered
    assert "root /opt/gxp/frontend-dist;" in rendered
    assert "ssl_certificate /etc/ssl/certs/gxp.crt;" in rendered
    assert "ssl_certificate_key /etc/ssl/private/gxp.key;" in rendered
    assert "proxy_pass http://127.0.0.1:8000/api/;" in rendered
    assert "{{" not in rendered


def test_render_vm_runtime_assets_service_uses_explicit_systemd_env_file(tmp_path: Path):
    output = tmp_path / "gxp.service"
    env = {
        "VM_APP_USER": "gxp",
        "VM_APP_GROUP": "gxp",
        "VM_CURRENT_BACKEND_RELEASE_LINK": "/opt/gxp/current-backend",
        "VM_CURRENT_BACKEND_VENV_LINK": "/opt/gxp/current-venv",
        "VM_SYSTEMD_ENV_FILE": "/etc/gxp/runtime.systemd.env",
        "APP_PORT": "8000",
    }

    completed = subprocess.run(
        [sys.executable, "tools/render_vm_runtime_assets.py", "service", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = output.read_text(encoding="utf-8")
    assert "EnvironmentFile=/etc/gxp/runtime.systemd.env" in rendered
    assert "WorkingDirectory=/opt/gxp/current-backend" in rendered
    assert "ExecStart=/opt/gxp/current-venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000" in rendered
    assert "{{" not in rendered


def test_render_vm_runtime_assets_service_uses_validation_env_override(tmp_path: Path):
    output = tmp_path / "gxp.validation.service"
    env = {
        "VM_APP_USER": "gxp",
        "VM_APP_GROUP": "gxp",
        "VM_CURRENT_BACKEND_RELEASE_LINK": "/opt/gxp/current-backend",
        "VM_CURRENT_BACKEND_VENV_LINK": "/opt/gxp/current-venv",
        "VM_SERVICE_WORKING_DIRECTORY": "/opt/gxp/backend-releases/abc123",
        "VM_SERVICE_EXECUTABLE": "/opt/gxp/backend-venvs/abc123/bin/uvicorn",
        "VM_SERVICE_ENVIRONMENT_FILE": "/tmp/runtime.systemd.env",
        "APP_PORT": "8001",
    }

    completed = subprocess.run(
        [sys.executable, "tools/render_vm_runtime_assets.py", "service", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rendered = output.read_text(encoding="utf-8")
    assert "EnvironmentFile=/tmp/runtime.systemd.env" in rendered
    assert "WorkingDirectory=/opt/gxp/backend-releases/abc123" in rendered
    assert "ExecStart=/opt/gxp/backend-venvs/abc123/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8001" in rendered
    assert "{{" not in rendered


def test_render_vm_runtime_assets_service_fails_when_required_service_env_missing(tmp_path: Path):
    output = tmp_path / "gxp.service"
    env = {
        "VM_APP_USER": "gxp",
        "VM_APP_GROUP": "gxp",
        "VM_CURRENT_BACKEND_RELEASE_LINK": "/opt/gxp/current-backend",
        "APP_PORT": "8000",
    }

    completed = subprocess.run(
        [sys.executable, "tools/render_vm_runtime_assets.py", "service", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Missing required environment variable: VM_CURRENT_BACKEND_VENV_LINK" in completed.stderr


def test_render_vm_runtime_assets_nginx_fails_when_required_nginx_env_missing(tmp_path: Path):
    output = tmp_path / "gxp.conf"
    env = {
        "GXP_FRONTEND_DIST_ROOT": "/opt/gxp/frontend-dist",
        "VM_TLS_CERT_PATH": "/etc/ssl/certs/gxp.crt",
        "VM_TLS_KEY_PATH": "/etc/ssl/private/gxp.key",
        "APP_PORT": "8000",
    }

    completed = subprocess.run(
        [sys.executable, "tools/render_vm_runtime_assets.py", "nginx", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Missing required environment variable: PUBLIC_BASE_URL" in completed.stderr
