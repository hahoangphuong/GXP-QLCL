from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import DocumentVersion, StorageBinding


class DocumentVersionLocatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class DocumentVersionLocator:
    document_version_id: str
    storage_root: str
    storage_relative_path: str
    original_filename: str | None
    storage_binding_id: str | None


def _normalize_relative_path(relative_path: str) -> str:
    normalized = str(relative_path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        raise DocumentVersionLocatorError("Document version locator path must not be blank.")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise DocumentVersionLocatorError("Document version locator path traversal is not allowed.")
    return "/".join(parts)


def _require_supported_storage_root(storage_root: str) -> str:
    if storage_root not in {"inspection", "dkkd"}:
        raise DocumentVersionLocatorError(f"Unsupported storage root {storage_root!r} for document version locator.")
    return storage_root


def _load_document_version(session: Session, document_version_id: str) -> DocumentVersion:
    stmt: Select[tuple[DocumentVersion]] = select(DocumentVersion).where(DocumentVersion.id == document_version_id)
    document_version = session.execute(stmt).scalar_one_or_none()
    if document_version is None:
        raise DocumentVersionLocatorError(f"DocumentVersion {document_version_id!r} was not found.")
    return document_version


def _load_storage_binding(session: Session, storage_binding_id: str | None) -> StorageBinding | None:
    if storage_binding_id is None:
        return None
    stmt: Select[tuple[StorageBinding]] = select(StorageBinding).where(StorageBinding.id == storage_binding_id)
    return session.execute(stmt).scalar_one_or_none()


def _validate_against_binding(
    *,
    storage_root: str,
    storage_relative_path: str,
    storage_binding: StorageBinding | None,
) -> None:
    if storage_binding is None:
        return
    if storage_root != "inspection":
        return
    folder_relative_path = _normalize_relative_path(storage_binding.relative_path)
    if storage_relative_path == folder_relative_path:
        raise DocumentVersionLocatorError("Document version locator must point to a file path, not only the bound folder.")
    if not storage_relative_path.startswith(f"{folder_relative_path}/"):
        raise DocumentVersionLocatorError(
            "Document version locator must stay within the bound storage folder for inspection-scoped documents."
        )


def assign_document_version_locator(
    session: Session,
    *,
    document_version_id: str,
    storage_root: str,
    storage_relative_path: str,
    original_filename: str | None = None,
) -> DocumentVersionLocator:
    document_version = _load_document_version(session, document_version_id)
    normalized_root = _require_supported_storage_root(storage_root)
    normalized_path = _normalize_relative_path(storage_relative_path)
    storage_binding = _load_storage_binding(session, document_version.storage_binding_id)
    _validate_against_binding(
        storage_root=normalized_root,
        storage_relative_path=normalized_path,
        storage_binding=storage_binding,
    )
    document_version.storage_root = normalized_root
    document_version.storage_relative_path = normalized_path
    document_version.original_filename = original_filename
    session.flush()
    return DocumentVersionLocator(
        document_version_id=document_version.id,
        storage_root=normalized_root,
        storage_relative_path=normalized_path,
        original_filename=original_filename,
        storage_binding_id=document_version.storage_binding_id,
    )


def get_document_version_locator(
    session: Session,
    document_version_id: str,
) -> DocumentVersionLocator | None:
    document_version = _load_document_version(session, document_version_id)
    if document_version.storage_root is None or document_version.storage_relative_path is None:
        return None
    return DocumentVersionLocator(
        document_version_id=document_version.id,
        storage_root=document_version.storage_root,
        storage_relative_path=document_version.storage_relative_path,
        original_filename=document_version.original_filename,
        storage_binding_id=document_version.storage_binding_id,
    )
