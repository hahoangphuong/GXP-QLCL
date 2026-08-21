from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.project_paths import phase_artifact_path
from backend.app.document.registry import CopyForwardDependency, TemplateRegistryEntry, load_curated_registry


class DocumentTemplateSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class DocumentGenerationRequest:
    family_code: str
    requested_by_user_id: str | None
    case_id: str | None = None
    capa_cycle_id: str | None = None
    certificate_id: str | None = None
    business_eligibility_certificate_id: str | None = None
    change_request_id: str | None = None
    gxp_type: str | None = None
    legacy_mode: str | None = None
    storage_scope: str | None = None
    language_code: str = "vi"
    idempotency_key: str | None = None
    payload: dict[str, str] | None = None


@dataclass(frozen=True)
class DocumentPayloadField:
    field_name: str
    value: str
    source: str
    is_sensitive: bool = False


@dataclass(frozen=True)
class DocumentPayloadEnvelope:
    family_code: str
    fields: tuple[DocumentPayloadField, ...]
    source_procedures: tuple[str, ...]
    notes: str | None = None

    def redacted_payload(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        for field in self.fields:
            payload[field.field_name] = "<redacted>" if field.is_sensitive else field.value
        return payload


@dataclass(frozen=True)
class TemplateSelectionInput:
    family_code: str
    gxp_type: str | None = None
    legacy_mode: str | None = None
    storage_scope: str | None = None
    source_application: str | None = None


@dataclass(frozen=True)
class TemplateSelectionResult:
    family_code: str
    logical_name: str
    template_pattern: str
    source_application: str
    storage_scope: str
    host_procedure: str
    population_procedures: tuple[str, ...]
    bookmarks: tuple[str, ...]
    copy_forward_dependencies: tuple[CopyForwardDependency, ...]
    notes: str | None = None


@dataclass(frozen=True)
class SourceDependencyPlan:
    source_family_code: str
    dependency_type: str
    required_bookmarks: tuple[str, ...]
    condition: str


@dataclass(frozen=True)
class DocumentGenerationPlan:
    request: DocumentGenerationRequest
    template: TemplateSelectionResult
    payload: DocumentPayloadEnvelope
    source_dependencies: tuple[SourceDependencyPlan, ...]


def _matches_optional_filter(candidate: str | None, requested: str | None) -> bool:
    if requested is None:
        return True
    return candidate == requested


def _entry_matches(entry: TemplateRegistryEntry, selector: TemplateSelectionInput) -> bool:
    if entry.family_code != selector.family_code:
        return False
    if not _matches_optional_filter(entry.storage_scope, selector.storage_scope):
        return False
    if not _matches_optional_filter(entry.source_application, selector.source_application):
        return False
    if selector.gxp_type is not None and selector.gxp_type not in entry.template_pattern:
        return False
    if selector.legacy_mode is not None and entry.selection_legacy_mode != selector.legacy_mode:
        return False
    return True


def select_template_entry(
    registry_entries: tuple[TemplateRegistryEntry, ...],
    selector: TemplateSelectionInput,
) -> TemplateSelectionResult:
    matches = [entry for entry in registry_entries if _entry_matches(entry, selector)]
    if not matches:
        raise DocumentTemplateSelectionError(
            f"No template registry entry matched family_code={selector.family_code!r}"
        )
    if len(matches) > 1:
        raise DocumentTemplateSelectionError(
            f"Ambiguous template registry selection for family_code={selector.family_code!r}: "
            f"{', '.join(entry.logical_name for entry in matches)}"
        )
    entry = matches[0]
    return TemplateSelectionResult(
        family_code=entry.family_code,
        logical_name=entry.logical_name,
        template_pattern=entry.template_pattern,
        source_application=entry.source_application,
        storage_scope=entry.storage_scope,
        host_procedure=entry.legacy_host_procedure,
        population_procedures=entry.population_procedures,
        bookmarks=entry.bookmarks,
        copy_forward_dependencies=entry.copy_forward_dependencies,
        notes=entry.notes,
    )


def build_dependency_plan(template: TemplateSelectionResult) -> tuple[SourceDependencyPlan, ...]:
    plans = [
        SourceDependencyPlan(
            source_family_code=dependency.source_family_code,
            dependency_type="copy_forward",
            required_bookmarks=dependency.source_bookmarks,
            condition=dependency.condition,
        )
        for dependency in template.copy_forward_dependencies
    ]
    return tuple(plans)


def plan_document_generation(
    registry_entries: tuple[TemplateRegistryEntry, ...],
    request: DocumentGenerationRequest,
    payload: DocumentPayloadEnvelope,
) -> DocumentGenerationPlan:
    template = select_template_entry(
        registry_entries,
        TemplateSelectionInput(
            family_code=request.family_code,
            gxp_type=request.gxp_type,
            legacy_mode=request.legacy_mode,
            storage_scope=request.storage_scope,
        ),
    )
    return DocumentGenerationPlan(
        request=request,
        template=template,
        payload=payload,
        source_dependencies=build_dependency_plan(template),
    )


def load_default_registry() -> tuple[TemplateRegistryEntry, ...]:
    return load_curated_registry(phase_artifact_path("phase5", "template_registry.curated.json"))
