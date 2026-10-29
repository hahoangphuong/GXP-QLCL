"""Read-only evidence for explicitly supplied output locators.

No storage traversal, deletion, orphan determination, or implicit DB commit.
A missing DB reference is NEVER evidence that a file is safe to remove.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import DocumentGenerationRun, DocumentVersion


_KNOWN_ROOTS = frozenset({"inspection", "dkkd", "template"})


@dataclass(frozen=True)
class OutputLocator:
    root: str
    relative_path: str


@dataclass(frozen=True)
class OutputVersionEvidence:
    version_id: str
    document_variant_id: str
    is_current: bool
    checksum_recorded: bool
    generation_run_ids: tuple[str, ...]
    generation_run_statuses: tuple[str, ...]


@dataclass(frozen=True)
class OutputLocatorEvidence:
    locator: OutputLocator
    versions: tuple[OutputVersionEvidence, ...]
    classification: str
    review_flags: tuple[str, ...] = ()
    physical_generation_identity: str = "not_observed"
    physical_storage_state: str = "not_observed"


@dataclass(frozen=True)
class OutputReconciliationReport:
    items: tuple[OutputLocatorEvidence, ...]
    status: str = "review_only"
    deletion_authorized: bool = False
    db_snapshot_consistency: str = "caller_transaction_unverified"
    physical_generation_ownership: str = "unverified"
    storage_atomicity: str = "unverified"
    cleanup_verdict: str = "not_evaluated"


def _valid_locator(locator: OutputLocator) -> bool:
    if not isinstance(locator, OutputLocator):
        return False
    root, path = locator.root, locator.relative_path
    if not isinstance(root, str) or root not in _KNOWN_ROOTS:
        return False
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path or ":" in path:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def validate_output_locator_request(
    locators: Iterable[OutputLocator], *, max_locators: int = 1000,
) -> None:
    """Reject invalid inventories before starting any database transaction."""
    if type(max_locators) is not int or not 1 <= max_locators <= 10000:
        raise ValueError("Invalid output reconciliation locator budget.")
    if not isinstance(locators, (tuple, list)):
        raise ValueError("Output locators must be a finite list or tuple.")
    if len(locators) > max_locators:
        raise ValueError("Output reconciliation locator budget exceeded.")
    if any(not _valid_locator(locator) for locator in locators):
        raise ValueError("Unsafe output locator.")
    pairs = [(loc.root, loc.relative_path) for loc in locators]
    if len(set(pairs)) != len(pairs):
        raise ValueError("Duplicate output locator.")



def reconcile_output_locators(
    session: Session,
    locators: Iterable[OutputLocator],
    *,
    max_locators: int = 1000,
) -> OutputReconciliationReport:
    """SELECT-only exact-locator report; caller must own a read-only session.

    Only DB registration is observed. Physical generation identity and
    storage state are explicitly NOT OBSERVED, regardless of checksum or
    generation-run success. Neither ownership nor an orphan verdict is supplied.
    """
    validate_output_locator_request(locators, max_locators=max_locators)
    pairs = [(loc.root, loc.relative_path) for loc in locators]
    # No claim of a transaction-stable snapshot is possible from this helper.
    # In PostgreSQL READ COMMITTED, version SELECTs and generation-run SELECTs
    # can observe different committed states. Callers needing one snapshot must
    # open a read-only REPEATABLE READ transaction before invoking this helper.
    # Keep the report conservatively unverified even if an external transaction
    # may have stronger isolation.
    references: dict[tuple[str, str], list[tuple[str, str, bool, bool]]] = {}
    runs: dict[str, list[tuple[str, str]]] = {}
    raw_version_ids: set = set()
    with session.no_autoflush:
        for start in range(0, len(pairs), 200):
            batch = pairs[start:start + 200]
            if not batch:
                continue
            rows = session.execute(
                select(
                    DocumentVersion.storage_root,
                    DocumentVersion.storage_relative_path,
                    DocumentVersion.id,
                    DocumentVersion.document_variant_id,
                    DocumentVersion.is_current,
                    DocumentVersion.checksum_sha256,
                ).where(tuple_(
                    DocumentVersion.storage_root,
                    DocumentVersion.storage_relative_path,
                ).in_(batch))
            )
            for root, path, vid, variant_id, current, checksum in rows:
                raw_version_ids.add(vid)
                references.setdefault((root, path), []).append((
                    str(vid), str(variant_id), bool(current), bool(checksum),
                ))
        # Preserve UUID values for typed SQLAlchemy/PostgreSQL IN bindings.
        version_ids = sorted(raw_version_ids, key=str)
        for start in range(0, len(version_ids), 200):
            rows = session.execute(
                select(
                    DocumentGenerationRun.output_document_version_id,
                    DocumentGenerationRun.id,
                    DocumentGenerationRun.status,
                ).where(DocumentGenerationRun.output_document_version_id.in_(
                    version_ids[start:start + 200],
                ))
            )
            for vid, run_id, status in rows:
                runs.setdefault(str(vid), []).append((str(run_id), str(status.value)))
    evidence = []
    for locator in locators:
        versions = []
        for vid, variant_id, is_current, checksum_recorded in sorted(
            references.get((locator.root, locator.relative_path), ())
        ):
            matched_runs = sorted(runs.get(vid, ()))
            versions.append(OutputVersionEvidence(
                version_id=vid,
                document_variant_id=variant_id,
                is_current=is_current,
                checksum_recorded=checksum_recorded,
                generation_run_ids=tuple(run_id for run_id, _ in matched_runs),
                generation_run_statuses=tuple(status for _, status in matched_runs),
            ))
        classification = (
            "no_exact_document_version_reference" if not versions else
            "multiple_exact_document_version_references" if len(versions) > 1 else
            "registered_exact_document_version_locator"
        )
        flags: set[str] = set()
        if not versions:
            flags.add("no_exact_db_reference")
        if len(versions) > 1:
            flags.add("multiple_exact_db_references")
        for version in versions:
            if not version.checksum_recorded:
                flags.add("checksum_not_recorded")
            if not version.generation_run_ids:
                flags.add("no_linked_generation_run")
            if len(version.generation_run_ids) > 1:
                flags.add("multiple_linked_generation_runs")
            if any(status != "succeeded" for status in version.generation_run_statuses):
                flags.add("generation_run_not_succeeded")
            if version.is_current and not version.checksum_recorded:
                flags.add("current_version_without_checksum")
        evidence.append(OutputLocatorEvidence(
            locator, tuple(versions), classification, tuple(sorted(flags)),
        ))
    return OutputReconciliationReport(
        items=tuple(sorted(evidence, key=lambda item: (
            item.locator.root, item.locator.relative_path,
        ))),
    )
