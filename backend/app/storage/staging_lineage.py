"""Read-only cross-check of staging candidates against exact document lineage.

An absent registered locator is not proof a staging file is orphaned.
StorageBinding represents an inspection folder, never a specific file.
No cleanup decision or storage mutation is implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import DocumentVersion, StorageBinding, TemplateDefinition
from backend.app.storage.staging import StagingAudit


@dataclass(frozen=True)
class StagingLineageItem:
    root: str
    relative_path: str
    category: str
    size: int | None
    document_version_ids: tuple[str, ...]
    template_definition_ids: tuple[str, ...]
    enclosing_inspection_binding_ids: tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class StagingLineageReport:
    items: tuple[StagingLineageItem, ...]
    input_inventory_truncated: bool
    input_incomplete_reason: str | None
    inspected_candidates: int
    status: str = "review_only"


def _batches(items: list, batch_size: int = 200) -> Iterator[list]:
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def _parent_folders(path: str) -> tuple[str, ...]:
    # Literal path segments only; folder matching cannot prove file ownership.
    parts = path.split("/")[:-1]
    return tuple("/".join(parts[:index]) for index in range(1, len(parts) + 1))


def reconcile_staging_lineage(
    session: Session,
    inventory: StagingAudit,
    *,
    max_candidates: int = 10000,
) -> StagingLineageReport:
    """Perform SELECT-only evidence lookup with a caller-owned read-only session.

    Only exact registered root/path pairs count as file-level references.
    Never infer a deletion decision from lack of a match.
    """
    if max_candidates < 1 or len(inventory.candidates) > max_candidates:
        raise ValueError("Staging lineage candidate limit exceeded.")
    keys = sorted({(c.root, c.relative_path) for c in inventory.candidates})
    if any(root not in {"inspection", "dkkd", "template"} or not path or
           path.startswith("/") or "\\" in path or
           any(segment in {"", ".", ".."} for segment in path.split("/"))
           for root, path in keys):
        raise ValueError("Staging inventory contains an invalid logical locator.")

    version_refs: dict[tuple[str, str], set[str]] = {}
    template_refs: dict[tuple[str, str], set[str]] = {}
    binding_refs: dict[str, set[str]] = {}
    parent_folders = sorted({
        parent
        for root, path in keys if root == "inspection"
        for parent in _parent_folders(path)
    })
    with session.no_autoflush:
        for batch in _batches(keys):
            rows = session.execute(
                select(DocumentVersion.storage_root, DocumentVersion.storage_relative_path, DocumentVersion.id)
                .where(tuple_(DocumentVersion.storage_root, DocumentVersion.storage_relative_path).in_(batch))
            )
            for root, path, version_id in rows:
                version_refs.setdefault((root, path), set()).add(str(version_id))

            templates = session.execute(
                select(TemplateDefinition.template_storage_root, TemplateDefinition.template_storage_relative_path, TemplateDefinition.id)
                .where(tuple_(TemplateDefinition.template_storage_root, TemplateDefinition.template_storage_relative_path).in_(batch))
            )
            for root, path, template_id in templates:
                template_refs.setdefault((root, path), set()).add(str(template_id))

        for batch in _batches(parent_folders):
            bindings = session.execute(
                select(StorageBinding.relative_path, StorageBinding.id)
                .where(StorageBinding.relative_path.in_(batch))
            )
            for folder, binding_id in bindings:
                binding_refs.setdefault(folder, set()).add(str(binding_id))

    items: list[StagingLineageItem] = []
    for candidate in inventory.candidates:
        key = (candidate.root, candidate.relative_path)
        versions = tuple(sorted(version_refs.get(key, ())))
        templates = tuple(sorted(template_refs.get(key, ())))
        bindings = tuple(sorted({
            binding_id
            for folder in (_parent_folders(candidate.relative_path) if candidate.root == "inspection" else ())
            for binding_id in binding_refs.get(folder, ())
        }))
        evidence = "registered_exact_locator" if versions or templates else "no_exact_locator_evidence"
        items.append(StagingLineageItem(
            root=candidate.root,
            relative_path=candidate.relative_path,
            category=candidate.category,
            size=candidate.size,
            document_version_ids=versions,
            template_definition_ids=templates,
            enclosing_inspection_binding_ids=bindings,
            evidence=evidence,
        ))
    return StagingLineageReport(
        items=tuple(sorted(items, key=lambda item: (item.root, item.relative_path))),
        input_inventory_truncated=inventory.truncated,
        input_incomplete_reason=inventory.incomplete_reason,
        inspected_candidates=len(inventory.candidates),
    )
