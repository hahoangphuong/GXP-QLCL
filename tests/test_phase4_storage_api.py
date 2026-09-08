from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, StorageResolutionStatus
from backend.app.db.models.phase1 import (
    Case,
    Company,
    LegacyInspectionStorageAnchor,
    Site,
    StorageBinding,
    StorageResolutionLog,
)
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


def test_inspection_folder_route_accepts_optional_year_without_changing_dkkd_contract():
    app = create_app("sqlite:///:memory:")
    schema = app.openapi()
    inspection_parameters = schema["paths"]["/storage/inspection-folder"]["get"]["parameters"]
    dkkd_parameters = schema["paths"]["/storage/dkkd-folder"]["get"]["parameters"]

    year = next(parameter for parameter in inspection_parameters if parameter["name"] == "year")
    assert year["required"] is False
    assert all(parameter["name"] != "year" for parameter in dkkd_parameters)


def test_inspection_folder_route_commits_automatic_lookup_observation(tmp_path: Path):
    storage = build_storage_service(tmp_path)
    folder = storage.inspection_root / "2024" / "Facility - (ID-103) - (KT-1376-GMP)"
    folder.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{tmp_path / 'storage-api.db'}", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        company = Company(legal_name="Storage API Company")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, legacy_site_id=103, site_name="Storage API Facility")
        session.add(site)
        session.flush()
        case = Case(
            site_id=site.id,
            legacy_inspection_id=1376,
            legacy_inspection_code="KT-1376-GMP",
            gxp_type="GMP",
            state=CaseState.INSPECTION_COMPLETED,
        )
        session.add(case)
        session.flush()
        session.add(
            LegacyInspectionStorageAnchor(
                case_id=case.id,
                source_sheet="db.ktra",
                source_row=1376,
                registration_submission_raw="2024-01-01",
                registration_submission_year=2024,
                registration_submission_status="usable",
                inspection_date_raw="-",
                inspection_year=None,
                inspection_year_status="unavailable",
                source_hash="a" * 64,
                source_version="b" * 64,
            )
        )
        session.commit()
        case_id = case.id

    app = create_app(str(engine.url), storage_service=storage)
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/storage/inspection-folder")
    with Session(engine) as session:
        response = endpoint(
            year=None,
            case_id=case_id,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
            session=session,
            lookup_service=app.state.storage_lookup_service,
            user=build_authenticated_user("storage-reader", "reader", permissions={"document.read"}),
        )

    assert response.status == "resolved"
    assert response.relative_path == "2024/Facility - (ID-103) - (KT-1376-GMP)"
    with Session(engine) as session:
        log = session.query(StorageResolutionLog).one()
        binding = session.query(StorageBinding).one()

    assert log.case_id == case_id
    assert log.status is StorageResolutionStatus.RESOLVED
    assert binding.case_id == case_id
    assert binding.relative_path == "2024/Facility - (ID-103) - (KT-1376-GMP)"


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
