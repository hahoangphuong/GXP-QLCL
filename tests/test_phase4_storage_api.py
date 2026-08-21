from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models.phase1 import StorageBinding
from backend.app.main import create_app
from backend.app.storage import LocalStorageService, StorageBindingLookupService, StorageConfig


def build_storage_service(tmp_path: Path) -> LocalStorageService:
    inspection_root = tmp_path / "inspection-root"
    dkkd_root = tmp_path / "dkkd-root"
    inspection_root.mkdir()
    dkkd_root.mkdir()
    return LocalStorageService(StorageConfig(inspection_root=inspection_root, dkkd_root=dkkd_root))


def test_create_app_sets_storage_unconfigured_state_when_env_missing():
    app = create_app("sqlite:///:memory:")

    assert app.state.storage_service is None
    assert app.state.storage_lookup_service is None
    assert app.state.storage_error is not None


def test_create_app_sets_storage_lookup_service_when_storage_is_injected(tmp_path: Path):
    storage = build_storage_service(tmp_path)

    app = create_app("sqlite:///:memory:", storage_service=storage)

    assert app.state.storage_service is storage
    assert isinstance(app.state.storage_lookup_service, StorageBindingLookupService)
    assert app.state.storage_error is None


def test_create_app_can_build_storage_service_from_env(tmp_path: Path):
    inspection_root = tmp_path / "inspection-root"
    inspection_root.mkdir()

    app = create_app(
        "sqlite:///:memory:",
        storage_env={"STORAGE_INSPECTION_ROOT": str(inspection_root), "STORAGE_CLASS": "synology_private_share_nonprod"},
    )

    assert app.state.storage_service is not None
    assert app.state.storage_service.config.storage_class == "synology_private_share_nonprod"
    assert isinstance(app.state.storage_lookup_service, StorageBindingLookupService)


def test_storage_probe_route_is_registered():
    app = create_app("sqlite:///:memory:")
    routes = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/storage/inspection-folder" in routes
    assert "/storage/dkkd-folder" in routes


def test_storage_lookup_state_can_use_existing_binding(tmp_path: Path):
    storage = build_storage_service(tmp_path)
    folder = storage.inspection_root / "2026" / "Folder - (ID-103) - (KT-1376-GMP)"
    folder.mkdir(parents=True)

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            StorageBinding(
                case_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                year=2026,
                site_legacy_id=103,
                inspection_legacy_code="KT-1376-GMP",
                relative_path="2026/Folder - (ID-103) - (KT-1376-GMP)",
                observed_folder_label="Folder - (ID-103) - (KT-1376-GMP)",
                storage_class=storage.config.storage_class,
            )
        )
        session.commit()

        app = create_app(str(engine.url), storage_service=storage)
        lookup_service = app.state.storage_lookup_service
        result = lookup_service.get_inspection_folder(
            session,
            case_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )

    assert result.source == "binding"
    assert result.resolution.relative_path == "2026/Folder - (ID-103) - (KT-1376-GMP)"


def test_storage_lookup_state_can_resolve_dkkd_folder(tmp_path: Path):
    storage = build_storage_service(tmp_path)
    folder = storage.dkkd_root / "US Pharma - 12 Street (91)"
    folder.mkdir(parents=True)

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        app = create_app(str(engine.url), storage_service=storage)
        lookup_service = app.state.storage_lookup_service
        result = lookup_service.get_dkkd_folder(
            session,
            case_id=None,
            site_legacy_id=91,
        )

    assert result.source == "live_resolution"
    assert result.resolution.relative_path == "US Pharma - 12 Street (91)"
