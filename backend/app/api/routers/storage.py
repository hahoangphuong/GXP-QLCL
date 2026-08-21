from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.api.session import get_session_from_request_factory
from backend.app.auth import AuthenticatedUser, get_authenticated_user, require_permissions
from backend.app.read_models import (
    DkkdFolderLookupRead,
    InspectionFolderLookupRead,
    StorageBindingRead,
)
from backend.app.storage import StorageBindingLookupService

def get_storage_lookup_service(request: Request) -> StorageBindingLookupService:
    service = getattr(request.app.state, "storage_lookup_service", None)
    if service is None:
        detail = getattr(request.app.state, "storage_error", None) or "Storage service is not configured."
        raise HTTPException(status_code=503, detail=detail)
    return service

def register_storage_routes(app, session_factory) -> None:
    session_dependency = Depends(get_session_from_request_factory(session_factory))

    def lookup_inspection_folder(
        year: int = Query(..., gt=0),
        site_legacy_id: int = Query(..., gt=0),
        inspection_legacy_code: str = Query(..., min_length=1),
        case_id: str | None = Query(default=None),
        session: Session = session_dependency,
        lookup_service: StorageBindingLookupService = Depends(get_storage_lookup_service),
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.read"})
        result = lookup_service.get_inspection_folder(
            session,
            case_id=case_id,
            year=year,
            site_legacy_id=site_legacy_id,
            inspection_legacy_code=inspection_legacy_code,
        )
        binding = result.binding
        return InspectionFolderLookupRead(
            status=result.resolution.status.value,
            source=result.source,
            relative_path=result.resolution.relative_path,
            candidate_count=result.resolution.candidate_count,
            detail=result.resolution.detail,
            storage_class=lookup_service.storage.config.storage_class,
            binding=(
                None
                if binding is None
                else StorageBindingRead(
                    case_id=binding.case_id,
                    year=binding.year,
                    site_legacy_id=binding.site_legacy_id,
                    inspection_legacy_code=binding.inspection_legacy_code,
                    relative_path=binding.relative_path,
                    observed_folder_label=binding.observed_folder_label,
                    storage_class=binding.storage_class,
                )
            ),
        )

    def lookup_dkkd_folder(
        site_legacy_id: int = Query(..., gt=0),
        case_id: str | None = Query(default=None),
        session: Session = session_dependency,
        lookup_service: StorageBindingLookupService = Depends(get_storage_lookup_service),
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.read"})
        result = lookup_service.get_dkkd_folder(
            session,
            case_id=case_id,
            site_legacy_id=site_legacy_id,
        )
        return DkkdFolderLookupRead(
            status=result.resolution.status.value,
            source=result.source,
            relative_path=result.resolution.relative_path,
            candidate_count=result.resolution.candidate_count,
            detail=result.resolution.detail,
            storage_class=lookup_service.storage.config.storage_class,
        )

    app.add_api_route(
        "/storage/inspection-folder",
        lookup_inspection_folder,
        methods=["GET"],
        response_model=InspectionFolderLookupRead,
        tags=["storage"],
    )
    app.add_api_route(
        "/storage/dkkd-folder",
        lookup_dkkd_folder,
        methods=["GET"],
        response_model=DkkdFolderLookupRead,
        tags=["storage"],
    )
