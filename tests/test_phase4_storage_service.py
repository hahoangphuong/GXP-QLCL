from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import StorageBinding, StorageResolutionLog
from backend.app.storage.binding_service import StorageBindingService
from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


def build_service(tmp_path: Path) -> LocalStorageService:
    inspection_root = tmp_path / "inspection-root"
    dkkd_root = tmp_path / "dkkd-root"
    inspection_root.mkdir()
    dkkd_root.mkdir()
    return LocalStorageService(StorageConfig(inspection_root=inspection_root, dkkd_root=dkkd_root))


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_resolve_inspection_folder_returns_resolved_for_unique_match(tmp_path: Path):
    service = build_service(tmp_path)
    folder = service.inspection_root / "2026" / "120 Armephaco - (ID-103) - (KT-1376-GMP)"
    folder.mkdir(parents=True)

    resolution = service.resolve_inspection_folder(year=2026, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert resolution.status == StorageResolutionStatus.RESOLVED
    assert resolution.relative_path == "2026/120 Armephaco - (ID-103) - (KT-1376-GMP)"


def test_resolve_inspection_folder_fails_closed_on_ambiguous_match(tmp_path: Path):
    service = build_service(tmp_path)
    (service.inspection_root / "2026" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    (service.inspection_root / "2026" / "B - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    resolution = service.resolve_inspection_folder(year=2026, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert resolution.status == StorageResolutionStatus.AMBIGUOUS
    assert resolution.candidate_count == 2
    assert resolution.relative_path is None


def test_resolve_inspection_folder_returns_not_found_when_year_missing(tmp_path: Path):
    service = build_service(tmp_path)

    resolution = service.resolve_inspection_folder(year=2026, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert resolution.status == StorageResolutionStatus.NOT_FOUND


def test_resolve_inspection_folder_cross_year_uses_only_exact_legacy_identity_tokens(tmp_path: Path):
    service = build_service(tmp_path)
    resolved = service.inspection_root / "2025" / "Armephaco - (id-1) - (kt-1-gmp)"
    resolved.mkdir(parents=True)
    (service.inspection_root / "2026" / "Wrong site - (ID-10) - (KT-1-GMP)").mkdir(parents=True)
    (service.inspection_root / "2026" / "Wrong inspection - (ID-1) - (KT-10-GMP)").mkdir(parents=True)
    (service.inspection_root / "Templates" / "Ignored - (ID-1) - (KT-1-GMP)").mkdir(parents=True)
    (service.inspection_root / "2027" / "Legacy - (1) - (KT-1-GMP)").mkdir(parents=True)

    resolution = service.resolve_inspection_folder(site_legacy_id=1, inspection_legacy_code="KT-1-GMP")

    assert resolution.status == StorageResolutionStatus.RESOLVED
    assert resolution.relative_path == "2025/Armephaco - (id-1) - (kt-1-gmp)"


def test_resolve_inspection_folder_cross_year_fails_closed_on_duplicate_or_missing_identity(tmp_path: Path):
    service = build_service(tmp_path)
    (service.inspection_root / "2024" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    (service.inspection_root / "2026" / "B - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    duplicate = service.resolve_inspection_folder(site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
    explicit = service.resolve_inspection_folder(year=2024, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
    missing = service.resolve_inspection_folder(site_legacy_id=103, inspection_legacy_code="KT-999-GMP")

    assert duplicate.status == StorageResolutionStatus.AMBIGUOUS
    assert duplicate.candidate_count == 2
    assert explicit.status == StorageResolutionStatus.RESOLVED
    assert explicit.relative_path == "2024/A - (ID-103) - (KT-1376-GMP)"
    assert missing.status == StorageResolutionStatus.NOT_FOUND


def test_cross_year_resolution_persists_actual_nas_year_and_never_binds_nonresolution(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2024" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        resolved = binding_service.resolve_inspection_folder(
            session, case_id=None, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )
        session.commit()
        bindings = list(session.scalars(select(StorageBinding)))

    assert resolved.binding is not None
    assert bindings[0].year == 2024


def test_cross_year_binding_lookup_rejects_multiple_persisted_year_bindings(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    with build_session() as session:
        for year in (2024, 2025):
            session.add(
                StorageBinding(
                    case_id=None,
                    year=year,
                    site_legacy_id=103,
                    inspection_legacy_code="KT-1376-GMP",
                    relative_path=f"{year}/Folder - (ID-103) - (KT-1376-GMP)",
                    observed_folder_label="Folder",
                    storage_class=service.config.storage_class,
                )
            )
        session.commit()

        result = binding_service.resolve_inspection_folder(
            session, case_id=None, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.AMBIGUOUS
    assert result.binding is None


def test_resolve_dkkd_folder_uses_site_token_match(tmp_path: Path):
    service = build_service(tmp_path)
    (service.dkkd_root / "US Pharma - 12 Street (91)").mkdir(parents=True)

    resolution = service.resolve_dkkd_folder(site_legacy_id=91)

    assert resolution.status == StorageResolutionStatus.RESOLVED
    assert resolution.relative_path == "US Pharma - 12 Street (91)"


def test_storage_io_operations_stay_within_root_and_support_checksum(tmp_path: Path):
    service = build_service(tmp_path)

    service.create_folder("2026/demo")
    written = service.write_stream("2026/demo/test.txt", BytesIO(b"hello world"))

    assert written.relative_path == "2026/demo/test.txt"
    assert service.exists("2026/demo/test.txt") is True
    assert service.stat("2026/demo/test.txt").size == 11
    assert service.checksum("2026/demo/test.txt") == sha256(b"hello world").hexdigest()


def test_storage_copy_move_and_rename_work(tmp_path: Path):
    service = build_service(tmp_path)
    service.write_stream("2026/demo/test.txt", BytesIO(b"abc"))

    copied = service.copy("2026/demo/test.txt", "2026/demo/test-copy.txt")
    moved = service.move("2026/demo/test-copy.txt", "2026/archive/test-copy.txt")
    renamed = service.rename("2026/archive/test-copy.txt", "final.txt")

    assert copied.relative_path == "2026/demo/test-copy.txt"
    assert moved.relative_path == "2026/archive/test-copy.txt"
    assert renamed.relative_path == "2026/archive/final.txt"


def test_storage_rejects_path_traversal(tmp_path: Path):
    service = build_service(tmp_path)

    try:
        service.create_folder("../escape")
    except StorageOperationError as exc:
        assert "Path traversal" in str(exc)
    else:
        raise AssertionError("Expected traversal protection to reject the path.")


def test_resolution_is_logged_to_storage_resolution_log(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2026" / "120 Armephaco - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        result = binding_service.resolve_inspection_folder(
            session,
            case_id=None,
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )
        session.commit()
        log = session.scalars(select(StorageResolutionLog)).one()

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert log.status == StorageResolutionStatus.RESOLVED
    assert log.site_legacy_id == 103
    assert log.inspection_legacy_code == "KT-1376-GMP"


def test_storage_binding_service_persists_storage_binding(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2026" / "120 Armephaco - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    with build_session() as session:
        result = binding_service.resolve_inspection_folder(
            session,
            case_id=case_id,
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )
        session.commit()
        stored = session.scalars(select(StorageBinding)).one()

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.binding is not None
    assert stored.case_id == case_id
    assert stored.year == 2026
    assert stored.site_legacy_id == 103
    assert stored.inspection_legacy_code == "KT-1376-GMP"
    assert stored.relative_path == "2026/120 Armephaco - (ID-103) - (KT-1376-GMP)"
    assert stored.observed_folder_label == "120 Armephaco - (ID-103) - (KT-1376-GMP)"


def test_storage_binding_service_updates_existing_binding_without_duplicate(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2026" / "Folder A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    case_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    with build_session() as session:
        first_result = binding_service.resolve_inspection_folder(
            session,
            case_id=case_id,
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )
        assert first_result.resolution.status == StorageResolutionStatus.RESOLVED
        assert first_result.binding is not None
        session.commit()

        (service.inspection_root / "2026" / "Folder A - (ID-103) - (KT-1376-GMP)").rename(
            service.inspection_root / "2026" / "Folder B - (ID-103) - (KT-1376-GMP)"
        )
    with build_session() as session:
        second_result = binding_service.resolve_inspection_folder(
            session,
            case_id=case_id,
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )
        session.commit()
        bindings = session.scalars(select(StorageBinding)).all()

    assert second_result.resolution.status == StorageResolutionStatus.RESOLVED
    assert second_result.binding is not None
    assert len(bindings) == 1
    assert bindings[0].relative_path == "2026/Folder B - (ID-103) - (KT-1376-GMP)"
    assert bindings[0].observed_folder_label == "Folder B - (ID-103) - (KT-1376-GMP)"


def test_storage_binding_service_does_not_persist_binding_when_resolution_is_not_resolved(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    case_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    with build_session() as session:
        result = binding_service.resolve_inspection_folder(
            session,
            case_id=case_id,
            year=2026,
            site_legacy_id=103,
            inspection_legacy_code="KT-1376-GMP",
        )
        session.commit()
        bindings = session.scalars(select(StorageBinding)).all()

    assert result.resolution.status == StorageResolutionStatus.NOT_FOUND
    assert result.binding is None
    assert bindings == []
