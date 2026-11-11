"""Two-session owner revalidation for canonical Document binary locators.

A locator is a sensitive read, even without opening the underlying bytes.
Never authorize it from Document or CAPA owner identities cached before
another committed business-owner change.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import create_engine
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
