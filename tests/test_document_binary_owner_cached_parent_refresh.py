"""Two-session owner revalidation for canonical Document binary locators.

A locator is a sensitive read, even without opening the underlying bytes.
Never authorize it from Document or CAPA owner identities cached before
another committed business-owner change.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
import pytest

from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    CapaCycle, Case, Company, Document, DocumentVariant, DocumentVersion, Site,
)
from backend.app.services.document_api import DocumentWorkflowService


def _seed_binary(tmp_path, *, scope: str):
    engine = create_engine(f"sqlite:///{tmp_path / 'binary_owner.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Two-session binary owner regression")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Synthetic owner Site")
        db.add(site)
        db.flush()
        original = Case(site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED)
        other = Case(site_id=site.id, gxp_type="GMP", state=CaseState.PLANNED)
        db.add_all([original, other])
        db.flush()
        cycle_id = None
        if scope == "capa_cycle":
            cycle = CapaCycle(
                case_id=original.id, round_no=1, status="requested",
                requested_on=None, submitted_on=None, assessed_on=None,
                assessor_name=None, result=None,
            )
            db.add(cycle)
            db.flush()
            cycle_id = cycle.id
        doc = Document(
            case_id=original.id if scope == "case" else None,
            capa_cycle_id=cycle_id,
            family_code="SYNTHETIC_BINARY_OWNER",
            document_type_code="SYNTHETIC_BINARY_OWNER",
        )
        db.add(doc)
        db.flush()
        variant = DocumentVariant(
            document_id=doc.id, variant_type=DocumentVariantType.EDITABLE_DOCX,
            is_active=True,
        )
        db.add(variant)
        db.flush()
        version = DocumentVersion(
            document_variant_id=variant.id, version_no=1, is_current=True,
            storage_root="inspection", storage_relative_path="synthetic/owner.docx",
            original_filename="owner.docx", checksum_sha256="a" * 64,
        )
        db.add(version)
        db.commit()
        return engine, original.id, other.id, doc.id, cycle_id


def test_locator_rechecks_document_exclusive_case_owner_after_other_session_commit(tmp_path):
    engine, old_case, new_case, doc_id, _ = _seed_binary(tmp_path, scope="case")
    service = DocumentWorkflowService()
    try:
        with Session(engine, expire_on_commit=False) as cached_session:
            old_document = cached_session.get(Document, doc_id)
            assert old_document.case_id == old_case

            with Session(engine) as writer:
                canonical = writer.get(Document, doc_id)
                canonical.case_id = new_case
                writer.commit()

            with pytest.raises(HTTPException) as exc:
                service.get_current_document_binary_locator_for_parent(
                    cached_session, document_id=doc_id,
                    expected_parent_scope="case", expected_parent_id=old_case,
                )
            assert exc.value.status_code == 404
            assert "requested business owner" in str(exc.value.detail)
            cached_session.rollback()
        with Session(engine) as verify:
            assert verify.get(Document, doc_id).case_id == new_case
    finally:
        engine.dispose()


def test_locator_rechecks_capa_case_owner_after_other_session_commit(tmp_path):
    engine, old_case, new_case, doc_id, cycle_id = _seed_binary(tmp_path, scope="capa_cycle")
    assert cycle_id is not None
    service = DocumentWorkflowService()
    try:
        with Session(engine, expire_on_commit=False) as cached_session:
            old_cycle = cached_session.get(CapaCycle, cycle_id)
            assert old_cycle.case_id == old_case

            with Session(engine) as writer:
                canonical = writer.get(CapaCycle, cycle_id)
                canonical.case_id = new_case
                writer.commit()

            with pytest.raises(HTTPException) as exc:
                service.get_current_document_binary_locator_for_parent(
                    cached_session, document_id=doc_id,
                    expected_parent_scope="capa_cycle", expected_parent_id=cycle_id,
                    expected_case_id=old_case,
                )
            assert exc.value.status_code == 404
            assert "requested case" in str(exc.value.detail)
            cached_session.rollback()
        with Session(engine) as verify:
            assert verify.get(CapaCycle, cycle_id).case_id == new_case
    finally:
        engine.dispose()


@pytest.mark.parametrize("draft_owner", ["variant", "version"])
def test_locator_uses_committed_binary_snapshot_without_discarding_local_draft(tmp_path, draft_owner):
    """Sensitive read must not autoflush or refresh operator's variant/version draft."""
    engine, case_id, _, doc_id, _ = _seed_binary(tmp_path, scope="case")
    service = DocumentWorkflowService()
    try:
        with Session(engine, autoflush=True, expire_on_commit=False) as db:
            variant = db.query(DocumentVariant).filter_by(document_id=doc_id).one()
            version = db.query(DocumentVersion).filter_by(document_variant_id=variant.id).one()
            if draft_owner == "variant":
                variant.is_active = False
            else:
                version.storage_relative_path = "draft/not-yet-saved.docx"
            pending = Company(legal_name="Unrelated pending company")
            db.add(pending)

            statements, flushes = [], []

            def on_sql(_conn, _cursor, statement, _params, _context, _many):
                statements.append(statement.lstrip().split(None, 1)[0].upper())

            def on_flush(*_args):
                flushes.append(True)
                raise AssertionError("Binary locator GET must not flush operator drafts")

            event.listen(engine, "before_cursor_execute", on_sql)
            event.listen(db, "before_flush", on_flush)
            try:
                locator = service.get_current_document_binary_locator_for_parent(
                    db, document_id=doc_id,
                    expected_parent_scope="case", expected_parent_id=case_id,
                )
            finally:
                event.remove(engine, "before_cursor_execute", on_sql)
                event.remove(db, "before_flush", on_flush)
            assert locator.storage_relative_path == "synthetic/owner.docx"
            assert not flushes
            assert statements and set(statements) <= {"SELECT"}
            assert pending in db.new
            if draft_owner == "variant":
                assert variant.is_active is False
                assert variant in db.dirty
            else:
                assert version.storage_relative_path == "draft/not-yet-saved.docx"
                assert version in db.dirty
            db.rollback()
        with Session(engine) as check:
            assert check.query(Company).count() == 1
            assert check.query(DocumentVariant).one().is_active is True
            assert check.query(DocumentVersion).one().storage_relative_path == "synthetic/owner.docx"
    finally:
        engine.dispose()


def test_locator_rechecks_committed_version_after_cached_identity(tmp_path):
    """A cached clean Version must not authorize a stale storage location."""
    engine, case_id, _, doc_id, _ = _seed_binary(tmp_path, scope="case")
    try:
        with Session(engine, expire_on_commit=False) as cached:
            variant = cached.query(DocumentVariant).filter_by(document_id=doc_id).one()
            version = cached.query(DocumentVersion).filter_by(document_variant_id=variant.id).one()
            assert version.storage_relative_path == "synthetic/owner.docx"
            with Session(engine) as writer:
                committed = writer.get(DocumentVersion, version.id)
                committed.storage_relative_path = "synthetic/updated.docx"
                writer.commit()
            locator = DocumentWorkflowService().get_current_document_binary_locator_for_parent(
                cached, document_id=doc_id,
                expected_parent_scope="case", expected_parent_id=case_id,
            )
            assert locator.storage_relative_path == "synthetic/updated.docx"
            # A locator GET does not need to change caller's cached ORM identity.
            assert version.storage_relative_path == "synthetic/owner.docx"
            cached.rollback()
    finally:
        engine.dispose()
