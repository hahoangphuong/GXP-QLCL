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
    assert report.plan.python_series == "3.12"
    assert report.plan.runtime_requirements_lock_file == "backend/requirements.runtime.vm.lock.txt"
    assert report.plan.runtime_env["VM_SRC_DIR"] == "/opt/gxp/src/GXP-QLCL"
    assert report.plan.runtime_env["VM_RUNTIME_ENV_FILE"] == "/etc/gxp/runtime.env"
    assert report.plan.runtime_env["VM_SYSTEMD_ENV_FILE"] == "/etc/gxp/runtime.systemd.env"
    assert report.plan.runtime_env["SYSTEMD_SERVICE_NAME"] == "gxp-web"
    assert report.plan.runtime_env["PUBLIC_BASE_URL"] == "https://gxp.example.com"
    assert report.plan.runtime_env["VM_CURRENT_BACKEND_VENV_LINK"] == "/opt/gxp/current-venv"
    assert report.plan.pg_listen_addresses == "127.0.0.1"
    assert report.plan.runtime_env["PG_LISTEN_ADDRESSES"] == "127.0.0.1"


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


def test_validate_vm_prod_deploy_accepts_private_postgres_listener_and_exact_remote_hba_config():
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
            "PG_LISTEN_ADDRESSES": "127.0.0.1,10.148.0.3",
            "PG_PRIVATE_CLIENT_CIDR": "10.20.0.0/26",
            "PG_PRIVATE_DB_NAME": "gmpnn_ai",
            "PG_PRIVATE_RUNTIME_USER": "gmpnn_ai_app",
            "PG_PRIVATE_MIGRATOR_USER": "gmpnn_ai_migrator",
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
    assert report.plan.pg_listen_addresses == "127.0.0.1,10.148.0.3"
    assert report.plan.runtime_env["DB_HOST"] == "127.0.0.1"
    assert report.plan.runtime_env["PG_LISTEN_ADDRESSES"] == "127.0.0.1,10.148.0.3"
    assert report.plan.runtime_env["PG_PRIVATE_CLIENT_CIDR"] == "10.20.0.0/26"
    assert report.plan.runtime_env["PG_PRIVATE_DB_NAME"] == "gmpnn_ai"
    assert report.plan.runtime_env["PG_PRIVATE_RUNTIME_USER"] == "gmpnn_ai_app"
    assert report.plan.runtime_env["PG_PRIVATE_MIGRATOR_USER"] == "gmpnn_ai_migrator"


def test_validate_vm_prod_deploy_rejects_broad_or_public_postgres_listener_values():
    base = {
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
        "SMB_USERNAME": "gxp-smb",
        "SMB_PASSWORD": "secret",
        "PUBLIC_BASE_URL": "https://gxp.example.com",
        "BACKUP_GCS_BUCKET": "gs://gxp-backups",
    }

    wildcard = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "*"})
    open_listener = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "0.0.0.0"})
    malformed = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,not-an-ip"})
    public = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,8.8.8.8"})
    link_local = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,169.254.1.1"})
    multicast = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,224.0.0.1"})
    reserved = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,240.0.0.1"})
    benchmark = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,198.18.0.1"})
    documentation = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,192.0.2.1"})
    outside_172 = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,172.32.0.1"})
    outside_192 = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": "127.0.0.1,192.169.0.1"})

    assert any("wildcard" in item for item in wildcard.errors)
    assert any("0.0.0.0" in item for item in open_listener.errors)
    assert any("invalid IP address" in item for item in malformed.errors)
    assert any("RFC1918 private IPv4" in item for item in public.errors)
    assert any("RFC1918 private IPv4" in item for item in link_local.errors)
    assert any("RFC1918 private IPv4" in item for item in multicast.errors)
    assert any("RFC1918 private IPv4" in item for item in reserved.errors)
    assert any("RFC1918 private IPv4" in item for item in benchmark.errors)
    assert any("RFC1918 private IPv4" in item for item in documentation.errors)
    assert any("RFC1918 private IPv4" in item for item in outside_172.errors)
    assert any("RFC1918 private IPv4" in item for item in outside_192.errors)


