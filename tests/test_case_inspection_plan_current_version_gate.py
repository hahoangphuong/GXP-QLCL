"""Typed KHKT CREATE state must match canonical Case OPEN/HISTORY state.

The query and contextual action read are exercised against an actual SQLAlchemy
database; no storage, template or real Case is touched.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    Case, Company, Document, DocumentVariant, DocumentVersion, Site,
)
from backend.app.services.catalog import CatalogReadService
from backend.app.services.document_api import DocumentWorkflowService

FAMILY = "INSPECTION_KE_HOACH_KT"


def _case_and_document(tmp_path, *, gxp_type="GMP", document_state="none"):
    engine = create_engine(
        f"sqlite:///{(tmp_path / ('typed-khkt-' + document_state + '.sqlite')).as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = Company(legal_name="Test company", short_name="KHKT")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Test facility")
        session.add(site)
        session.flush()
        case = Case(
            site_id=site.id,
            gxp_type=gxp_type,
            state=CaseState.DRAFT,
            opened_year=2026,
        )
        session.add(case)
        session.flush()
        case_id = case.id

        if document_state != "none":
            other_case = None
            if document_state == "other_case":
                other_case = Case(
                    site_id=site.id,
                    gxp_type=gxp_type,
                    state=CaseState.DRAFT,
                    opened_year=2026,
                )
                session.add(other_case)
                session.flush()

            doc = Document(
                family_code="INSPECTION_QD_KT" if document_state == "other_family" else FAMILY,
                document_type_code="INSPECTION_QD_KT" if document_state == "other_family" else FAMILY,
                case_id=other_case.id if other_case is not None else case_id,
            )
            session.add(doc)
            session.flush()
            variant = DocumentVariant(
                document_id=doc.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
            )
            session.add(variant)
            session.flush()
            version = DocumentVersion(
                document_variant_id=variant.id,
                version_no=1,
                storage_root="inspection",
                storage_relative_path="synthetic/khkt.docx",
                original_filename="Kế hoạch kiểm tra.docx",
                checksum_sha256="a" * 64,
                is_current=document_state not in {"not_current"},
            )
            if document_state == "missing_checksum":
                version.checksum_sha256 = None
            if document_state == "blank_path":
                version.storage_relative_path = "  "
            session.add(version)

        session.commit()
    return engine, case_id


def _create_action(session, case_id):
    user = build_authenticated_user(
        "typed-khkt-test", permissions={"document.read", "document.write"},
    )
    items = CatalogReadService()._build_case_contextual_document_actions(
        session, case_id=case_id, capa_cycles=[], user=user,
    )
    item = next(row for row in items if row["family_code"] == FAMILY)
    return next(action for action in item["actions"] if action["action_key"] == "create")


@pytest.mark.parametrize("document_state", (
    "none",
    "not_current",
    "missing_checksum",
    "blank_path",
    "other_case",
    "other_family",
))
def test_khkt_typed_create_preflight_matches_enabled_case_action(
    tmp_path, document_state,
):
    engine, case_id = _case_and_document(tmp_path, document_state=document_state)
    with Session(engine) as session:
        action = _create_action(session, case_id)
        payload = DocumentWorkflowService.build_case_inspection_plan_render_payload(
            session, case_id=case_id, idempotency_key="new-create",
        )
        assert action["available"] is True
        assert action["create_readiness"] == "READY_CREATE_OPEN_HISTORY"
        assert payload["case_id"] == case_id
        assert payload["family_code"] == FAMILY
        assert payload["idempotency_key"] == "new-create"
        assert payload["strict_payload"] is True


@pytest.mark.parametrize("gxp_type", ("GMP", "GLP", "GMPbb", "GSP"))
def test_khkt_typed_create_rejects_existing_current_document_before_render(
    tmp_path, gxp_type,
):
    engine, case_id = _case_and_document(
        tmp_path, gxp_type=gxp_type, document_state="current",
    )
    with Session(engine) as session:
        action = _create_action(session, case_id)
        assert action["available"] is False
        assert action["create_readiness"] == "READY_OPEN_HISTORY"
        assert "create_endpoint" not in action
        before = list(session.scalars(select(DocumentVersion.id)))
        with pytest.raises(HTTPException, match="already exists") as err:
            DocumentWorkflowService.build_case_inspection_plan_render_payload(
                session, case_id=case_id, idempotency_key="fresh-create",
            )
        assert err.value.status_code == 409
        assert list(session.scalars(select(DocumentVersion.id))) == before
        assert session.new == set()


def test_khkt_typed_create_rejects_unknown_case_before_document_query(tmp_path):
    engine, _ = _case_and_document(tmp_path)
    with Session(engine) as session:
        with pytest.raises(HTTPException, match="not found") as err:
            DocumentWorkflowService.build_case_inspection_plan_render_payload(
                session, case_id="not-a-case", idempotency_key=None,
            )
        assert err.value.status_code == 404
