from pathlib import Path

from tools.validate_phase18_storage_bridge_bootstrap import (
    load_json_file,
    validate_bridge_env_contract,
    validate_storage_bridge_bootstrap,
)


def test_validate_bridge_env_contract_accepts_cloud_run_smb_bridge_baseline():
    errors, warnings = validate_bridge_env_contract(
        {
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "BRIDGE_RUNTIME": "storage_bridge",
            "STORAGE_CLASS": "synology_smb_bridge",
            "STORAGE_INSPECTION_ROOT": r"\\100.x.x.x\Share\01 - Kiem tra GPs",
            "STORAGE_DKKD_ROOT": r"\\100.x.x.x\Share\Chung nhan DDKKDD",
            "STORAGE_TEMPLATE_ROOT": r"\\100.x.x.x\Share\Templates",
            "SMB_AUTH_PROTOCOL": "ntlm",
            "BRIDGE_AUTH_MODE": "google_oidc",
            "TAILSCALE_ENABLE": "1",
        }
    )

    assert errors == []
    assert warnings == []


def test_validate_storage_bridge_bootstrap_accepts_example_shape():
    config = {
        "project_id": "gxp-qlcl",
        "region": "asia-southeast1",
        "service_name": "gxp-storage-bridge",
        "artifact_registry_repo": "gxp-qlcl",
        "image_name": "gxp-storage-bridge",
        "image_tag": "bootstrap-001",
        "service_account": "gxp-storage-bridge@gxp-qlcl.iam.gserviceaccount.com",
        "caller_service_account": "gxp-web-runtime@gxp-qlcl.iam.gserviceaccount.com",
        "env_file": "backend/.env.storage_bridge.cloudrun.example",
        "tailscale_authkey_secret": "gxp-tailscale-auth-key",
        "smb_username_secret": "gxp-storage-bridge-smb-username",
        "smb_password_secret": "gxp-storage-bridge-smb-password",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 10,
        "timeout_seconds": 300,
        "min_instances": 0,
        "max_instances": 2,
        "ingress": "all",
        "allow_unauthenticated": False,
    }

    report = validate_storage_bridge_bootstrap(config)

    assert report.errors == []
    assert "gcloud" in report.build_command_preview
    assert "deploy" in report.deploy_command_preview
    assert "status.url" in report.bridge_base_url_source


def test_validate_storage_bridge_bootstrap_rejects_non_smb_bridge_runtime():
    config = {
        "project_id": "gxp-qlcl",
        "region": "asia-southeast1",
        "service_name": "gxp-storage-bridge",
        "artifact_registry_repo": "gxp-qlcl",
        "image_name": "gxp-storage-bridge",
        "image_tag": "bootstrap-001",
        "service_account": "bridge@example.com",
        "caller_service_account": "app@example.com",
        "env_file": "backend/.env.cloudrun.external_bridge.example",
        "tailscale_authkey_secret": "a",
        "smb_username_secret": "b",
        "smb_password_secret": "c",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 10,
        "timeout_seconds": 300,
        "min_instances": 0,
        "max_instances": 1,
        "ingress": "all",
        "allow_unauthenticated": False,
    }

    report = validate_storage_bridge_bootstrap(config)

    assert any("STORAGE_CLASS must be synology_smb_bridge" in item for item in report.errors)


def test_load_json_file_reads_bootstrap(tmp_path: Path):
    path = tmp_path / "bootstrap.json"
    path.write_text('{"service_name":"gxp-storage-bridge"}', encoding="utf-8")

    payload = load_json_file(path)

    assert payload["service_name"] == "gxp-storage-bridge"
