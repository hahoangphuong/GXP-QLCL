from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState, StorageResolutionStatus
from backend.app.db.models.phase1 import Case, CaseApplication, StorageBinding, StorageResolutionLog
from backend.app.storage.binding_service import StorageBindingService
from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


def build_service(tmp_path: Path) -> LocalStorageService:
    inspection_root = tmp_path / "inspection-root"
    dkkd_root = tmp_path / "dkkd-root"
    inspection_root.mkdir()
    dkkd_root.mkdir()
    return LocalStorageService(StorageConfig(inspection_root=inspection_root, dkkd_root=dkkd_root))


def build_counting_service(tmp_path: Path) -> CountingLocalStorageService:
    inspection_root = tmp_path / "inspection-root"
    dkkd_root = tmp_path / "dkkd-root"
    inspection_root.mkdir()
    dkkd_root.mkdir()
    return CountingLocalStorageService(StorageConfig(inspection_root=inspection_root, dkkd_root=dkkd_root))


def build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


class CountingLocalStorageService(LocalStorageService):
    def __init__(self, config: StorageConfig):
        super().__init__(config)
        self.inspection_lookup_years: list[int | None] = []

    def resolve_inspection_folder(
        self,
        *,
        case_id: str | None = None,
        year: int | None = None,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ):
        self.inspection_lookup_years.append(year)
        return super().resolve_inspection_folder(
            case_id=case_id,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )


def add_case_application(
    session: Session,
    *,
    case_id: str,
    submitted_on: datetime | None,
    opened_year: int | None = None,
) -> None:
    if opened_year is not None:
        session.add(
            Case(
                id=case_id,
                site_id="site-for-storage-test",
                gxp_type="GMP",
                state=CaseState.CERTIFIED,
                opened_year=opened_year,
            )
        )
    session.add(CaseApplication(case_id=case_id, submitted_on=submitted_on))
    session.flush()


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


def test_storage_adapter_rejects_unbounded_cross_year_lookup(tmp_path: Path):
    service = build_service(tmp_path)
    (service.inspection_root / "2025" / "Armephaco - (ID-1) - (KT-1-GMP)").mkdir(parents=True)

    resolution = service.resolve_inspection_folder(site_legacy_id=1, inspection_legacy_code="KT-1-GMP")

    assert resolution.status == StorageResolutionStatus.INVALID
    assert resolution.candidate_count == 0


def test_storage_adapter_keeps_explicit_year_exact_identity_semantics(tmp_path: Path):
    service = build_service(tmp_path)
    (service.inspection_root / "2024" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    (service.inspection_root / "2026" / "B - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    explicit = service.resolve_inspection_folder(year=2024, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert explicit.status == StorageResolutionStatus.RESOLVED
    assert explicit.relative_path == "2024/A - (ID-103) - (KT-1376-GMP)"


def test_submission_year_match_stops_before_next_year_and_persists_actual_nas_year(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    for year in (2020, 2021):
        (service.inspection_root / str(year) / f"Live {year} - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0001"
        add_case_application(session, case_id=case_id, submitted_on=datetime(2020, 12, 31, tzinfo=timezone.utc))
        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )
        session.commit()
        binding = session.scalars(select(StorageBinding)).one()

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.resolution.relative_path == "2020/Live 2020 - (ID-103) - (KT-1376-GMP)"
    assert binding.year == 2020
    assert service.inspection_lookup_years == [2020]


def test_submission_year_miss_falls_back_once_to_next_year(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2021" / "Live - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0002"
        add_case_application(session, case_id=case_id, submitted_on=datetime(2020, 1, 1, tzinfo=timezone.utc))
        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.resolution.relative_path == "2021/Live - (ID-103) - (KT-1376-GMP)"
    assert service.inspection_lookup_years == [2020, 2021]


def test_submission_window_stops_after_two_missing_years(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0003"
        add_case_application(session, case_id=case_id, submitted_on=datetime(2020, 1, 1, tzinfo=timezone.utc))
        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.NOT_FOUND
    assert service.inspection_lookup_years == [2020, 2021]


def test_submission_year_ambiguity_does_not_scan_next_year(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    for label in ("A", "B"):
        (service.inspection_root / "2020" / f"{label} - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0004"
        add_case_application(session, case_id=case_id, submitted_on=datetime(2020, 1, 1, tzinfo=timezone.utc))
        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.AMBIGUOUS
    assert result.binding is None
    assert service.inspection_lookup_years == [2020]


def test_fallback_year_ambiguity_is_fail_closed(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    for label in ("A", "B"):
        (service.inspection_root / "2021" / f"{label} - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0005"
        add_case_application(session, case_id=case_id, submitted_on=datetime(2020, 1, 1, tzinfo=timezone.utc))
        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.AMBIGUOUS
    assert result.binding is None
    assert service.inspection_lookup_years == [2020, 2021]


def test_missing_submitted_on_is_invalid_without_nas_lookup(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0006"
        add_case_application(session, case_id=case_id, submitted_on=None)
        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.INVALID
    assert service.inspection_lookup_years == []


def test_submitted_on_controls_lookup_when_opened_year_disagrees(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2020" / "Live - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0007"
        add_case_application(
            session,
            case_id=case_id,
            submitted_on=datetime(2020, 1, 1, tzinfo=timezone.utc),
            opened_year=2025,
        )
        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert service.inspection_lookup_years == [2020]


def test_stale_binding_cannot_bypass_bounded_live_authority(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    live_folder = service.inspection_root / "2021" / "Live - (ID-103) - (KT-1376-GMP)"
    live_folder.mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0008"
        add_case_application(session, case_id=case_id, submitted_on=datetime(2020, 1, 1, tzinfo=timezone.utc))
        session.add(
            StorageBinding(
                case_id=case_id,
                year=2020,
                site_legacy_id=103,
                inspection_legacy_code="KT-1376-GMP",
                relative_path="2020/Stale - (ID-103) - (KT-1376-GMP)",
                observed_folder_label="Stale",
                storage_class=service.config.storage_class,
            )
        )
        session.commit()

        result = binding_service.resolve_inspection_folder(
            session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.source == "live_resolution"
    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.resolution.relative_path == "2021/Live - (ID-103) - (KT-1376-GMP)"
    assert service.inspection_lookup_years == [2020, 2021]


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
