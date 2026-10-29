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
    run = ("v-1", "r-1", SimpleNamespace(value="succeeded"), "variant-1")
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


def test_review_flags_identify_unresolved_db_evidence_without_orphan_verdict():
    versions = [
        ("inspection", "case/output.docx", "v1", "variant", True, None),
        ("inspection", "case/output.docx", "v2", "variant", False, "recorded"),
    ]
    runs = [
        ("v2", "r2", SimpleNamespace(value="failed"), "variant"),
        ("v2", "r1", SimpleNamespace(value="pending"), "variant"),
    ]
    session = QueryOnlySession(versions, runs)
    report = reconcile_output_locators(
        session, [OutputLocator("inspection", "case/output.docx")]
    )
    item = report.items[0]
    assert item.classification == "multiple_exact_document_version_references"
    assert item.review_flags == tuple(sorted({
        "multiple_exact_db_references", "current_version_without_checksum",
        "checksum_not_recorded", "no_linked_generation_run",
        "multiple_linked_generation_runs", "generation_run_not_succeeded",
    }))
    assert report.db_snapshot_consistency == "caller_transaction_unverified"
    assert report.deletion_authorized is False
    assert item.versions[1].generation_run_ids == ("r1", "r2")
    assert item.versions[1].generation_run_statuses == ("pending", "failed")


def test_missing_reference_flag_is_not_orphan_authorization():
    report = reconcile_output_locators(
        QueryOnlySession(), [OutputLocator("dkkd", "missing.docx")]
    )
    assert report.items[0].review_flags == ("no_exact_db_reference",)
    assert report.deletion_authorized is False


def test_clean_single_reference_has_no_review_flags():
    report = reconcile_output_locators(
        QueryOnlySession(
            [("inspection", "case/ok.docx", "v", "variant", True, "sha")],
            [("v", "r", SimpleNamespace(value="succeeded"), "variant")],
        ),
        [OutputLocator("inspection", "case/ok.docx")],
    )
    assert report.items[0].review_flags == ()
    assert report.deletion_authorized is False


@pytest.mark.parametrize(
    ("version_rows", "run_rows", "expected_classification"),
    [
        ((), (), "no_exact_document_version_reference"),
        (
            (("inspection", "case/evidence.docx", "v1", "variant", True, "checksum"),),
            (("v1", "r1", SimpleNamespace(value="succeeded"), "variant"),),
            "registered_exact_document_version_locator",
        ),
        (
            (
                ("inspection", "case/evidence.docx", "v1", "variant", True, "checksum"),
                ("inspection", "case/evidence.docx", "v2", "variant", False, "checksum"),
            ),
            (
                ("v1", "r1", SimpleNamespace(value="succeeded"), "variant"),
                ("v2", "r2", SimpleNamespace(value="succeeded"), "variant"),
            ),
            "multiple_exact_document_version_references",
        ),
    ],
)
def test_db_evidence_never_attests_physical_generation_or_cleanup(
    version_rows, run_rows, expected_classification,
):
    report = reconcile_output_locators(
        QueryOnlySession(version_rows, run_rows),
        [OutputLocator("inspection", "case/evidence.docx")],
    )
    item = report.items[0]
    assert item.classification == expected_classification
    assert item.physical_generation_identity == "not_observed"
    assert item.physical_storage_state == "not_observed"
    assert report.physical_generation_ownership == "unverified"
    assert report.storage_atomicity == "unverified"
    assert report.cleanup_verdict == "not_evaluated"
    assert report.deletion_authorized is False


def test_run_variant_mismatch_is_not_accepted_as_clean_lineage():
    report = reconcile_output_locators(
        QueryOnlySession(
            [("inspection", "case/wrong-variant.docx", "v", "right-variant", True, "sha")],
            [("v", "r", SimpleNamespace(value="succeeded"), "other-variant")],
        ),
        [OutputLocator("inspection", "case/wrong-variant.docx")],
    )
    version = report.items[0].versions[0]
    assert version.generation_run_statuses == ("succeeded",)
    assert version.generation_run_variant_identity_verified is False
    assert report.items[0].review_flags == ("generation_run_variant_identity_mismatch",)
    assert report.deletion_authorized is False


def test_two_runs_with_one_foreign_variant_are_flagged():
    report = reconcile_output_locators(
        QueryOnlySession(
            [("inspection", "case/two-runs.docx", "v", "right-variant", False, "sha")],
            [
                ("v", "r1", SimpleNamespace(value="succeeded"), "right-variant"),
                ("v", "r2", SimpleNamespace(value="succeeded"), "foreign-variant"),
            ],
        ),
        [OutputLocator("inspection", "case/two-runs.docx")],
    )
    assert report.items[0].review_flags == (
        "generation_run_variant_identity_mismatch",
        "multiple_linked_generation_runs",
    )
    assert report.deletion_authorized is False
