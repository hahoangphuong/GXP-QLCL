"""Read-only staging-artifact discovery for the storage adapters.

A filename match is an *unverified candidate*, never proof that a transfer
is abandoned. This module has no deletion or mutation operation.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4
import re

from backend.app.storage.types import StorageServiceProtocol


_MANAGED = re.compile(r"^\.gxp-stage-[a-z0-9_-]{6,64}\.tmp$")
_LEGACY_SMB = re.compile(r"^.+\.tmp-[0-9a-f]{32}$")


def new_staging_name() -> str:
    return f".gxp-stage-{uuid4().hex}.tmp"


def classify_staging_candidate(filename: str) -> str | None:
    if _MANAGED.fullmatch(filename):
        return "managed_candidate"
    if _LEGACY_SMB.fullmatch(filename):
        return "legacy_smb_candidate"
    return None


@dataclass(frozen=True)
class StagingCandidate:
    root: str
    relative_path: str
    category: str
    size: int | None


@dataclass(frozen=True)
class StagingAudit:
    candidates: tuple[StagingCandidate, ...]
    scanned_directories: int
    scanned_entries: int
    truncated: bool
    incomplete_reason: str | None


def audit_staging_candidates(
    storage: StorageServiceProtocol,
    *,
    roots: tuple[str, ...] = ("inspection",),
    max_directories: int = 250,
    max_entries: int = 10000,
    max_depth: int = 8,
) -> StagingAudit:
    """Inventory metadata only; never read file contents or change a path.

    Directory and entry budgets prevent unbounded NAS walks. An incomplete
    scan is explicitly reported instead of being misrepresented as clean.
    """
    if not roots or any(root not in {"inspection", "dkkd", "template"} for root in roots):
        raise ValueError("Specify one or more recognized storage roots.")
    if max_directories < 1 or max_entries < 1 or max_depth < 0:
        raise ValueError("Scan budgets must be positive (max_depth may be zero).")

    queue = deque((root, "", 0) for root in dict.fromkeys(roots))
    findings: list[StagingCandidate] = []
    scanned_directories = 0
    scanned_entries = 0
    incomplete_reason = None

    while queue:
        if scanned_directories >= max_directories:
            incomplete_reason = "directory_budget_exceeded"
            break
        root, folder, depth = queue.popleft()
        entries = storage.list(folder, root=root)
        scanned_directories += 1
        for entry in entries:
            if scanned_entries >= max_entries:
                incomplete_reason = "entry_budget_exceeded"
                break
            scanned_entries += 1
            category = classify_staging_candidate(entry.name)
            if category is not None:
                findings.append(StagingCandidate(
                    root=root,
                    relative_path=entry.relative_path,
                    category=category,
                    size=entry.size,
                ))
            if entry.is_dir:
                if depth >= max_depth:
                    incomplete_reason = incomplete_reason or "depth_budget_exceeded"
                else:
                    queue.append((root, entry.relative_path, depth + 1))
        if incomplete_reason == "entry_budget_exceeded":
            break

    return StagingAudit(
        candidates=tuple(findings),
        scanned_directories=scanned_directories,
        scanned_entries=scanned_entries,
        truncated=incomplete_reason is not None,
        incomplete_reason=incomplete_reason,
    )
