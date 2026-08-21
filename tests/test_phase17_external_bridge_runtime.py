from backend.app.storage.external_bridge import ExternalBridgeStorageService
from backend.app.storage.factory import create_storage_service_from_env
from backend.storage_bridge_main import create_storage_bridge_app


def test_create_storage_service_from_env_supports_external_bridge_http():
    service = create_storage_service_from_env(
        {
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.internal",
            "STORAGE_BRIDGE_AUTH_AUDIENCE": "https://bridge.internal",
        }
    )

    assert isinstance(service, ExternalBridgeStorageService)
    assert service.config.auth_audience == "https://bridge.internal"


def test_storage_bridge_app_rejects_external_bridge_loop_configuration():
    service = create_storage_service_from_env(
        {
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.internal",
        }
    )

    app = create_storage_bridge_app(service)

    assert app.state.storage_service is None
    assert "filesystem-backed" in app.state.storage_error
