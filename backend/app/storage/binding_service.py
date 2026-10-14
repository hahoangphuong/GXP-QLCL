from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import LegacyInspectionStorageAnchor, StorageBinding, StorageResolutionLog
from backend.app.storage.types import (
    StorageResolution,
    StorageServiceProtocol,
    matches_inspection_identity,
)


@dataclass(frozen=True)
class InspectionFolderBindingResult:
    resolution: StorageResolution
    binding: StorageBinding | None
    source: str


class StorageBindingService:
    def __init__(self, storage: StorageServiceProtocol):
        self.storage = storage

    def _persist_resolution_log(
        self,
        session: Session,
        *,
        case_id: str | None,
        year: int | None,
        site_legacy_id: int | None,
        inspection_legacy_code: str | None,
        resolution: StorageResolution,
    ) -> None:
        session.add(
            StorageResolutionLog(
                case_id=case_id,
                year=year,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
                status=resolution.status,
                candidate_count=resolution.candidate_count,
                resolved_relative_path=resolution.relative_path,
                detail=resolution.detail,
            )
        )
        session.flush()

    def _load_binding(
        self,
        session: Session,
        *,
        year: int,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> StorageBinding | None:
        stmt = select(StorageBinding).where(
            StorageBinding.year == year,
            StorageBinding.site_legacy_id == site_legacy_id,
            StorageBinding.inspection_legacy_code == inspection_legacy_code,
        )
        return session.scalars(stmt).one_or_none()

    @staticmethod
    def _load_storage_anchor(session: Session, *, case_id: str | None) -> LegacyInspectionStorageAnchor | None:
        if not case_id:
            return None
        stmt = select(LegacyInspectionStorageAnchor).where(LegacyInspectionStorageAnchor.case_id == case_id)
        return session.scalars(stmt).one_or_none()

    @staticmethod
    def _anchor_years(anchor: LegacyInspectionStorageAnchor | None) -> tuple[int, ...]:
        """Use only source-recorded submission/inspection years, never year+1.

        A conflicting or malformed original year must not be silently rescued
        by another source column. Preserve registration-first lookup order;
        cross-year result selection is handled separately and fail-closed.
        """
        if anchor is None:
            return ()
        years: list[int] = []
        for status, value in (
            (anchor.registration_submission_status, anchor.registration_submission_year),
            (anchor.inspection_year_status, anchor.inspection_year),
        ):
            if status == "conflict":
                return ()
            if status == "unavailable":
                if value is not None:
                    return ()
                continue
            if status != "usable" or type(value) is not int or not 1900 <= value <= 2100:
                return ()
            if value not in years:
                years.append(value)
        return tuple(years)

    @staticmethod
    def _invalid_anchor_resolution() -> StorageResolution:
        return StorageResolution(
            status=StorageResolutionStatus.INVALID,
            relative_path=None,
            absolute_path=None,
            candidate_count=0,
            detail="A usable legacy inspection storage anchor is required for automatic folder resolution.",
        )

    @staticmethod
    def _resolved_year(resolution: StorageResolution) -> int:
        if resolution.relative_path is None:
            raise RuntimeError("Resolved inspection folder is missing relative_path.")
        first_component = resolution.relative_path.replace("\\", "/").split("/", 1)[0]
        if len(first_component) != 4 or not first_component.isascii() or not first_component.isdigit():
            raise RuntimeError("Resolved inspection folder must begin with a four-digit NAS year.")
        return int(first_component)

    def _upsert_binding(
        self,
        session: Session,
        *,
        case_id: str | None,
        year: int,
        site_legacy_id: int,
        inspection_legacy_code: str,
        resolution: StorageResolution,
    ) -> StorageBinding:
        if resolution.relative_path is None:
            raise RuntimeError("Resolved inspection folder is missing relative_path.")
        binding = self._load_binding(
            session,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )
        observed_folder_label = Path(resolution.relative_path).name
        if binding is None:
            binding = StorageBinding(
                case_id=case_id,
                year=year,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
                relative_path=resolution.relative_path,
                observed_folder_label=observed_folder_label,
                storage_class=self.storage.config.storage_class,
            )
            session.add(binding)
        else:
            binding.case_id = case_id or binding.case_id
            binding.relative_path = resolution.relative_path
            binding.observed_folder_label = observed_folder_label
            binding.storage_class = self.storage.config.storage_class
        session.flush()
        return binding

    def _persisted_binding_folder_is_eligible(
        self,
        binding: StorageBinding,
        *,
        year: int,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> bool:
        # A persisted path is a cache of a physical identity resolution, not
        # proof that a still-existing path has retained the same identity.
        # Live inspection resolution searches exactly one folder below year.
        parts = binding.relative_path.replace("\\", "/").split("/")
        if (
            len(parts) != 2
            or parts[0] != str(year)
            or not matches_inspection_identity(
                parts[1],
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
        ):
            return False
        try:
            entry = self.storage.stat(binding.relative_path, root="inspection")
        except (FileNotFoundError, NotADirectoryError):
            return False
        return entry.is_dir

    def resolve_inspection_folder(
        self,
        session: Session,
        *,
        case_id: str | None,
        year: int | None = None,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> InspectionFolderBindingResult:
        binding = None
        if year is not None:
            binding = self._load_binding(
                session,
                year=year,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
        if (
            binding is not None
            and year is not None
            and self._persisted_binding_folder_is_eligible(
                binding,
                year=year,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
        ):
            resolution = StorageResolution(
                status=StorageResolutionStatus.RESOLVED,
                relative_path=binding.relative_path,
                absolute_path=None,
                candidate_count=1,
                detail="Resolved from persisted storage_binding.",
            )
            self._persist_resolution_log(
                session,
                case_id=case_id,
                year=binding.year,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
                resolution=resolution,
            )
            return InspectionFolderBindingResult(
                resolution=resolution,
                binding=binding,
                source="binding",
            )

        lookup_year = year
        if year is None:
            source_years = self._anchor_years(
                self._load_storage_anchor(session, case_id=case_id)
            )
            lookup_year = source_years[0] if len(source_years) == 1 else None
            if not source_years:
                resolution = self._invalid_anchor_resolution()
            else:
                observed = [
                    self.storage.resolve_inspection_folder(
                        case_id=case_id,
                        year=source_year,
                        site_legacy_id=site_legacy_id,
                        inspection_legacy_code=inspection_legacy_code,
                    )
                    for source_year in source_years
                ]
                resolved = [
                    item for item in observed
                    if item.status == StorageResolutionStatus.RESOLVED
                ]
                if any(item.status == StorageResolutionStatus.INVALID for item in observed):
                    resolution = self._invalid_anchor_resolution()
                elif (
                    any(item.status == StorageResolutionStatus.AMBIGUOUS for item in observed)
                    or len(resolved) > 1
                ):
                    resolution = StorageResolution(
                        status=StorageResolutionStatus.AMBIGUOUS,
                        relative_path=None,
                        absolute_path=None,
                        candidate_count=sum(item.candidate_count for item in observed),
                        detail="Multiple source-year inspection folder candidates.",
                    )
                elif len(resolved) == 1:
                    resolution = resolved[0]
                else:
                    resolution = StorageResolution(
                        status=StorageResolutionStatus.NOT_FOUND,
                        relative_path=None,
                        absolute_path=None,
                        candidate_count=0,
                        detail="No inspection folder matched either recorded source year.",
                    )
        else:
            resolution = self.storage.resolve_inspection_folder(
                case_id=case_id,
                year=year,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
        self._persist_resolution_log(
            session,
            case_id=case_id,
            year=lookup_year if resolution.status != StorageResolutionStatus.RESOLVED else self._resolved_year(resolution),
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
            resolution=resolution,
        )
        refreshed_binding: StorageBinding | None = None
        if resolution.status == StorageResolutionStatus.RESOLVED:
            try:
                with session.begin_nested():
                    refreshed_binding = self._upsert_binding(
                        session,
                        case_id=case_id,
                        year=year if year is not None else self._resolved_year(resolution),
                        site_legacy_id=site_legacy_id,
                        inspection_legacy_code=inspection_legacy_code,
                        resolution=resolution,
                    )
            except IntegrityError:
                refreshed_binding = self._load_binding(
                    session,
                    year=year if year is not None else self._resolved_year(resolution),
                    site_legacy_id=site_legacy_id,
                    inspection_legacy_code=inspection_legacy_code,
                )
                if refreshed_binding is None:
                    raise
        return InspectionFolderBindingResult(
            resolution=resolution,
            binding=refreshed_binding,
            source="live_resolution",
        )
