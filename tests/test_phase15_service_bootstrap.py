from pathlib import Path

from tools.validate_phase15_service_bootstrap import (
    load_json_file,
    validate_service_bootstrap_config,
)


def test_validate_service_bootstrap_accepts_nfs_volume_baseline():
    config = {
        "project_id": "gxp-project-id",
        "region": "asia-southeast1",
        "service_name": "gxp-web-api",
        "image": "asia-southeast1-docker.pkg.dev/gxp-project-id/gxp-web/gxp-web-api:build-001",
        "service_account": "gxp-web-api@gxp-project-id.iam.gserviceaccount.com",
        "env_file": "backend/.env.cloudrun.example",
        "secret_bindings_file": "infra/cloudrun/secret_bindings.example.json",
        "cloud_sql_connection_name": "gxp-project-id:asia-southeast1:gxp-qlcl-db",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 20,
        "timeout_seconds": 300,
        "min_instances": 0,
        "max_instances": 3,
        "ingress": "all",
        "allow_unauthenticated": False,
        "vpc_network": "projects/gxp-project-id/global/networks/gxp-private",
        "vpc_subnet": "projects/gxp-project-id/regions/asia-southeast1/subnetworks/gxp-private-ase1",
        "vpc_egress": "private-ranges-only",
        "storage_mode": "nfs_volume",
        "storage_mounts": [
            {
                "name": "inspection",
                "mount_path": "/mnt/synology/inspection",
                "server": "10.10.0.20",
                "export_path": "/volume1/01 - Kiem tra GPs",
                "read_only": False,
            }
        ],
    }

    report = validate_service_bootstrap_config(config)

    assert report.errors == []
    assert "--add-cloudsql-instances" in report.deploy_command_preview
    assert "--add-volume" in report.deploy_command_preview


def test_validate_service_bootstrap_rejects_tailscale_smb_mode():
    config = {
        "project_id": "gxp-project-id",
        "region": "asia-southeast1",
        "service_name": "gxp-web-api",
        "image": "image",
        "service_account": "svc@example.com",
        "env_file": "backend/.env.cloudrun.example",
        "secret_bindings_file": "infra/cloudrun/secret_bindings.example.json",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 1,
        "timeout_seconds": 60,
        "min_instances": 0,
        "max_instances": 1,
        "ingress": "all",
        "allow_unauthenticated": False,
        "storage_mode": "tailscale_smb_in_container",
        "storage_mounts": [],
    }

    report = validate_service_bootstrap_config(config)

    assert any("Cloud Run does not support mounting SMB/Tailscale" in item for item in report.errors)


def test_validate_service_bootstrap_requires_vpc_for_nfs_mode():
    config = {
        "project_id": "gxp-project-id",
        "region": "asia-southeast1",
        "service_name": "gxp-web-api",
        "image": "image",
        "service_account": "svc@example.com",
        "env_file": "backend/.env.cloudrun.example",
        "secret_bindings_file": "infra/cloudrun/secret_bindings.example.json",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 1,
        "timeout_seconds": 60,
        "min_instances": 0,
        "max_instances": 1,
        "ingress": "all",
        "allow_unauthenticated": False,
        "storage_mode": "nfs_volume",
        "storage_mounts": [
            {
                "name": "inspection",
                "mount_path": "/mnt/synology/inspection",
                "server": "10.10.0.20",
                "export_path": "/volume1/01 - Kiem tra GPs",
                "read_only": False,
            }
        ],
    }

    report = validate_service_bootstrap_config(config)

    assert "vpc_network is required when storage_mode=nfs_volume." in report.errors
    assert "vpc_subnet is required when storage_mode=nfs_volume." in report.errors


def test_validate_service_bootstrap_requires_bridge_fields_for_external_bridge_mode():
    config = {
        "project_id": "gxp-project-id",
        "region": "asia-southeast1",
        "service_name": "gxp-web-api",
        "image": "image",
        "service_account": "svc@example.com",
        "env_file": "backend/.env.cloudrun.example",
        "secret_bindings_file": "infra/cloudrun/secret_bindings.example.json",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 1,
        "timeout_seconds": 60,
        "min_instances": 0,
        "max_instances": 1,
        "ingress": "all",
        "allow_unauthenticated": False,
        "storage_mode": "external_bridge",
    }

    report = validate_service_bootstrap_config(config)

    assert "bridge_base_url is required when storage_mode=external_bridge." in report.errors
    assert "bridge_auth_audience is required when storage_mode=external_bridge." in report.errors


def test_load_json_file_reads_example_config(tmp_path: Path):
    config_path = tmp_path / "service.json"
    config_path.write_text('{"service_name":"gxp-web-api"}', encoding="utf-8")

    payload = load_json_file(config_path)

    assert payload["service_name"] == "gxp-web-api"
