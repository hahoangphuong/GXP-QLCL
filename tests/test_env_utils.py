from pathlib import Path

import yaml

from tools.env_utils import dotenv_to_yaml_env_file, write_yaml_env_file
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
