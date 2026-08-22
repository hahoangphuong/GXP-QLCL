from __future__ import annotations

import os
from pathlib import Path

from backend.app.storage.external_bridge import ExternalBridgeStorageService
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.smb import SmbStorageService
from backend.app.storage.types import (
    ExternalBridgeStorageConfig,
    SmbStorageConfig,
    StorageConfig,
    StorageOperationError,
    StorageServiceProtocol,
)


def storage_config_from_env(env: dict[str, str] | None = None) -> StorageConfig:
    source = os.environ if env is None else env
    inspection_root = source.get("STORAGE_INSPECTION_ROOT", "").strip()
    if not inspection_root:
        raise StorageOperationError("Missing required env var STORAGE_INSPECTION_ROOT.")
    dkkd_root = source.get("STORAGE_DKKD_ROOT", "").strip() or None
    template_root = source.get("STORAGE_TEMPLATE_ROOT", "").strip() or None
    storage_class = source.get("STORAGE_CLASS", "").strip() or "local_filesystem_fake"
    return StorageConfig(
        inspection_root=Path(inspection_root),
        dkkd_root=Path(dkkd_root) if dkkd_root else None,
        template_root=Path(template_root) if template_root else None,
        storage_class=storage_class,
    )


def create_storage_service_from_env(env: dict[str, str] | None = None) -> StorageServiceProtocol:
    source = os.environ if env is None else env
    storage_class = source.get("STORAGE_CLASS", "").strip() or "local_filesystem_fake"
    if storage_class == "external_bridge_http":
        base_url = source.get("STORAGE_BRIDGE_BASE_URL", "").strip()
        if not base_url:
            raise StorageOperationError("Missing required env var STORAGE_BRIDGE_BASE_URL.")
        auth_mode = source.get("BRIDGE_AUTH_MODE", "").strip().lower() or "google_oidc"
        audience = source.get("STORAGE_BRIDGE_AUTH_AUDIENCE", "").strip() or None
        return ExternalBridgeStorageService(
            ExternalBridgeStorageConfig(
                base_url=base_url,
                auth_mode=auth_mode,
                auth_audience=audience,
                auth_client_id=source.get("STORAGE_BRIDGE_CLIENT_ID", "").strip() or None,
                auth_token_issuer=source.get("STORAGE_BRIDGE_TOKEN_ISSUER", "").strip() or None,
                auth_signing_key=source.get("STORAGE_BRIDGE_SIGNING_KEY", "").strip() or None,
                storage_class=storage_class,
            )
        )
    if storage_class in {"synology_smb", "synology_smb_bridge"}:
        inspection_root = source.get("STORAGE_INSPECTION_ROOT", "").strip()
        if not inspection_root:
            raise StorageOperationError("Missing required env var STORAGE_INSPECTION_ROOT.")
        return SmbStorageService(
            SmbStorageConfig(
                inspection_root=inspection_root,
                dkkd_root=source.get("STORAGE_DKKD_ROOT", "").strip() or None,
                template_root=source.get("STORAGE_TEMPLATE_ROOT", "").strip() or None,
                username=source.get("SMB_USERNAME", "").strip() or None,
                password=source.get("SMB_PASSWORD", "").strip() or None,
                auth_protocol=source.get("SMB_AUTH_PROTOCOL", "").strip().lower() or "ntlm",
                port=int(source.get("SMB_PORT", "445")),
                encrypt=source.get("SMB_ENCRYPT", "false").strip().lower() in {"1", "true", "yes", "on"},
                connection_timeout=int(source.get("SMB_CONNECTION_TIMEOUT_SECONDS", "60")),
                storage_class="synology_smb",
            )
        )
    return FilesystemStorageService(storage_config_from_env(source))
