from pathlib import Path

from tools.validate_phase18_storage_bridge_bootstrap import (
    load_json_file,
    validate_bridge_env_contract,
    validate_storage_bridge_bootstrap,
)


def test_validate_bridge_env_contract_accepts_filesystem_backed_bridge():
    errors, warnings = validate_bridge_env_contract(
        {
            "DEPLOYMENT_PLATFORM": "google_cloud_run",
            "STORAGE_CLASS": "synology_private_share_nonprod",
            "STORAGE_INSPECTION_ROOT": "/mnt/synology/inspection",
            "STORAGE_DKKD_ROOT": "/mnt/synology/dkkd",
            "STORAGE_TEMPLATE_ROOT": "/mnt/synology/templates",
        }
    )

    assert errors == []
    assert warnings == []


def test_validate_storage_bridge_bootstrap_accepts_example_shape():
    config = {
        "project_id": "gxp-project-id",
        "region": "asia-southeast1",
        "service_name": "gxp-storage-bridge",
        "image": "asia-southeast1-docker.pkg.dev/gxp-project-id/gxp-web/gxp-storage-bridge:build-001",
        "service_account": "gxp-storage-bridge@gxp-project-id.iam.gserviceaccount.com",
        "caller_service_account": "gxp-web-api@gxp-project-id.iam.gserviceaccount.com",
        "env_file": "backend/.env.storage_bridge.cloudrun.example",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 10,
        "timeout_seconds": 300,
        "min_instances": 0,
        "max_instances": 2,
        "ingress": "all",
        "allow_unauthenticated": False,
        "vpc_network": "projects/gxp-project-id/global/networks/gxp-private",
        "vpc_subnet": "projects/gxp-project-id/regions/asia-southeast1/subnetworks/gxp-private-ase1",
        "vpc_egress": "private-ranges-only",
        "storage_mounts": [
            {
                "name": "inspection",
                "mount_path": "/mnt/synology/inspection",
                "server": "10.10.0.20",
                "export_path": "/volume1/inspection",
                "read_only": False,
            }
        ],
    }

    report = validate_storage_bridge_bootstrap(config)

    assert report.errors == []
    assert "--add-volume" in report.deploy_command_preview
    assert "services" in report.invoker_binding_preview


def test_validate_storage_bridge_bootstrap_rejects_external_bridge_storage_class():
    config = {
        "project_id": "gxp-project-id",
        "region": "asia-southeast1",
        "service_name": "gxp-storage-bridge",
        "image": "image",
        "service_account": "bridge@example.com",
        "caller_service_account": "app@example.com",
        "env_file": "backend/.env.cloudrun.external_bridge.example",
        "cpu": "1",
        "memory": "1Gi",
        "concurrency": 10,
        "timeout_seconds": 300,
        "min_instances": 0,
        "max_instances": 1,
        "ingress": "all",
        "allow_unauthenticated": False,
        "vpc_network": "projects/gxp/global/networks/private",
        "vpc_subnet": "projects/gxp/regions/asia-southeast1/subnetworks/private",
        "storage_mounts": [
            {
                "name": "inspection",
                "mount_path": "/mnt/synology/inspection",
                "server": "10.10.0.20",
                "export_path": "/volume1/inspection",
                "read_only": False,
            }
        ],
    }

    report = validate_storage_bridge_bootstrap(config)

    assert any("Bridge runtime must not use STORAGE_CLASS=external_bridge_http." in item for item in report.errors)


def test_load_json_file_reads_bootstrap(tmp_path: Path):
    path = tmp_path / "bootstrap.json"
    path.write_text('{"service_name":"gxp-storage-bridge"}', encoding="utf-8")

    payload = load_json_file(path)

    assert payload["service_name"] == "gxp-storage-bridge"
