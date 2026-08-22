from tools.validate_vm_prod_deploy import validate_vm_prod_deploy_env


def test_validate_vm_prod_deploy_accepts_local_postgres_direct_smb_oidc_baseline():
    report = validate_vm_prod_deploy_env(
        {
            "DEPLOYMENT_PLATFORM": "compute_engine_vm",
            "AUTH_PROVIDER": "google_oidc",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_OIDC_CLIENT_ID": "client-id.apps.googleusercontent.com",
            "AUTH_ALLOWED_EMAIL_DOMAIN": "example.com",
            "DB_MODE": "local_postgres",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "5432",
            "STORAGE_CLASS": "synology_smb",
            "STORAGE_INSPECTION_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
            "STORAGE_DKKD_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Chứng nhận ĐĐKKDD",
            "STORAGE_TEMPLATE_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Templates",
            "SMB_USERNAME": "gxp-smb",
            "SMB_PASSWORD": "secret",
            "PUBLIC_BASE_URL": "https://gxp.example.com",
            "BACKUP_GCS_BUCKET": "gs://gxp-backups",
        }
    )

    assert report.errors == []
    assert report.plan is not None
    assert report.plan.db_mode == "local_postgres"
    assert report.plan.storage_class == "synology_smb"
    assert report.plan.auth_provider == "google_oidc"
    assert report.plan.runtime_requirements_file == "backend/requirements.runtime.vm.txt"
    assert ":***@" in report.plan.database_url_redacted
    assert report.plan.node_major == 22
    assert report.plan.swap_size_gb == 4
    assert report.plan.app_port == 8000
    assert report.plan.runtime_env["VM_SRC_DIR"] == "/opt/gxp/src/GXP-QLCL"
    assert report.plan.runtime_env["VM_RUNTIME_ENV_FILE"] == "/etc/gxp/runtime.env"
    assert report.plan.runtime_env["SYSTEMD_SERVICE_NAME"] == "gxp-web"
    assert report.plan.runtime_env["PUBLIC_BASE_URL"] == "https://gxp.example.com"


def test_validate_vm_prod_deploy_accepts_cloud_sql_dormant_option():
    report = validate_vm_prod_deploy_env(
        {
            "DEPLOYMENT_PLATFORM": "compute_engine_vm",
            "AUTH_PROVIDER": "google_iap_jwt",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_IAP_EXPECTED_AUDIENCE": "/projects/123/locations/asia-southeast1/services/gxp-web",
            "DB_MODE": "cloud_sql",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "CLOUD_SQL_CONNECTION_NAME": "gxp-qlcl:asia-southeast1:gxp-db",
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_INSPECTION_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
            "STORAGE_DKKD_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Chứng nhận ĐĐKKDD",
            "STORAGE_TEMPLATE_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Templates",
            "PUBLIC_BASE_URL": "https://gxp.example.com",
            "BACKUP_GCS_BUCKET": "gs://gxp-backups",
        }
    )

    assert report.errors == []
    assert report.plan is not None
    assert report.plan.db_mode == "cloud_sql"
    assert report.plan.storage_class == "external_bridge_http"


def test_validate_vm_prod_deploy_rejects_postgres_superuser_and_public_db_host():
    report = validate_vm_prod_deploy_env(
        {
            "DEPLOYMENT_PLATFORM": "compute_engine_vm",
            "AUTH_PROVIDER": "google_oidc",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_OIDC_CLIENT_ID": "client-id.apps.googleusercontent.com",
            "DB_MODE": "local_postgres",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_HOST": "10.10.10.10",
            "STORAGE_CLASS": "synology_smb",
            "STORAGE_INSPECTION_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
            "STORAGE_DKKD_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Chứng nhận ĐĐKKDD",
            "STORAGE_TEMPLATE_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Templates",
            "SMB_USERNAME": "gxp-smb",
            "SMB_PASSWORD": "secret",
            "PUBLIC_BASE_URL": "https://gxp.example.com",
            "BACKUP_GCS_BUCKET": "gs://gxp-backups",
        }
    )

    assert any("DB_USER must not be postgres" in item for item in report.errors)
    assert any("DB_HOST must stay local/private" in item for item in report.errors)


def test_validate_vm_prod_deploy_requires_smb_credentials_for_direct_smb_mode():
    report = validate_vm_prod_deploy_env(
        {
            "DEPLOYMENT_PLATFORM": "compute_engine_vm",
            "AUTH_PROVIDER": "google_oidc",
            "AUTH_ROLE_SOURCE": "database",
            "AUTH_OIDC_CLIENT_ID": "client-id.apps.googleusercontent.com",
            "DB_MODE": "local_postgres",
            "DB_NAME": "gxp_qlcl",
            "DB_USER": "gxp_app",
            "DB_PASSWORD": "secret",
            "DB_HOST": "127.0.0.1",
            "STORAGE_CLASS": "synology_smb",
            "STORAGE_INSPECTION_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
            "STORAGE_DKKD_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Chứng nhận ĐĐKKDD",
            "STORAGE_TEMPLATE_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Templates",
            "PUBLIC_BASE_URL": "https://gxp.example.com",
            "BACKUP_GCS_BUCKET": "gs://gxp-backups",
        }
    )

    assert any("SMB_USERNAME is required." in item for item in report.errors)
    assert any("SMB_PASSWORD is required." in item for item in report.errors)
