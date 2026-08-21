from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.db.enums import StorageResolutionStatus
from backend.app.db.models.phase1 import StorageBinding
from backend.app.storage.binding_service import StorageBindingService
from backend.app.storage.types import StorageResolution, StorageServiceProtocol


@dataclass(frozen=True)
class InspectionFolderLookup:
    resolution: StorageResolution
    binding: StorageBinding | None
    source: str


@dataclass(frozen=True)
class DkkdFolderLookup:
    resolution: StorageResolution
    source: str


class StorageBindingLookupService:
    def __init__(self, storage: StorageServiceProtocol):
        self.storage = storage
        self.binding_service = StorageBindingService(storage)

    def get_inspection_folder(
        self,
        session: Session,
        *,
        case_id: str | None,
        year: int,
        site_legacy_id: int,
        inspection_legacy_code: str,
    ) -> InspectionFolderLookup:
        result = self.binding_service.resolve_inspection_folder(
            session,
            case_id=case_id,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )
        return InspectionFolderLookup(
            resolution=result.resolution,
            binding=result.binding,
            source=result.source,
        )

    def get_dkkd_folder(
        self,
        session: Session,
        *,
        case_id: str | None,
        site_legacy_id: int,
    ) -> DkkdFolderLookup:
        resolution = self.storage.resolve_dkkd_folder(
            case_id=case_id,
            site_legacy_id=site_legacy_id,
        )
        return DkkdFolderLookup(
            resolution=resolution,
            source="live_resolution",
        )
