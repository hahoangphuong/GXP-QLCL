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
        scanned_directories=2, scanned_entries=8, truncated=truncated,
        incomplete_reason="storage_access_failed" if truncated else None,
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
