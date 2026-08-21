from __future__ import annotations

from dataclasses import dataclass

from backend.app.document.service_contract import DocumentGenerationPlan, SourceDependencyPlan


class SourceDocumentResolutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceDocumentLookupRequest:
    family_code: str
    required_bookmarks: tuple[str, ...]
    dependency_type: str
    case_id: str | None = None
    certificate_id: str | None = None
    business_eligibility_certificate_id: str | None = None
    change_request_id: str | None = None
    prefer_current_version: bool = True


@dataclass(frozen=True)
class SourceDocumentCandidate:
    document_id: str
    family_code: str
    document_version_id: str | None
    available_bookmarks: tuple[str, ...]
    is_current_version: bool
    storage_binding_id: str | None = None


@dataclass(frozen=True)
class SourceDocumentResolution:
    request: SourceDocumentLookupRequest
    candidate: SourceDocumentCandidate


def build_source_lookup_requests(plan: DocumentGenerationPlan) -> tuple[SourceDocumentLookupRequest, ...]:
    requests = []
    for dependency in plan.source_dependencies:
        requests.append(
            SourceDocumentLookupRequest(
                family_code=dependency.source_family_code,
                required_bookmarks=dependency.required_bookmarks,
                dependency_type=dependency.dependency_type,
                case_id=plan.request.case_id,
                certificate_id=plan.request.certificate_id,
                business_eligibility_certificate_id=plan.request.business_eligibility_certificate_id,
                change_request_id=plan.request.change_request_id,
            )
        )
    return tuple(requests)


def resolve_source_document_candidate(
    lookup_request: SourceDocumentLookupRequest,
    candidates: tuple[SourceDocumentCandidate, ...],
) -> SourceDocumentResolution:
    matching = []
    required = set(lookup_request.required_bookmarks)
    for candidate in candidates:
        if candidate.family_code != lookup_request.family_code:
            continue
        if not required.issubset(set(candidate.available_bookmarks)):
            continue
        if lookup_request.prefer_current_version and not candidate.is_current_version:
            continue
        matching.append(candidate)
    if not matching:
        raise SourceDocumentResolutionError(
            f"No source document candidate matched family_code={lookup_request.family_code!r}"
        )
    if len(matching) > 1:
        raise SourceDocumentResolutionError(
            f"Ambiguous source document resolution for family_code={lookup_request.family_code!r}"
        )
    return SourceDocumentResolution(request=lookup_request, candidate=matching[0])