def test_validate_vm_prod_deploy_accepts_rfc1918_listener_boundaries_only():
    base = {
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
        "SMB_USERNAME": "gxp-smb",
        "SMB_PASSWORD": "secret",
        "PUBLIC_BASE_URL": "https://gxp.example.com",
        "BACKUP_GCS_BUCKET": "gs://gxp-backups",
    }

    accepted_listeners = [
        "127.0.0.1,10.0.0.1",
        "127.0.0.1,10.255.255.254",
        "127.0.0.1,172.16.0.1",
        "127.0.0.1,172.31.255.254",
        "127.0.0.1,192.168.0.1",
        "127.0.0.1,192.168.255.254",
    ]

    for listen_addresses in accepted_listeners:
        report = validate_vm_prod_deploy_env({**base, "PG_LISTEN_ADDRESSES": listen_addresses})
        assert report.errors == [], listen_addresses


def test_validate_vm_prod_deploy_accepts_only_rfc1918_private_client_cidrs():
    base = {
        "DEPLOYMENT_PLATFORM": "compute_engine_vm",
        "AUTH_PROVIDER": "google_oidc",
        "AUTH_ROLE_SOURCE": "database",
        "AUTH_OIDC_CLIENT_ID": "client-id.apps.googleusercontent.com",
        "DB_MODE": "local_postgres",
        "DB_NAME": "gxp_qlcl",
        "DB_USER": "gxp_app",
        "DB_PASSWORD": "secret",
        "DB_HOST": "127.0.0.1",
        "PG_PRIVATE_DB_NAME": "gmpnn_ai",
        "PG_PRIVATE_RUNTIME_USER": "gmpnn_ai_app",
        "PG_PRIVATE_MIGRATOR_USER": "gmpnn_ai_migrator",
        "STORAGE_CLASS": "synology_smb",
        "STORAGE_INSPECTION_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs",
        "STORAGE_DKKD_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Chứng nhận ĐĐKKDD",
        "STORAGE_TEMPLATE_ROOT": r"\\100.95.45.127\Hồ sơ nội bộ\01 - Kiểm tra GPs\Templates",
        "SMB_USERNAME": "gxp-smb",
        "SMB_PASSWORD": "secret",
        "PUBLIC_BASE_URL": "https://gxp.example.com",
        "BACKUP_GCS_BUCKET": "gs://gxp-backups",
    }

    for cidr in ["10.20.0.0/26", "172.16.0.0/12", "192.168.10.0/24"]:
        report = validate_vm_prod_deploy_env({**base, "PG_PRIVATE_CLIENT_CIDR": cidr})
        assert report.errors == [], cidr

    rejected_cidrs = [
        "127.0.0.0/8",
        "169.254.0.0/16",
        "198.18.0.0/15",
        "192.0.2.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    ]
    for cidr in rejected_cidrs:
        report = validate_vm_prod_deploy_env({**base, "PG_PRIVATE_CLIENT_CIDR": cidr})
        assert any("RFC1918 private IPv4 range" in item for item in report.errors), cidr


def test_validate_vm_prod_deploy_rejects_overly_broad_private_remote_postgres_hba_values():
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
            "PG_PRIVATE_CLIENT_CIDR": "0.0.0.0/0",
            "PG_PRIVATE_DB_NAME": "all",
            "PG_PRIVATE_RUNTIME_USER": "all",
            "PG_PRIVATE_MIGRATOR_USER": "gmpnn_ai_migrator",
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

    assert any("PG_PRIVATE_DB_NAME must not be all." in item for item in report.errors)
    assert any("PG_PRIVATE_RUNTIME_USER must not be all." in item for item in report.errors)
    assert any("must not be an open network like 0.0.0.0/0" in item for item in report.errors)


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


def test_validate_vm_prod_deploy_rejects_non_python_312_vm_baseline():
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
            "SMB_USERNAME": "gxp-smb",
            "SMB_PASSWORD": "secret",
            "PUBLIC_BASE_URL": "https://gxp.example.com",
            "BACKUP_GCS_BUCKET": "gs://gxp-backups",
            "VM_PYTHON_SERIES": "3.13",
        }
    )

    assert any("VM_PYTHON_SERIES must remain 3.12" in item for item in report.errors)
