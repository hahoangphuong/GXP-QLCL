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
from backend.app.storage.staging import (
    RootScanCoverage, StagingAudit, StagingCandidate, classify_staging_candidate,
)


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
    input_requested_roots: tuple[str, ...] = ()
    input_root_coverage: tuple[RootScanCoverage, ...] = ()


def _batches(items: list, batch_size: int = 200) -> Iterator[list]:
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def _parent_folders(path: str) -> tuple[str, ...]:
    # Literal path segments only; folder matching cannot prove file ownership.
    parts = path.split("/")[:-1]
    return tuple("/".join(parts[:index]) for index in range(1, len(parts) + 1))


_KNOWN_ROOTS = frozenset({"inspection", "dkkd", "template"})
_CATEGORIES = frozenset({"managed_candidate", "legacy_smb_candidate"})
_INCOMPLETE_REASONS = frozenset({
    "directory_budget_exceeded", "entry_budget_exceeded",
    "depth_budget_exceeded", "storage_access_failed", "storage_setup_failed",
})


def _valid_locator(path: str, *, allow_empty: bool = False) -> bool:
    if not isinstance(path, str):
        return False
    if path == "":
        return allow_empty
    if path.startswith("/") or "\\" in path or ":" in path:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        return False
    return all(segment not in {"", ".", ".."} for segment in path.split("/"))


