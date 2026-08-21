from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import DocumentVersion, StorageBinding, TemplateDefinition
from backend.app.document.source_resolver_contract import SourceDocumentResolution


class SourceBinaryContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceBinaryRequirement:
    source_document_id: str
    source_document_version_id: str | None
    source_family_code: str
    storage_binding_id: str | None
    storage_root: str | None
    folder_relative_path: str | None
    exact_storage_root: str | None
    exact_storage_relative_path: str | None
    original_filename: str | None
    required_bookmarks: tuple[str, ...]
    legacy_filename_prefix_hints: tuple[str, ...]
    readiness_status: str
    detail: str


def _storage_root_for_scope(storage_scope: str) -> str | None:
    if storage_scope == "inspection_folder":
        return "inspection"
    if storage_scope == "dkkd_folder":
        return "dkkd"
    return None


def _prefix_hints_for_family(family_code: str) -> tuple[str, ...]:
    prefix_hints = {
        "INSPECTION_BB_KT": ("4.",),
        "INSPECTION_CAPA_LAN_1": ("5.1.",),
        "INSPECTION_PT_PCT": ("6.",),
    }
    return prefix_hints.get(family_code, ())


def _active_template_definition(session: Session, family_code: str) -> TemplateDefinition:
    stmt: Select[tuple[TemplateDefinition]] = select(TemplateDefinition).where(
        TemplateDefinition.family_code == family_code,
        TemplateDefinition.is_active.is_(True),
    )
    matches = list(session.execute(stmt).scalars())
    if len(matches) > 1:
        raise SourceBinaryContractError(f"Ambiguous active template_definition rows for family_code={family_code!r}")
    if not matches:
        raise SourceBinaryContractError(f"Missing active template_definition row for family_code={family_code!r}")
    return matches[0]


def _storage_binding(session: Session, storage_binding_id: str | None) -> StorageBinding | None:
    if storage_binding_id is None:
        return None
    stmt: Select[tuple[StorageBinding]] = select(StorageBinding).where(StorageBinding.id == storage_binding_id)
    return session.execute(stmt).scalar_one_or_none()


def _document_version(session: Session, document_version_id: str | None) -> DocumentVersion | None:
    if document_version_id is None:
        return None
    stmt: Select[tuple[DocumentVersion]] = select(DocumentVersion).where(DocumentVersion.id == document_version_id)
    return session.execute(stmt).scalar_one_or_none()


def _locator_matches_binding(
    *,
    document_version: DocumentVersion | None,
    binding: StorageBinding | None,
) -> bool:
    if document_version is None:
        return False
    if document_version.storage_root is None or document_version.storage_relative_path is None:
        return False
    if binding is None:
        return True
    normalized_folder = binding.relative_path.replace("\\", "/").strip().strip("/")
    normalized_path = document_version.storage_relative_path.replace("\\", "/").strip().strip("/")
    return normalized_path.startswith(f"{normalized_folder}/")


def build_source_binary_requirements(
    session: Session,
    source_resolutions: tuple[SourceDocumentResolution, ...],
) -> tuple[SourceBinaryRequirement, ...]:
    requirements: list[SourceBinaryRequirement] = []
    for resolution in source_resolutions:
        template_definition = _active_template_definition(session, resolution.candidate.family_code)
        storage_root = _storage_root_for_scope(template_definition.storage_scope)
        binding = _storage_binding(session, resolution.candidate.storage_binding_id)
        document_version = _document_version(session, resolution.candidate.document_version_id)

        if resolution.candidate.document_version_id is None:
            readiness_status = "missing_document_version"
            detail = "Source dependency resolved to a logical document but no concrete document_version exists yet."
        elif document_version is None:
            readiness_status = "missing_document_version_row"
            detail = "Source dependency references a document_version_id that does not exist."
        elif resolution.candidate.storage_binding_id is None:
            readiness_status = "missing_storage_binding"
            detail = "Source document version has no storage_binding_id, so the source folder cannot be resolved."
        elif binding is None:
            readiness_status = "missing_storage_binding_row"
            detail = "Source document version references a storage_binding_id that does not exist."
        elif storage_root is None:
            readiness_status = "unsupported_storage_scope"
            detail = (
                f"Source family uses storage_scope={template_definition.storage_scope!r}, "
                "which has no StorageService root mapping yet."
            )
        elif document_version.storage_root is None or document_version.storage_relative_path is None:
            readiness_status = "folder_bound_locator_required"
            detail = (
                "Source folder is known, but exact source file locator is not registered on document_version yet. "
                "Render/copy-forward must fail closed until the concrete source binary path is persisted."
            )
        elif document_version.storage_root != storage_root:
            readiness_status = "storage_root_mismatch"
            detail = (
                f"Source document version locator uses storage_root={document_version.storage_root!r}, "
                f"but family scope requires {storage_root!r}."
            )
        elif not _locator_matches_binding(document_version=document_version, binding=binding):
            readiness_status = "locator_outside_bound_folder"
            detail = "Source document version locator does not stay within the resolved storage folder."
        else:
            readiness_status = "direct_stream_ready"
            detail = (
                "Source document version has an exact storage locator and can be opened through StorageService."
            )

        requirements.append(
            SourceBinaryRequirement(
                source_document_id=resolution.candidate.document_id,
                source_document_version_id=resolution.candidate.document_version_id,
                source_family_code=resolution.candidate.family_code,
                storage_binding_id=resolution.candidate.storage_binding_id,
                storage_root=storage_root,
                folder_relative_path=binding.relative_path if binding is not None else None,
                exact_storage_root=document_version.storage_root if document_version is not None else None,
                exact_storage_relative_path=document_version.storage_relative_path if document_version is not None else None,
                original_filename=document_version.original_filename if document_version is not None else None,
                required_bookmarks=resolution.request.required_bookmarks,
                legacy_filename_prefix_hints=_prefix_hints_for_family(resolution.candidate.family_code),
                readiness_status=readiness_status,
                detail=detail,
            )
        )
    return tuple(requirements)
