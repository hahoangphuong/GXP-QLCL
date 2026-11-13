"""Canonical PCT/CT round document content: only persisted links authorize bytes.

No filename, stage, Case-level inventory or completion-date inference. Reuse
existing document locator, checksum verification and per-request RBAC.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.api.routers.document import register_document_routes
from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, Document, DocumentVariant, DocumentVersion,
    InspectionApprovalDocumentLink, InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService


class SyntheticStorage:
    def __init__(self, content: bytes):
        self.content = content

    def exists(self, path, *, root):
        assert (root, path) == ("inspection", "synthetic/pct.pdf")
        return True

    @contextmanager
    def read_stream(self, path, *, root):
        assert (root, path) == ("inspection", "synthetic/pct.pdf")
        yield BytesIO(self.content)


@pytest.fixture
def boundary():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    data = b"%PDF-1.4\nsynthetic-pct-content\n"
    with Session(engine) as session:
        company = Company(legal_name="Synthetic PCT operator")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name="Synthetic PCT Site")
        session.add(site)
        session.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        other_case = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
        session.add_all([case, other_case])
        session.flush()
        pct1 = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=1)
        pct2 = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=2)
        other_pct = InspectionApprovalSubmission(case_id=other_case.id, stage="PCT", round_no=1)
        doc = Document(
            case_id=case.id, family_code="INSPECTION_PT_PCT",
            document_type_code="INSPECTION_PT_PCT", title="PCT 1",
        )
        unbound = Document(
            case_id=case.id, family_code="INSPECTION_PT_PCT",
            document_type_code="INSPECTION_PT_PCT", title="Unbound PCT",
        )
        session.add_all([pct1, pct2, other_pct, doc, unbound])
        session.flush()
        variant = DocumentVariant(
            document_id=doc.id, variant_type=DocumentVariantType.EDITABLE_DOCX,
            is_active=True,
        )
        session.add(variant)
        session.flush()
        session.add(DocumentVersion(
            document_variant_id=variant.id, version_no=1, is_current=True,
            storage_root="inspection", storage_relative_path="synthetic/pct.pdf",
            original_filename="pct.pdf", checksum_sha256=sha256(data).hexdigest(),
        ))
        session.flush()
        ids = dict(
            pct1=pct1.id, pct2=pct2.id, other_pct=other_pct.id,
            doc=doc.id, unbound=unbound.id, case=case.id,
        )
        session.commit()
    app = FastAPI()
    register_document_routes(app, lambda: None)
    path = "/approval-submissions/{approval_submission_id}/documents/{document_id}/content"
    matches = [r for r in app.routes if getattr(r, "path", None) == path]
    assert len(matches) == 1 and matches[0].methods == {"GET"}
    try:
        yield engine, ids, matches[0].endpoint, SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(storage_service=SyntheticStorage(data)))
        ), data
    finally:
        engine.dispose()


def _reader():
    return build_authenticated_user("synthetic-pct-reader", permissions={"document.read"})


def _bind(engine, ids):
    with Session(engine) as session:
        CaseWorkflowService().bind_approval_document(
            session, approval_submission_id=ids["pct1"], document_id=ids["doc"],
            expected_version=1, reason="Synthetic association",
            user=build_authenticated_user("synthetic-pct-editor", "manager"),
        )
        session.commit()


async def _content(response):
    return b"".join([part async for part in response.body_iterator])


def _counts(session):
    return (
        session.scalar(select(func.count(InspectionApprovalDocumentLink.id))),
        session.scalar(select(func.count(AuditEvent.id))),
    )


def test_round_open_requires_explicit_link_not_case_inventory(boundary):
    engine, ids, endpoint, request, _ = boundary
    with Session(engine) as session:
        for round_id, document_id in (
            (ids["pct1"], ids["doc"]),
            (ids["pct2"], ids["doc"]),
            (ids["other_pct"], ids["doc"]),
            (ids["pct1"], ids["unbound"]),
        ):
            with pytest.raises(HTTPException) as exc:
                endpoint(
                    approval_submission_id=round_id, document_id=document_id,
                    request=request, session=session, user=_reader(),
                )
            assert exc.value.status_code == 404
        assert _counts(session) == (0, 0)


def test_bound_round_open_reuses_verified_binary_and_does_not_write(boundary):
    engine, ids, endpoint, request, data = boundary
    _bind(engine, ids)
    with Session(engine) as session:
        before = _counts(session)
        response = endpoint(
            approval_submission_id=ids["pct1"], document_id=ids["doc"],
            request=request, session=session, user=_reader(),
        )
        assert asyncio.run(_content(response)) == data
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.media_type == "application/pdf"
        assert _counts(session) == before == (1, 1)
        assert not session.new and not session.dirty
        with pytest.raises(HTTPException) as wrong_round:
            endpoint(
                approval_submission_id=ids["pct2"], document_id=ids["doc"],
                request=request, session=session, user=_reader(),
            )
        assert wrong_round.value.status_code == 404


def test_round_open_requires_document_read_before_source_lookup(boundary):
    engine, ids, endpoint, request, _ = boundary
    _bind(engine, ids)
    with Session(engine) as session:
        with pytest.raises(HTTPException) as denied:
            endpoint(
                approval_submission_id=ids["pct1"], document_id=ids["doc"],
                request=request, session=session,
                user=build_authenticated_user("denied", permissions={"inspection.edit"}),
            )
        assert denied.value.status_code == 403
        assert _counts(session) == (1, 1)


def test_round_open_fails_closed_on_source_corruption_or_binary_mismatch(boundary):
    engine, ids, endpoint, request, _ = boundary
    _bind(engine, ids)
    # Retained exact persisted link is not enough if bytes have changed.
    request.app.state.storage_service = SyntheticStorage(b"not-the-canonical-binary")
    with Session(engine) as session:
        with pytest.raises(HTTPException) as bad_checksum:
            endpoint(
                approval_submission_id=ids["pct1"], document_id=ids["doc"],
                request=request, session=session, user=_reader(),
            )
        assert bad_checksum.value.status_code == 409
    # Simulate legacy inconsistent source in disposable SQLite (the real
    # PostgreSQL migration 0030 rejects this change at the DB boundary).
    with Session(engine) as tamper:
        tamper.get(Document, ids["doc"]).family_code = "INSPECTION_PT_CT"
        tamper.commit()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as invalid_owner:
            endpoint(
                approval_submission_id=ids["pct1"], document_id=ids["doc"],
                request=request, session=session, user=_reader(),
            )
        assert invalid_owner.value.status_code == 409
        assert _counts(session) == (1, 1)
