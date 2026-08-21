from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import StorageBinding
from backend.app.storage.binding_lookup import StorageBindingLookupService
from backend.app.storage.external_bridge import ExternalBridgeStorageService
from backend.app.storage.factory import create_storage_service_from_env, storage_config_from_env
from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageOperationError


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_storage_config_from_env_reads_required_roots(tmp_path: Path):
    inspection_root = tmp_path / "inspection"
    dkkd_root = tmp_path / "dkkd"
    config = storage_config_from_env(
        {
            "STORAGE_INSPECTION_ROOT": str(inspection_root),
            "STORAGE_DKKD_ROOT": str(dkkd_root),
            "STORAGE_CLASS": "synology_private_share_nonprod",
        }
    )

    assert config.inspection_root == inspection_root
    assert config.dkkd_root == dkkd_root
    assert config.storage_class == "synology_private_share_nonprod"


def test_create_storage_service_from_env_returns_local_adapter(tmp_path: Path):
    inspection_root = tmp_path / "inspection"
    service = create_storage_service_from_env({"STORAGE_INSPECTION_ROOT": str(inspection_root)})

    assert isinstance(service, LocalStorageService)
    assert service.config.inspection_root == inspection_root


def test_create_storage_service_from_env_returns_external_bridge_adapter():
    service = create_storage_service_from_env(
        {
            "STORAGE_CLASS": "external_bridge_http",
            "STORAGE_BRIDGE_BASE_URL": "https://bridge.internal",
            "STORAGE_BRIDGE_AUTH_AUDIENCE": "https://bridge.internal",
        }
    )

    assert isinstance(service, ExternalBridgeStorageService)
    assert service.config.base_url == "https://bridge.internal"


def test_storage_config_from_env_requires_inspection_root():
    try:
        storage_config_from_env({})
    except StorageOperationError as exc:
        assert "STORAGE_INSPECTION_ROOT" in str(exc)
    else:
        raise AssertionError("Expected missing inspection root env var to fail.")


def test_lookup_service_prefers_existing_storage_binding(tmp_path: Path):
    inspection_root = tmp_path / "inspection"
    inspection_root.mkdir()
    bound_folder = inspection_root / "2026" / "Folder - (ID-103) - (KT-1376-GMP)"
    bound_folder.mkdir(parents=True)
    storage = LocalStorageService(
        create_storage_service_from_env({"STORAGE_INSPECTION_ROOT": str(inspection_root)}).config
    )
    lookup = StorageBindingLookupService(storage)

    with build_session() as session:
        binding = StorageBinding(
            case_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
            relative_path="2026/Folder - (ID-103) - (KT-1376-GMP)",
            observed_folder_label="Folder - (ID-103) - (KT-1376-GMP)",
            storage_class=storage.config.storage_class,
        )
        session.add(binding)
        session.commit()

        result = lookup.get_inspection_folder(
            session,
            case_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )

    assert result.source == "binding"
    assert result.binding is not None
    assert result.resolution.relative_path == "2026/Folder - (ID-103) - (KT-1376-GMP)"


def test_lookup_service_falls_back_to_live_resolution_when_binding_missing_on_disk(tmp_path: Path):
    inspection_root = tmp_path / "inspection"
    inspection_root.mkdir()
    live_folder = inspection_root / "2026" / "Live Folder - (ID-103) - (KT-1376-GMP)"
    live_folder.mkdir(parents=True)
    storage = create_storage_service_from_env({"STORAGE_INSPECTION_ROOT": str(inspection_root)})
    lookup = StorageBindingLookupService(storage)

    with build_session() as session:
        binding = StorageBinding(
            case_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
            relative_path="2026/Stale Folder - (ID-103) - (KT-1376-GMP)",
            observed_folder_label="Stale Folder - (ID-103) - (KT-1376-GMP)",
            storage_class=storage.config.storage_class,
        )
        session.add(binding)
        session.commit()

        result = lookup.get_inspection_folder(
            session,
            case_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )
        session.commit()
        refreshed = session.query(StorageBinding).one()

    assert result.source == "live_resolution"
    assert result.binding is not None
    assert refreshed.relative_path == "2026/Live Folder - (ID-103) - (KT-1376-GMP)"


def test_lookup_service_resolves_dkkd_folder_from_site_token(tmp_path: Path):
    inspection_root = tmp_path / "inspection"
    dkkd_root = tmp_path / "dkkd"
    inspection_root.mkdir()
    dkkd_root.mkdir()
    (dkkd_root / "US Pharma - 12 Street (91)").mkdir(parents=True)
    storage = create_storage_service_from_env(
        {
            "STORAGE_INSPECTION_ROOT": str(inspection_root),
            "STORAGE_DKKD_ROOT": str(dkkd_root),
        }
    )
    lookup = StorageBindingLookupService(storage)

    with build_session() as session:
        result = lookup.get_dkkd_folder(
            session,
            case_id=None,
            site_legacy_id=91,
        )

    assert result.source == "live_resolution"
    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.resolution.relative_path == "US Pharma - 12 Street (91)"
