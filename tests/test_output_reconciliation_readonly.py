"""Exact output lineage evidence stays read-only and never licenses deletion."""
from types import SimpleNamespace

import pytest

from backend.app.document.output_reconciliation import (
    OutputLocator,
    reconcile_output_locators,
)


class _NoAutoflush:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class QueryOnlySession:
    no_autoflush = _NoAutoflush()

    def __init__(self, version_rows=(), run_rows=()):
        self.version_rows = version_rows
        self.run_rows = run_rows
        self.calls = 0

    def execute(self, statement):
        self.calls += 1
        return self.version_rows if self.calls == 1 else self.run_rows

    def commit(self):
        raise AssertionError("read-only reconciliation must never commit")

    def flush(self):
        raise AssertionError("read-only reconciliation must never flush")


def test_reconciliation_matches_exact_root_and_path_without_storage_access():
    version = ("inspection", "2026/case/one.docx", "v-1", "variant-1", True, "abc")
    run = ("v-1", "r-1", SimpleNamespace(value="succeeded"))
    session = QueryOnlySession((version,), (run,))
    report = reconcile_output_locators(
        session, [
            OutputLocator("inspection", "2026/case/one.docx"),
            OutputLocator("dkkd", "2026/case/one.docx"),
        ]
    )
    assert report.status == "review_only"
    assert report.deletion_authorized is False
    assert session.calls == 2
    matched, missing = report.items[1], report.items[0]
    assert matched.classification == "registered_exact_document_version_locator"
    assert matched.versions[0].version_id == "v-1"
    assert matched.versions[0].generation_run_statuses == ("succeeded",)
    assert missing.classification == "no_exact_document_version_reference"
    assert missing.versions == ()


@pytest.mark.parametrize("path", [
    "../escape", "/absolute", "a//b", "a/./b", "a/../b",
    "a\\b", "C:drive", "bad\x00name",
])
def test_reconciliation_rejects_unsafe_input_before_query(path):
    session = QueryOnlySession()
    with pytest.raises(ValueError, match="Unsafe"):
        reconcile_output_locators(session, [OutputLocator("inspection", path)])
    assert session.calls == 0


def test_reconciliation_rejects_duplicate_and_budget_without_query():
    session = QueryOnlySession()
    locator = OutputLocator("inspection", "a.docx")
    with pytest.raises(ValueError, match="Duplicate"):
        reconcile_output_locators(session, [locator, locator])
    with pytest.raises(ValueError, match="budget exceeded"):
        reconcile_output_locators(session, [locator, OutputLocator("inspection", "b.docx")], max_locators=1)
    with pytest.raises(ValueError, match="Unsafe"):
        reconcile_output_locators(session, [OutputLocator("unknown", "a.docx")])
    assert session.calls == 0


def test_empty_inventory_does_not_query_or_infer_orphan():
    session = QueryOnlySession()
    report = reconcile_output_locators(session, [])
    assert report.items == ()
    assert report.deletion_authorized is False
    assert session.calls == 0
