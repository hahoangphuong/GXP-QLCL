from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import StorageBinding, StorageResolutionLog
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

    def _load_bindings_for_identity(
        self,
        session: Session,
        *,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> list[StorageBinding]:
        stmt = select(StorageBinding).where(
            StorageBinding.site_legacy_id == site_legacy_id,
            StorageBinding.inspection_legacy_code == inspection_legacy_code,
        ).order_by(StorageBinding.year.asc())
        return list(session.scalars(stmt))

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
        if year is None:
            candidate_bindings = self._load_bindings_for_identity(
                session,
                site_legacy_id=site_legacy_id,
                inspection_legacy_code=inspection_legacy_code,
            )
            if len(candidate_bindings) > 1:
                resolution = StorageResolution(
                    status=StorageResolutionStatus.AMBIGUOUS,
                    relative_path=None,
                    absolute_path=None,
                    candidate_count=len(candidate_bindings),
                    detail="More than one persisted storage_binding matched the legacy identity tokens.",
                )
                self._persist_resolution_log(
                    session,
                    case_id=case_id,
                    year=None,
                    site_legacy_id=site_legacy_id,
                    inspection_legacy_code=inspection_legacy_code,
                    resolution=resolution,
                )
                return InspectionFolderBindingResult(resolution=resolution, binding=None, source="binding")
            binding = candidate_bindings[0] if candidate_bindings else None
        else:
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

        resolution = self.storage.resolve_inspection_folder(
            case_id=case_id,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )
        self._persist_resolution_log(
            session,
            case_id=case_id,
            year=year if resolution.status != StorageResolutionStatus.RESOLVED else self._resolved_year(resolution),
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
