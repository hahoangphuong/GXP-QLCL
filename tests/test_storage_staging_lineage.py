from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import DocumentVariantType
from backend.app.db.models.phase1 import DocumentVersion, StorageBinding, TemplateDefinition
from backend.app.storage.staging import StagingAudit, StagingCandidate
from backend.app.storage.staging_lineage import reconcile_staging_lineage


def _inventory(*candidates: tuple[str, str], truncated: bool = False) -> StagingAudit:
    return StagingAudit(
        candidates=tuple(StagingCandidate(
            root=root, relative_path=path, category="managed_candidate", size=10,
        ) for root, path in candidates),
        scanned_directories=max(2, len({root for root, _ in candidates})),
        scanned_entries=8, truncated=truncated,
        requested_roots=tuple(dict.fromkeys(root for root, _ in candidates)),
        incomplete_reason="storage_access_failed" if truncated else None,
        failed_root="inspection" if truncated else None,
        failed_relative_path="" if truncated else None,
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as active:
        yield active
        active.rollback()
    engine.dispose()


def test_staging_lineage_exact_document_version_is_protected_reference(session):
    session.add(DocumentVersion(
        document_variant_id=str(uuid4()), version_no=1,
        storage_root="inspection", storage_relative_path="2026/site/a.docx",
    ))
    session.flush()
    report = reconcile_staging_lineage(session, _inventory(("inspection", "2026/site/a.docx")))
    item = report.items[0]
    assert item.evidence == "registered_exact_locator"
    assert len(item.document_version_ids) == 1
    assert item.template_definition_ids == ()
    assert report.status == "review_only"


def test_staging_lineage_template_exact_location_only_matching_root(session):
    session.add(TemplateDefinition(
        family_code="TEST", document_type_code="DOC", source_application="word",
        storage_scope="inspection_folder",
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        template_name="Template 1", is_active=True,
        template_storage_root="template", template_storage_relative_path="word/t.docx",
    ))
    session.flush()
    report = reconcile_staging_lineage(session, _inventory(
        ("template", "word/t.docx"), ("inspection", "word/t.docx")))
    matches = {(item.root, item.relative_path): item for item in report.items}
    assert len(matches[("template", "word/t.docx")].template_definition_ids) == 1
    assert matches[("template", "word/t.docx")].evidence == "registered_exact_locator"
    assert matches[("inspection", "word/t.docx")].evidence == "no_exact_locator_evidence"


def test_staging_lineage_flags_multiple_versions_at_same_exact_locator_for_review(session):
    path = "2026/site/.gxp-stage-abc123.tmp"
    first, second = str(uuid4()), str(uuid4())
    session.add_all([
        DocumentVersion(id=first, document_variant_id=str(uuid4()), version_no=1,
                        storage_root="inspection", storage_relative_path=path),
        DocumentVersion(id=second, document_variant_id=str(uuid4()), version_no=1,
                        storage_root="inspection", storage_relative_path=path),
    ])
    session.flush()
    report = reconcile_staging_lineage(session, _inventory(
        ("inspection", path),
        ("dkkd", path),
    ))
    rows = {(item.root, item.relative_path): item for item in report.items}
    assert rows[("inspection", path)].evidence == "multiple_exact_locator_references"
    assert rows[("inspection", path)].document_version_ids == tuple(sorted((first, second)))
    assert rows[("inspection", path)].template_definition_ids == ()
    assert rows[("dkkd", path)].evidence == "no_exact_locator_evidence"
    assert report.status == "review_only"


def test_staging_lineage_flags_cross_registry_overlap_without_guessing_owner(session):
    path = "2026/shared/.gxp-stage-abc123.tmp"
    session.add(DocumentVersion(
        document_variant_id=str(uuid4()), version_no=1,
        storage_root="inspection", storage_relative_path=path,
    ))
    session.add(TemplateDefinition(
        family_code="STAGING_SHARED", document_type_code="DOC",
        source_application="word", storage_scope="inspection_folder",
        variant_type=DocumentVariantType.EDITABLE_DOCX,
        template_name="overlap", is_active=True,
        template_storage_root="inspection", template_storage_relative_path=path,
    ))
    session.flush()
    item = reconcile_staging_lineage(session, _inventory(("inspection", path))).items[0]
    assert len(item.document_version_ids) == 1
    assert len(item.template_definition_ids) == 1
    assert item.evidence == "multiple_exact_locator_references"


def test_staging_lineage_binding_is_folder_only_not_file_identity(session):
    session.add(StorageBinding(
        case_id=None, year=2026, site_legacy_id=91,
        inspection_legacy_code="KT-91-GMP",
        relative_path="2026/facility (ID-91)", storage_class="synology_legacy",
    ))
    session.flush()
    report = reconcile_staging_lineage(session, _inventory(
        ("inspection", "2026/facility (ID-91)/.gxp-stage-aabbcc.tmp"),
        ("inspection", "2026/facility (ID-910)/.gxp-stage-aabbcc.tmp"),
        ("dkkd", "2026/facility (ID-91)/.gxp-stage-aabbcc.tmp"),
    ))
    matches = {(i.root, i.relative_path): i for i in report.items}
    candidate = matches[("inspection", "2026/facility (ID-91)/.gxp-stage-aabbcc.tmp")]
    assert len(candidate.enclosing_inspection_binding_ids) == 1
    assert candidate.evidence == "no_exact_locator_evidence"
    assert matches[("inspection", "2026/facility (ID-910)/.gxp-stage-aabbcc.tmp")].enclosing_inspection_binding_ids == ()
    assert matches[("dkkd", "2026/facility (ID-91)/.gxp-stage-aabbcc.tmp")].enclosing_inspection_binding_ids == ()


def test_staging_lineage_partial_scan_remains_explicitly_incomplete(session):
    result = reconcile_staging_lineage(session, _inventory(
        ("inspection", "one/.gxp-stage-aabbcc.tmp"), truncated=True))
    assert result.input_inventory_truncated is True
    assert result.input_incomplete_reason == "storage_access_failed"
    assert result.items[0].evidence == "no_exact_locator_evidence"
    assert result.status == "review_only"


def test_staging_lineage_rejects_bad_paths_and_large_inventory(session):
    for bad in ["../outside", "a//b", "/absolute", "a\\b", "a/./b", "a/../b"]:
        with pytest.raises(ValueError, match="invalid logical locator"):
            reconcile_staging_lineage(session, _inventory(("inspection", bad)))
    with pytest.raises(ValueError, match="candidate limit"):
        reconcile_staging_lineage(
            session, _inventory(("inspection", "one"), ("inspection", "two")),
            max_candidates=1,
        )


def test_staging_lineage_uses_selects_and_does_not_autoflush(session):
    seen: list[str] = []
    event.listen(session.bind, "before_cursor_execute",
        lambda conn, cursor, statement, params, ctx, executemany: seen.append(statement))
    report = reconcile_staging_lineage(session, _inventory(
        ("inspection", "2026/a/.gxp-stage-aabbcc.tmp")))
    assert report.items[0].document_version_ids == ()
    assert seen and all(sql.lstrip().upper().startswith("SELECT") for sql in seen)
    assert not session.new and not session.dirty and not session.deleted


def test_staging_lineage_rejects_contradictory_inventory_before_database_queries(session):
    from backend.app.storage.staging_lineage import validate_staging_inventory

    for inventory in [
        StagingAudit(
            candidates=(), scanned_directories=0, scanned_entries=0,
            truncated="false", incomplete_reason=None,
        ),
        StagingAudit(
            candidates=(), scanned_directories=0, scanned_entries=0,
            truncated=False, incomplete_reason="storage_access_failed",
        ),
        StagingAudit(
            candidates=(), scanned_directories=0, scanned_entries=0,
            truncated=True, incomplete_reason="storage_setup_failed",
            failed_root="inspection",
        ),
    ]:
        with pytest.raises(ValueError):
            validate_staging_inventory(inventory)
        with pytest.raises(ValueError):
            reconcile_staging_lineage(session, inventory)


def test_staging_lineage_empty_complete_scope_is_explicit(session):
    inventory = StagingAudit(
        candidates=(), scanned_directories=1, scanned_entries=0,
        truncated=False, incomplete_reason=None, requested_roots=("inspection",),
    )
    report = reconcile_staging_lineage(session, inventory)
    assert report.items == ()
    assert report.inspected_candidates == 0
    assert report.input_requested_roots == ("inspection",)
    assert report.status == "review_only"


def test_staging_lineage_rejects_empty_complete_scan_and_wrong_scope(session):
    invalid = [
        StagingAudit(
            candidates=(), scanned_directories=0, scanned_entries=0,
            truncated=False, incomplete_reason=None, requested_roots=("inspection",),
        ),
        StagingAudit(
            candidates=(), scanned_directories=1, scanned_entries=0,
            truncated=False, incomplete_reason=None,
            requested_roots=("inspection", "dkkd"),
        ),
        StagingAudit(
            candidates=(StagingCandidate(
                root="template", relative_path="word/.gxp-stage-abc123.tmp",
                category="managed_candidate", size=1,
            ),), scanned_directories=1, scanned_entries=1,
            truncated=False, incomplete_reason=None, requested_roots=("inspection",),
        ),
    ]
    for inventory in invalid:
        with pytest.raises(ValueError):
            reconcile_staging_lineage(session, inventory)


def test_staging_lineage_report_preserves_per_root_coverage(session):
    from backend.app.storage.staging import RootScanCoverage
    inventory = StagingAudit(
        candidates=(StagingCandidate(
            root="inspection", relative_path="year/site/.gxp-stage-aabbcc.tmp",
            category="managed_candidate", size=4,
        ),),
        scanned_directories=1, scanned_entries=1, truncated=True,
        incomplete_reason="directory_budget_exceeded",
        requested_roots=("inspection", "dkkd"),
        root_coverage=(
            RootScanCoverage("inspection", "complete", 1, 1),
            RootScanCoverage("dkkd", "not_started", 0, 0),
        ),
    )
    result = reconcile_staging_lineage(session, inventory)
    assert [(x.root, x.status) for x in result.input_root_coverage] == [
        ("inspection", "complete"), ("dkkd", "not_started"),
    ]
    assert result.input_inventory_truncated
    assert result.items[0].evidence == "no_exact_locator_evidence"
    assert result.status == "review_only"
