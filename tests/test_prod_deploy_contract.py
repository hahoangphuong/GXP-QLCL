from tools.validate_prod_deploy import validate_prod_deploy_env


def test_validate_prod_deploy_accepts_external_bridge_single_service_baseline():
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

    assert report.errors == []
    assert report.plan is not None
    assert report.plan.db_name == "gxp_qlcl"
    assert report.plan.db_user == "gxp_app"
    assert report.plan.frontend_topology == "single_cloud_run_service"
    assert report.plan.runtime_env["STORAGE_CLASS"] == "external_bridge_http"


def test_validate_prod_deploy_rejects_non_bridge_storage_and_missing_iap_fields():
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
            "STORAGE_CLASS": "synology_private_share_prod",
        }
    )

    assert any("AUTH_IAP_EXPECTED_AUDIENCE is required." in item for item in report.errors)
    assert any("AUTH_IAP_ALLOWED_EMAIL_DOMAIN is required." in item for item in report.errors)
    assert any("STORAGE_CLASS must be external_bridge_http" in item for item in report.errors)


def test_validate_prod_deploy_requires_hmac_secret_when_hmac_mode_selected():
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
            "BRIDGE_AUTH_MODE": "hmac_jwt",
            "STORAGE_BRIDGE_CLIENT_ID": "gxp-web",
            "STORAGE_BRIDGE_TOKEN_ISSUER": "gxp-qlcl",
        }
    )

    assert any("STORAGE_BRIDGE_SIGNING_KEY_SECRET is required" in item for item in report.errors)
