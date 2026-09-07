from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import CaseApplication, StorageBinding, StorageResolutionLog
from backend.app.storage.types import StorageResolution, StorageServiceProtocol


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
    def _submission_year(session: Session, *, case_id: str | None) -> int | None:
        if not case_id:
            return None
        submitted_on = session.scalar(
            select(CaseApplication.submitted_on).where(CaseApplication.case_id == case_id)
        )
        return None if submitted_on is None else submitted_on.year

    def _resolve_submission_window(
        self,
        session: Session,
        *,
        case_id: str | None,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> tuple[StorageResolution, int | None]:
        submission_year = self._submission_year(session, case_id=case_id)
        if submission_year is None:
            return (
                StorageResolution(
                    status=StorageResolutionStatus.INVALID,
                    relative_path=None,
                    absolute_path=None,
                    candidate_count=0,
                    detail="Case application submitted_on is required for bounded inspection folder resolution.",
                ),
                None,
            )

        for lookup_year in (submission_year, submission_year + 1):
            resolution = self.storage.resolve_inspection_folder(
                case_id=case_id,
                year=lookup_year,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
            # A match or ambiguity in the current priority year is authoritative.
            if resolution.status != StorageResolutionStatus.NOT_FOUND:
                return resolution, lookup_year
        return resolution, submission_year + 1

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
        if binding is not None and self.storage.exists(binding.relative_path):
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

        if year is None:
            resolution, lookup_year = self._resolve_submission_window(
                session,
                case_id=case_id,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
        else:
            lookup_year = year
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