def validate_staging_inventory(
    inventory: StagingAudit,
    *,
    max_candidates: int = 10000,
    require_scanner_categories: bool = False,
    require_declared_scope: bool = False,
    require_root_coverage: bool = False,
) -> None:
    """Validate metadata only; never attest authenticity or deletion safety.

    The optional CLI requires category/basename consistency because its input
    is supposed to be a real scanner export. Pure in-memory callers can pass
    artificial category labels for isolated lineage tests, but must still
    supply safe, internally consistent paths and counters.
    """
    if not isinstance(inventory, StagingAudit):
        raise ValueError("Invalid staging inventory.")
    if type(max_candidates) is not int or max_candidates < 1 or len(inventory.candidates) > max_candidates:
        raise ValueError("Staging lineage candidate limit exceeded.")
    if not isinstance(inventory.candidates, tuple):
        raise ValueError("Invalid staging candidate collection.")
    scope = inventory.requested_roots
    if (
        not isinstance(scope, tuple) or
        any(not isinstance(root, str) or root not in _KNOWN_ROOTS for root in scope)
        or len(set(scope)) != len(scope)
        or (require_declared_scope and not scope)
    ):
        raise ValueError("Invalid or missing staging inventory root scope.")
    coverage = inventory.root_coverage
    if not isinstance(coverage, tuple) or (require_root_coverage and not coverage):
        raise ValueError("Missing or invalid staging root coverage.")
    if coverage:
        if not scope or len(coverage) != len(scope):
            raise ValueError("Staging root coverage does not match requested scope.")
        for expected_root, entry in zip(scope, coverage):
            if (
                not isinstance(entry, RootScanCoverage)
                or entry.root != expected_root
                or entry.status not in {"complete", "partial", "not_started"}
                or type(entry.scanned_directories) is not int
                or entry.scanned_directories < 0
                or type(entry.scanned_entries) is not int
                or entry.scanned_entries < 0
                or (entry.status == "not_started" and (
                    entry.scanned_directories != 0 or entry.scanned_entries != 0
                ))
                or (entry.status == "complete" and entry.scanned_directories < 1)
            ):
                raise ValueError("Invalid per-root staging scan coverage.")
        if (
            sum(entry.scanned_directories for entry in coverage) != inventory.scanned_directories
            or sum(entry.scanned_entries for entry in coverage) != inventory.scanned_entries
        ):
            raise ValueError("Per-root scan counters do not match the inventory totals.")
        if inventory.truncated:
            if all(entry.status == "complete" for entry in coverage):
                raise ValueError("Truncated inventory must include incomplete root coverage.")
        elif any(entry.status != "complete" for entry in coverage):
            raise ValueError("Complete inventory cannot have incomplete root coverage.")
    if (
        type(inventory.scanned_directories) is not int or inventory.scanned_directories < 0
        or type(inventory.scanned_entries) is not int
        or inventory.scanned_entries < len(inventory.candidates)
        or type(inventory.truncated) is not bool
    ):
        raise ValueError("Invalid staging inventory counters or truncation flag.")
    if inventory.truncated:
        if inventory.incomplete_reason not in _INCOMPLETE_REASONS:
            raise ValueError("Invalid staging incomplete reason.")
    else:
        if inventory.incomplete_reason is not None:
            raise ValueError("Complete staging inventory cannot contain an incomplete reason.")
        # Every requested root needs at least its initial directory scan.
        # Even without a scope field, a scanner cannot call an empty,
        # zero-directory inventory "complete".
        if inventory.scanned_directories == 0 or (
            scope and inventory.scanned_directories < len(scope)
        ):
            raise ValueError("A complete inventory requires scanned root directories.")
    if inventory.incomplete_reason == "storage_access_failed":
        if (
            inventory.failed_root not in _KNOWN_ROOTS
            or (scope and inventory.failed_root not in scope)
            or not _valid_locator(inventory.failed_relative_path, allow_empty=True)
        ):
            raise ValueError("Invalid staging access failure locator.")
    elif inventory.failed_root is not None or inventory.failed_relative_path is not None:
        raise ValueError("Unexpected staging failure locator.")
    if inventory.incomplete_reason == "storage_setup_failed":
        if (
            inventory.candidates or inventory.scanned_directories or inventory.scanned_entries
            or (coverage and any(entry.status != "not_started" for entry in coverage))
        ):
            raise ValueError("A storage setup failure cannot contain scanned entries.")
    if inventory.incomplete_reason == "storage_access_failed" and coverage:
        failed = next(entry for entry in coverage if entry.root == inventory.failed_root)
        if failed.status != "partial":
            raise ValueError("A failed root must be marked partially scanned.")

    not_started_roots = {
        entry.root for entry in coverage if entry.status == "not_started"
    }
    seen: set[tuple[str, str]] = set()
    for candidate in inventory.candidates:
        if not isinstance(candidate, StagingCandidate):
            raise ValueError("Invalid staging candidate record.")
        if (
            candidate.root not in _KNOWN_ROOTS
            or (scope and candidate.root not in scope)
            or candidate.root in not_started_roots
            or not _valid_locator(candidate.relative_path)
        ):
            raise ValueError("Staging inventory contains an invalid logical locator.")
        if candidate.category not in _CATEGORIES:
            raise ValueError("Invalid staging candidate category.")
        if candidate.size is not None and (type(candidate.size) is not int or candidate.size < 0):
            raise ValueError("Invalid staging candidate size.")
        key = (candidate.root, candidate.relative_path)
        if key in seen:
            raise ValueError("Duplicate staging candidate locator.")
        seen.add(key)
        if require_scanner_categories and classify_staging_candidate(
            candidate.relative_path.rsplit("/", 1)[-1],
        ) != candidate.category:
            raise ValueError("Staging candidate name does not match its category.")


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
    validate_staging_inventory(inventory, max_candidates=max_candidates)
    keys = sorted({(c.root, c.relative_path) for c in inventory.candidates})

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
        # Two different DB records can name the same exact binary path.
        # Report the overlap explicitly, without inferring it is invalid or
        # resolving ownership from labels, filenames or apparent recency.
        reference_count = len(versions) + len(templates)
        if reference_count > 1:
            evidence = "multiple_exact_locator_references"
        elif reference_count == 1:
            evidence = "registered_exact_locator"
        else:
            evidence = "no_exact_locator_evidence"
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
        input_requested_roots=inventory.requested_roots,
        input_root_coverage=inventory.root_coverage,
    )
