from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO, Iterator

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import TemplateDefinition
from backend.app.storage.types import StorageServiceProtocol

if TYPE_CHECKING:
    from backend.app.document.service import AllocatedDocumentGeneration


class TemplateBinaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class TemplateBinaryLocator:
    template_definition_id: str
    family_code: str
    template_name: str
    storage_root: str
    storage_relative_path: str
    original_filename: str | None
    checksum_sha256: str | None


@dataclass(frozen=True)
class TemplateBinaryRequirement:
    template_definition_id: str | None
    family_code: str
    template_name: str
    storage_root: str | None
    storage_relative_path: str | None
    original_filename: str | None
    checksum_sha256: str | None
    readiness_status: str
    detail: str


def _load_template_definition(session: Session, template_definition_id: str) -> TemplateDefinition:
    stmt: Select[tuple[TemplateDefinition]] = select(TemplateDefinition).where(TemplateDefinition.id == template_definition_id)
    template_definition = session.execute(stmt).scalar_one_or_none()
    if template_definition is None:
        raise TemplateBinaryError(f"TemplateDefinition {template_definition_id!r} was not found.")
    return template_definition


def _normalize_relative_path(relative_path: str) -> str:
    normalized = str(relative_path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        raise TemplateBinaryError("Template binary relative path must not be blank.")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise TemplateBinaryError("Template binary path traversal is not allowed.")
    return "/".join(parts)


def assign_template_binary_locator(
    session: Session,
    *,
    template_definition_id: str,
    storage_root: str,
    storage_relative_path: str,
    original_filename: str | None = None,
    checksum_sha256: str | None = None,
) -> TemplateBinaryLocator:
    if storage_root != "template":
        raise TemplateBinaryError("Template binaries must use storage_root='template'.")
    template_definition = _load_template_definition(session, template_definition_id)
    normalized_path = _normalize_relative_path(storage_relative_path)
    template_definition.template_storage_root = storage_root
    template_definition.template_storage_relative_path = normalized_path
    template_definition.template_original_filename = original_filename
    template_definition.template_checksum_sha256 = checksum_sha256
    session.flush()
    return TemplateBinaryLocator(
        template_definition_id=template_definition.id,
        family_code=template_definition.family_code,
        template_name=template_definition.template_name,
        storage_root=storage_root,
        storage_relative_path=normalized_path,
        original_filename=original_filename,
        checksum_sha256=checksum_sha256,
    )


def get_template_binary_locator(
    session: Session,
    template_definition_id: str,
) -> TemplateBinaryLocator | None:
    template_definition = _load_template_definition(session, template_definition_id)
    if template_definition.template_storage_root is None or template_definition.template_storage_relative_path is None:
        return None
    return TemplateBinaryLocator(
        template_definition_id=template_definition.id,
        family_code=template_definition.family_code,
        template_name=template_definition.template_name,
        storage_root=template_definition.template_storage_root,
        storage_relative_path=template_definition.template_storage_relative_path,
        original_filename=template_definition.template_original_filename,
        checksum_sha256=template_definition.template_checksum_sha256,
    )


def build_template_binary_requirement(
    session: Session,
    allocated: AllocatedDocumentGeneration,
) -> TemplateBinaryRequirement:
    template_definition_id = allocated.prepared.persisted_state.template_definition_id
    if template_definition_id is None:
        return TemplateBinaryRequirement(
            template_definition_id=None,
            family_code=allocated.prepared.generation_plan.template.family_code,
            template_name=allocated.prepared.generation_plan.template.template_pattern,
            storage_root=None,
            storage_relative_path=None,
            original_filename=None,
            checksum_sha256=None,
            readiness_status="missing_template_definition",
            detail="No template_definition row is linked to the prepared generation.",
        )
    template_definition = _load_template_definition(session, template_definition_id)
    if template_definition.template_storage_root is None or template_definition.template_storage_relative_path is None:
        return TemplateBinaryRequirement(
            template_definition_id=template_definition.id,
            family_code=template_definition.family_code,
            template_name=template_definition.template_name,
            storage_root=None,
            storage_relative_path=None,
            original_filename=template_definition.template_original_filename,
            checksum_sha256=template_definition.template_checksum_sha256,
            readiness_status="missing_template_locator",
            detail="TemplateDefinition has no exact template binary locator yet.",
        )
    if template_definition.template_storage_root != "template":
        return TemplateBinaryRequirement(
            template_definition_id=template_definition.id,
            family_code=template_definition.family_code,
            template_name=template_definition.template_name,
            storage_root=template_definition.template_storage_root,
            storage_relative_path=template_definition.template_storage_relative_path,
            original_filename=template_definition.template_original_filename,
            checksum_sha256=template_definition.template_checksum_sha256,
            readiness_status="invalid_template_root",
            detail="TemplateDefinition template binary locator must use storage_root='template'.",
        )
    return TemplateBinaryRequirement(
        template_definition_id=template_definition.id,
        family_code=template_definition.family_code,
        template_name=template_definition.template_name,
        storage_root=template_definition.template_storage_root,
        storage_relative_path=template_definition.template_storage_relative_path,
        original_filename=template_definition.template_original_filename,
        checksum_sha256=template_definition.template_checksum_sha256,
        readiness_status="direct_stream_ready",
        detail="TemplateDefinition has an exact template binary locator and can be opened through StorageService.",
    )


@contextmanager
def open_template_binary_stream(
    storage: StorageServiceProtocol,
    requirement: TemplateBinaryRequirement,
) -> Iterator[BinaryIO]:
    if requirement.readiness_status != "direct_stream_ready":
        raise TemplateBinaryError(f"Template binary is not ready for direct access: {requirement.readiness_status}.")
    if requirement.storage_root is None or requirement.storage_relative_path is None:
        raise TemplateBinaryError("Template binary locator is incomplete.")
    with storage.read_stream(requirement.storage_relative_path, root=requirement.storage_root) as stream:
        yield stream
