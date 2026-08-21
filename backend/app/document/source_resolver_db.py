from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import Select, desc, or_, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Document, DocumentVariant, DocumentVersion, TemplateDefinition
from backend.app.document.source_resolver_contract import (
    SourceDocumentCandidate,
    SourceDocumentLookupRequest,
    SourceDocumentResolution,
    resolve_source_document_candidate,
)


class SourceDocumentQueryError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceDocumentCandidateQueryResult:
    request: SourceDocumentLookupRequest
    candidates: tuple[SourceDocumentCandidate, ...]


def _document_parent_filters(lookup_request: SourceDocumentLookupRequest) -> list:
    return [
        Document.case_id == lookup_request.case_id,
        Document.certificate_id == lookup_request.certificate_id,
        Document.business_eligibility_certificate_id == lookup_request.business_eligibility_certificate_id,
        Document.change_request_id == lookup_request.change_request_id,
    ]


def _bookmark_contract_for_family(session: Session, family_code: str) -> tuple[str, ...]:
    stmt: Select[tuple[TemplateDefinition]] = select(TemplateDefinition).where(
        TemplateDefinition.family_code == family_code,
        TemplateDefinition.is_active.is_(True),
    )
    matches = list(session.execute(stmt).scalars())
    if len(matches) > 1:
        raise SourceDocumentQueryError(f"Ambiguous template_definition rows for source family_code={family_code!r}")
    if not matches:
        raise SourceDocumentQueryError(f"Missing template_definition row for source family_code={family_code!r}")
    bookmark_contract = matches[0].bookmark_contract
    if not bookmark_contract:
        return ()
    payload = json.loads(bookmark_contract)
    bookmarks = payload.get("bookmarks", [])
    if not isinstance(bookmarks, list):
        raise SourceDocumentQueryError(f"Invalid bookmark contract for source family_code={family_code!r}")
    return tuple(str(bookmark) for bookmark in bookmarks)


def list_source_document_candidates(
    session: Session,
    lookup_request: SourceDocumentLookupRequest,
) -> SourceDocumentCandidateQueryResult:
    available_bookmarks = _bookmark_contract_for_family(session, lookup_request.family_code)
    stmt: Select[tuple[Document, DocumentVariant, DocumentVersion | None]] = (
        select(Document, DocumentVariant, DocumentVersion)
        .join(DocumentVariant, DocumentVariant.document_id == Document.id)
        .join(DocumentVersion, DocumentVersion.document_variant_id == DocumentVariant.id, isouter=True)
        .where(
            Document.family_code == lookup_request.family_code,
            *_document_parent_filters(lookup_request),
            DocumentVariant.is_active.is_(True),
        )
        .order_by(Document.id, desc(DocumentVersion.is_current), desc(DocumentVersion.version_no))
    )
    candidates: list[SourceDocumentCandidate] = []
    for document, _, document_version in session.execute(stmt).all():
        candidates.append(
            SourceDocumentCandidate(
                document_id=document.id,
                family_code=document.family_code,
                document_version_id=document_version.id if document_version is not None else None,
                available_bookmarks=available_bookmarks,
                is_current_version=bool(document_version.is_current) if document_version is not None else False,
                storage_binding_id=document_version.storage_binding_id if document_version is not None else None,
            )
        )
    return SourceDocumentCandidateQueryResult(request=lookup_request, candidates=tuple(candidates))


def resolve_source_document_from_db(
    session: Session,
    lookup_request: SourceDocumentLookupRequest,
) -> SourceDocumentResolution:
    query_result = list_source_document_candidates(session, lookup_request)
    return resolve_source_document_candidate(lookup_request, query_result.candidates)
