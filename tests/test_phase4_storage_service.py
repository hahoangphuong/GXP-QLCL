from __future__ import annotations

from hashlib import sha256
import inspect
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import LegacyInspectionStorageAnchor, StorageBinding, StorageResolutionLog
from backend.app.storage.binding_service import StorageBindingService
from backend.app.storage.local import LocalStorageService
from backend.app.storage.types import StorageConfig, StorageOperationError


def build_service(tmp_path: Path) -> LocalStorageService:
    inspection_root = tmp_path / "inspection-root"
    dkkd_root = tmp_path / "dkkd-root"
    inspection_root.mkdir()
    dkkd_root.mkdir()
    return LocalStorageService(StorageConfig(inspection_root=inspection_root, dkkd_root=dkkd_root))


class CountingLocalStorageService(LocalStorageService):
    def __init__(self, config: StorageConfig):
        super().__init__(config)
        self.lookup_years: list[int | None] = []

    def resolve_inspection_folder(self, *, case_id=None, year=None, site_legacy_id, inspection_legacy_code):
        self.lookup_years.append(year)
        return super().resolve_inspection_folder(
            case_id=case_id,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )


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


def add_anchor(
    session: Session,
    *,
    case_id: str,
    registration_status: str = "usable",
    registration_year: int | None = 2024,
    inspection_status: str = "unavailable",
    inspection_year: int | None = None,
) -> None:
    session.add(
        LegacyInspectionStorageAnchor(
            case_id=case_id,
            source_sheet="db.ktra",
            source_row=5,
            registration_submission_raw="2024-01-01" if registration_year else "-",
            registration_submission_year=registration_year,
            registration_submission_status=registration_status,
            inspection_date_raw=str(inspection_year or "-"),
            inspection_year=inspection_year,
            inspection_year_status=inspection_status,
            source_hash="a" * 64,
            source_version="b" * 64,
        )
    )
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


def test_resolve_inspection_folder_requires_explicit_year(tmp_path: Path):
    service = build_service(tmp_path)
    resolved = service.inspection_root / "2025" / "Armephaco - (id-1) - (kt-1-gmp)"
    resolved.mkdir(parents=True)
    (service.inspection_root / "2026" / "Wrong site - (ID-10) - (KT-1-GMP)").mkdir(parents=True)
    (service.inspection_root / "2026" / "Wrong inspection - (ID-1) - (KT-10-GMP)").mkdir(parents=True)
    (service.inspection_root / "Templates" / "Ignored - (ID-1) - (KT-1-GMP)").mkdir(parents=True)
    (service.inspection_root / "2027" / "Legacy - (1) - (KT-1-GMP)").mkdir(parents=True)

    resolution = service.resolve_inspection_folder(year=None, site_legacy_id=1, inspection_legacy_code="KT-1-GMP")

    assert resolution.status == StorageResolutionStatus.INVALID
    assert resolution.candidate_count == 0


