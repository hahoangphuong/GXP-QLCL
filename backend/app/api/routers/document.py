from __future__ import annotations

from hashlib import sha256
import tempfile
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.session import commit_or_409, get_session_from_request_factory
from backend.app.auth import AuthenticatedUser, get_authenticated_user, require_permissions, require_role
from backend.app.read_models import (
    DocumentDetailRead,
    DocumentGenerationPrepareRequest,
    DocumentGenerationRunStatusRead,
    DocumentPreparationRead,
    DocumentRenderRead,
    DocumentTemplateRenderRequest,
)
from backend.app.services.document_api import DocumentWorkflowService
from backend.app.storage.types import StorageOperationError

def register_document_routes(app, session_factory) -> None:
    dependency = Depends(get_session_from_request_factory(session_factory))
    service = DocumentWorkflowService()

    def prepare_document_generation(
        payload: DocumentGenerationPrepareRequest,
        request: Request,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.write"})
        result = service.prepare_generation(
            session,
            storage=request.app.state.storage_service,
            payload=payload.model_dump(),
            user=user,
        )
        commit_or_409(session)
        return DocumentPreparationRead(**result)

    def render_template_docx(
        payload: DocumentTemplateRenderRequest,
        request: Request,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.write"})
        storage = request.app.state.storage_service
        result = service.render_template_docx(
            session,
            storage=storage,
            payload=payload.model_dump(),
            user=user,
        )
        try:
            commit_or_409(session)
        except Exception as exc:
            if storage is not None:
                cleanup_error = service.cleanup_render_output_after_commit_failure(
                    storage,
                    result,
                )
                if cleanup_error is not None:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Document DB commit failed and output cleanup also failed: "
                            + cleanup_error
                        ),
                    ) from exc
            raise
        result.pop("_rollback_cleanup_required", None)
        return DocumentRenderRead(**result)

    def get_document_generation_run(
        generation_run_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.read"})
        result = service.get_generation_run(session, generation_run_id)
        return DocumentGenerationRunStatusRead(**result)

    def get_document_detail(
        document_id: str,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.read"})
        result = service.get_document(session, document_id)
        return DocumentDetailRead(**result)

    def _open_document_current_content(
        *,
        locator,
        request: Request,
    ):
        storage = request.app.state.storage_service
        if storage is None:
            raise HTTPException(status_code=503, detail="StorageService is unavailable for document content access.")
        verified_stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        try:
            if not storage.exists(
                locator.storage_relative_path,
                root=locator.storage_root,
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Document current binary is missing from storage.",
                )
            digest = sha256()
            with storage.read_stream(
                locator.storage_relative_path,
                root=locator.storage_root,
            ) as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    verified_stream.write(chunk)
            if digest.hexdigest() != locator.checksum_sha256:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Document current binary checksum does not match the "
                        "persisted document version."
                    ),
                )
            verified_stream.seek(0)
        except HTTPException:
            verified_stream.close()
            raise
        except FileNotFoundError as exc:
            verified_stream.close()
            raise HTTPException(
                status_code=409,
                detail="Document current binary is missing from storage.",
            ) from exc
        except StorageOperationError as exc:
            verified_stream.close()
            raise HTTPException(
                status_code=503,
                detail="StorageService failed while opening document content.",
            ) from exc
        except Exception:
            verified_stream.close()
            raise

        def iter_chunks():
            try:
                while True:
                    chunk = verified_stream.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                verified_stream.close()

        response = StreamingResponse(iter_chunks(), media_type=locator.media_type)
        response.headers["Content-Disposition"] = (
            f"inline; filename*=UTF-8''{quote(locator.original_filename)}"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def open_case_document_current_content(
        case_id: str,
        document_id: str,
        request: Request,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.read"})
        locator = service.get_current_document_binary_locator_for_parent(
            session,
            document_id=document_id,
            expected_parent_scope="case",
            expected_parent_id=case_id,
        )
        return _open_document_current_content(locator=locator, request=request)

    def open_capa_cycle_document_current_content(
        case_id: str,
        capa_cycle_id: str,
        document_id: str,
        request: Request,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.read"})
        locator = service.get_current_document_binary_locator_for_parent(
            session,
            document_id=document_id,
            expected_parent_scope="capa_cycle",
            expected_parent_id=capa_cycle_id,
            expected_case_id=case_id,
        )
        return _open_document_current_content(locator=locator, request=request)

    app.add_api_route(
        "/documents/prepare",
        prepare_document_generation,
        methods=["POST"],
        response_model=DocumentPreparationRead,
        tags=["documents"],
    )
    app.add_api_route(
        "/documents/render-template-docx",
        render_template_docx,
        methods=["POST"],
        response_model=DocumentRenderRead,
        tags=["documents"],
    )
    app.add_api_route(
        "/document-generation-runs/{generation_run_id}",
        get_document_generation_run,
        methods=["GET"],
        response_model=DocumentGenerationRunStatusRead,
        tags=["documents"],
    )
    app.add_api_route(
        "/documents/{document_id}",
        get_document_detail,
        methods=["GET"],
        response_model=DocumentDetailRead,
        tags=["documents"],
    )
    app.add_api_route(
        "/cases/{case_id}/documents/{document_id}/content",
        open_case_document_current_content,
        methods=["GET"],
        tags=["documents"],
    )
    app.add_api_route(
        "/cases/{case_id}/capa-cycles/{capa_cycle_id}/documents/{document_id}/content",
        open_capa_cycle_document_current_content,
        methods=["GET"],
        tags=["documents"],
    )
