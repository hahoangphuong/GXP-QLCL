"""Regression: reused output must not trust a merely existing stale inspection binding."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.db.enums import StorageResolutionStatus
from backend.app.document import output_version
from backend.app.document.output_version import OutputVersionAllocationError
from backend.app.storage.types import StorageResolution


class _Session:
    def __init__(self, binding):
        self.binding = binding

    def execute(self, _statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.binding)


class _Storage:
    def __init__(self):
        self.resolve_calls = 0
        self.stat_calls = 0

    def exists(self, _path, **_kwargs):
        # Old implementation incorrectly accepted a stale path on this alone.
        return True

    def stat(self, _path, **_kwargs):
        self.stat_calls += 1
        return SimpleNamespace(is_dir=True)

    def resolve_inspection_folder(self, **_kwargs):
        self.resolve_calls += 1
        return StorageResolution(
            status=StorageResolutionStatus.NOT_FOUND,
            relative_path=None,
            absolute_path=None,
            candidate_count=0,
            detail="No matching inspection directory",
        )


def test_reused_output_rejects_existing_path_with_wrong_case_identity(monkeypatch):
    monkeypatch.setattr(
        output_version, "_load_case_storage_identity", lambda *_args: (2026, 73, "KT001")
    )
    # A directory can exist yet be unrelated to the canonical Case identity.
    binding = SimpleNamespace(
        id="stale-binding",
        relative_path="2026/unrelated-inspection-directory",
    )
    session = _Session(binding)
    storage = _Storage()
    prepared = SimpleNamespace(
        generation_plan=SimpleNamespace(
            template=SimpleNamespace(storage_scope="inspection_folder"),
            request=SimpleNamespace(case_id="case-1"),
        )
    )

    with pytest.raises(OutputVersionAllocationError, match="resolution failed"):
        output_version._resolve_reused_output_identity(session, storage, prepared)

    assert storage.stat_calls == 0  # Invalid label rejected before filesystem stat.
    assert storage.resolve_calls == 1  # Canonical resolver consulted; no stale reuse.
