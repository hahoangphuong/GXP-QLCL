from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from backend.app.db.models.phase1 import TemplateBinding


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TemplateBinaryBindingError(RuntimeError):
    pass


class TemplateBinaryBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "template_binary_binding"

    template_binding_id: Mapped[str] = mapped_column(
        ForeignKey("template_binding.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    storage_root: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "storage_root = 'template'",
            name="template_binary_binding_root_template",
        ),
    )


@dataclass(frozen=True)
class TemplateBinaryBindingLocator:
    template_binding_id: str
    storage_root: str
    storage_relative_path: str
    original_filename: str | None
    checksum_sha256: str


def normalize_template_binary_relative_path(relative_path: str) -> str:
    normalized = str(relative_path or "").replace("\\", "/").strip().strip("/")
    if not normalized:
        raise TemplateBinaryBindingError(
            "Template binary binding relative path must not be blank."
        )
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise TemplateBinaryBindingError(
            "Template binary binding path traversal is not allowed."
        )
    return "/".join(parts)


def normalize_template_binary_checksum(checksum_sha256: str) -> str:
    normalized = str(checksum_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(normalized):
        raise TemplateBinaryBindingError(
            "Template binary binding checksum_sha256 must be exactly 64 lowercase hexadecimal characters."
        )
    return normalized


def assign_template_binary_binding(
    session: Session,
    *,
    template_binding_id: str,
    storage_root: str,
    storage_relative_path: str,
    original_filename: str | None,
    checksum_sha256: str,
) -> TemplateBinaryBindingLocator:
    if storage_root != "template":
        raise TemplateBinaryBindingError(
            "Template binary bindings must use storage_root='template'."
        )

    binding = session.get(TemplateBinding, template_binding_id)
    if binding is None:
        raise TemplateBinaryBindingError(
            f"TemplateBinding {template_binding_id!r} was not found."
        )

    normalized_path = normalize_template_binary_relative_path(storage_relative_path)
    normalized_checksum = normalize_template_binary_checksum(checksum_sha256)

    existing = session.scalar(
        select(TemplateBinaryBinding).where(
            TemplateBinaryBinding.template_binding_id == template_binding_id
        )
    )
    if existing is None:
        existing = TemplateBinaryBinding(
            template_binding_id=template_binding_id,
            storage_root="template",
            storage_relative_path=normalized_path,
            original_filename=original_filename,
            checksum_sha256=normalized_checksum,
        )
        session.add(existing)
    else:
        existing.storage_root = "template"
        existing.storage_relative_path = normalized_path
        existing.original_filename = original_filename
        existing.checksum_sha256 = normalized_checksum

    session.flush()

    return TemplateBinaryBindingLocator(
        template_binding_id=template_binding_id,
        storage_root=existing.storage_root,
        storage_relative_path=existing.storage_relative_path,
        original_filename=existing.original_filename,
        checksum_sha256=existing.checksum_sha256,
    )


def get_template_binary_binding_locator(
    session: Session,
    template_binding_id: str,
) -> TemplateBinaryBindingLocator | None:
    existing = session.scalar(
        select(TemplateBinaryBinding).where(
            TemplateBinaryBinding.template_binding_id == template_binding_id
        )
    )
    if existing is None:
        return None
    return TemplateBinaryBindingLocator(
        template_binding_id=existing.template_binding_id,
        storage_root=existing.storage_root,
        storage_relative_path=existing.storage_relative_path,
        original_filename=existing.original_filename,
        checksum_sha256=existing.checksum_sha256,
    )