def test_resolve_inspection_folder_requires_explicit_year_for_duplicate_namespace(tmp_path: Path):
    service = build_service(tmp_path)
    (service.inspection_root / "2024" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    (service.inspection_root / "2026" / "B - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    duplicate = service.resolve_inspection_folder(year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
    explicit = service.resolve_inspection_folder(year=2024, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
    missing = service.resolve_inspection_folder(year=2024, site_legacy_id=103, inspection_legacy_code="KT-999-GMP")

    assert duplicate.status == StorageResolutionStatus.INVALID
    assert duplicate.candidate_count == 0
    assert explicit.status == StorageResolutionStatus.RESOLVED
    assert explicit.relative_path == "2024/A - (ID-103) - (KT-1376-GMP)"
    assert missing.status == StorageResolutionStatus.NOT_FOUND


def test_anchor_registration_year_wins_and_resolved_uses_one_storage_call(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2024" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0001"
        add_anchor(session, case_id=case_id, registration_year=2024, inspection_year=2025, inspection_status="usable")
        resolved = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
        session.commit()
        bindings = list(session.scalars(select(StorageBinding)))

    assert resolved.resolution.status == StorageResolutionStatus.RESOLVED
    assert resolved.binding is not None
    assert bindings[0].year == 2024
    assert service.lookup_years == [2024]


def test_anchor_registration_unavailable_falls_back_to_inspection_year(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2025" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)

    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0002"
        add_anchor(session, case_id=case_id, registration_status="unavailable", registration_year=None, inspection_status="usable", inspection_year=2025)
        result = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.resolution.relative_path == "2025/A - (ID-103) - (KT-1376-GMP)"
    assert service.lookup_years == [2025]


def test_storage_binding_resolver_has_no_date_or_anchor_projection_dependency():
    source = inspect.getsource(StorageBindingService)

    assert "CaseApplication" not in source
    assert "InspectionOutcome" not in source
    assert "LegacyInspectionStorageAnchor" in source
    assert "CaseApplication" not in source


def test_anchor_not_found_then_next_year_resolves_and_uses_two_calls(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2025" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0003"
        add_anchor(session, case_id=case_id, registration_year=2024)
        result = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
        binding = session.scalars(select(StorageBinding)).one()

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.resolution.relative_path.startswith("2025/")
    assert binding.year == 2025
    assert service.lookup_years == [2024, 2025]


def test_anchor_not_found_twice_creates_no_binding(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0004"
        add_anchor(session, case_id=case_id, registration_year=2024)
        result = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
        assert session.scalars(select(StorageBinding)).all() == []

    assert result.resolution.status == StorageResolutionStatus.NOT_FOUND
    assert service.lookup_years == [2024, 2025]


def test_anchor_ambiguous_stops_without_next_year_or_binding(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    for label in ("A", "B"):
        (service.inspection_root / "2024" / f"{label} - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0005"
        add_anchor(session, case_id=case_id, registration_year=2024)
        result = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
        assert session.scalars(select(StorageBinding)).all() == []

    assert result.resolution.status == StorageResolutionStatus.AMBIGUOUS
    assert service.lookup_years == [2024]


def test_anchor_unusable_returns_invalid_without_storage_call_or_binding(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0006"
        add_anchor(session, case_id=case_id, registration_status="conflict", registration_year=None, inspection_status="conflict")
        result = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")
        assert session.scalars(select(StorageBinding)).all() == []

    assert result.resolution.status == StorageResolutionStatus.INVALID
    assert service.lookup_years == []


def test_missing_anchor_returns_invalid_without_storage_call(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    with build_session() as session:
        result = binding_service.resolve_inspection_folder(
            session, case_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0009", year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP"
        )

    assert result.resolution.status == StorageResolutionStatus.INVALID
    assert service.lookup_years == []


def test_registration_conflict_uses_usable_inspection_fallback(tmp_path: Path):
    service = build_counting_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2025" / "A - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0010"
        add_anchor(session, case_id=case_id, registration_status="conflict", registration_year=None, inspection_status="usable", inspection_year=2025)
        result = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert service.lookup_years == [2025]


def test_stale_binding_cannot_bypass_anchor_bounded_lookup(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    (service.inspection_root / "2025" / "Live - (ID-103) - (KT-1376-GMP)").mkdir(parents=True)
    with build_session() as session:
        case_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0007"
        add_anchor(session, case_id=case_id, registration_year=2024)
        session.add(StorageBinding(case_id=case_id, year=2024, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP", relative_path="2024/Stale - (ID-103) - (KT-1376-GMP)", observed_folder_label="Stale", storage_class=service.config.storage_class))
        session.commit()
        result = binding_service.resolve_inspection_folder(session, case_id=case_id, year=None, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert result.source == "live_resolution"
    assert result.resolution.status == StorageResolutionStatus.RESOLVED
    assert result.resolution.relative_path.startswith("2025/")


def test_explicit_year_binding_fast_path_is_unchanged(tmp_path: Path):
    service = build_service(tmp_path)
    binding_service = StorageBindingService(service)
    folder = service.inspection_root / "2024" / "Live - (ID-103) - (KT-1376-GMP)"
    folder.mkdir(parents=True)
    with build_session() as session:
        binding = StorageBinding(case_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0008", year=2024, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP", relative_path="2024/Live - (ID-103) - (KT-1376-GMP)", observed_folder_label=folder.name, storage_class=service.config.storage_class)
        session.add(binding)
        session.commit()
        result = binding_service.resolve_inspection_folder(session, case_id=binding.case_id, year=2024, site_legacy_id=103, inspection_legacy_code="KT-1376-GMP")

    assert result.source == "binding"
    assert result.resolution.status == StorageResolutionStatus.RESOLVED


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
