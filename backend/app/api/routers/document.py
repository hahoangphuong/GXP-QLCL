from __future__ import annotations

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
        result = service.render_template_docx(
            session,
            storage=request.app.state.storage_service,
            payload=payload.model_dump(),
            user=user,
        )
        commit_or_409(session)
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

    def open_document_current_content(
        document_id: str,
        request: Request,
        session: Session = dependency,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        require_permissions(user, {"document.read"})
        storage = request.app.state.storage_service
        if storage is None:
            raise HTTPException(status_code=503, detail="StorageService is unavailable for document content access.")
        locator = service.get_current_document_binary_locator(session, document_id)
        stream_context = storage.read_stream(locator.storage_relative_path, root=locator.storage_root)
        stream = stream_context.__enter__()

        def iter_chunks():
            try:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                stream_context.__exit__(None, None, None)

        response = StreamingResponse(iter_chunks(), media_type=locator.media_type)
        response.headers["Content-Disposition"] = (
            f"inline; filename*=UTF-8''{quote(locator.original_filename)}"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

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
        "/documents/{document_id}/content",
        open_document_current_content,
        methods=["GET"],
        tags=["documents"],
    )
