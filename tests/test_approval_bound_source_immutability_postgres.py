"""PostgreSQL gate for immutable PCT/CT association source identities.

Runs only in a fresh isolated schema of loopback gxp_qlcl_test.
Never writes rehearsal, go-live or another externally hosted DB.
"""
from __future__ import annotations

from importlib import import_module
import os
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, Document, InspectionApprovalDocumentLink,
    InspectionApprovalSubmission, Site,
)
from backend.app.services.workflow import CaseWorkflowService

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires disposable PostgreSQL", allow_module_level=True)

MIGRATION = "migrations.versions.20261113_0030_approval_bound_source_immutability"


def _apply_migration(connection, direction):
    module = import_module(MIGRATION)
    previous = module.op
    module.op = Operations(MigrationContext.configure(connection))
    try:
        getattr(module, direction)()
    finally:
        module.op = previous


@pytest.fixture
def bound_db():
    url = make_url(DATABASE_URL)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "gxp_qlcl_test":
        pytest.fail("Requires loopback disposable gxp_qlcl_test; no writes performed.")
    schema = "bound_source_guard_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(
            DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            _apply_migration(conn, "upgrade")
        factory = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False, future=True,
        )
        with factory() as session:
            company = Company(legal_name="Bound Source " + schema)
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name="Synthetic bound source")
            session.add(site)
            session.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
            session.add_all([case, other])
            session.flush()
            pct = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=1)
            other_pct = InspectionApprovalSubmission(case_id=other.id, stage="PCT", round_no=1)
            document = Document(
                case_id=case.id, family_code="INSPECTION_PT_PCT",
                document_type_code="INSPECTION_PT_PCT", title="Synthetic bound PCT",
            )
            unbound = Document(
                case_id=case.id, family_code="INSPECTION_PT_PCT",
                document_type_code="INSPECTION_PT_PCT", title="Unbound PCT",
            )
            session.add_all([pct, other_pct, document, unbound])
            session.flush()
            ids = {
                "case": case.id, "other": other.id, "pct": pct.id,
                "other_pct": other_pct.id, "document": document.id, "unbound": unbound.id,
            }
            session.commit()
        with factory() as session:
            bound = CaseWorkflowService().bind_approval_document(
                session, approval_submission_id=ids["pct"],
                document_id=ids["document"], expected_version=1,
                reason="Synthetic association identity proof",
                user=build_authenticated_user("bound-source-pg", "manager"),
            )
            assert bound["created"] is True
            ids["binding"] = bound["binding_id"]
            session.commit()
        yield factory, ids, engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize(
    "column,value",
    [
        ("case_id", "other"),
        ("family_code", "INSPECTION_PT_CT"),
        ("capa_cycle_id", "other"),
        ("certificate_id", "other"),
        ("business_eligibility_certificate_id", "other"),
        ("change_request_id", "other"),
    ],
)
def test_bound_document_source_cannot_change_after_binding(bound_db, column, value):
    factory, ids, _ = bound_db
    new_value = ids[value] if value == "other" else value
    with factory() as session:
        with pytest.raises(IntegrityError, match="APPROVAL_BOUND_DOCUMENT_SOURCE_IMMUTABLE"):
            session.execute(
                update(Document).where(Document.id == ids["document"])
                .values(**{column: new_value})
            )
            session.commit()
        session.rollback()
    with factory() as verify:
        document = verify.get(Document, ids["document"])
        assert document.case_id == ids["case"]
        assert document.family_code == "INSPECTION_PT_PCT"
        assert document.capa_cycle_id is None
        assert document.certificate_id is None
        assert document.business_eligibility_certificate_id is None
        assert document.change_request_id is None
        assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1


@pytest.mark.parametrize("column,value", [
    ("case_id", "other"),
    ("stage", "CT"),
    ("round_no", 2),
])
def test_bound_submission_case_stage_and_round_are_immutable(bound_db, column, value):
    factory, ids, _ = bound_db
    next_value = ids[value] if value == "other" else value
    with factory() as session:
        with pytest.raises(IntegrityError, match="APPROVAL_BOUND_SUBMISSION_IDENTITY_IMMUTABLE"):
            session.execute(
                update(InspectionApprovalSubmission)
                .where(InspectionApprovalSubmission.id == ids["pct"])
                .values(**{column: next_value})
            )
            session.commit()
        session.rollback()
    with factory() as verify:
        submission = verify.get(InspectionApprovalSubmission, ids["pct"])
        assert (submission.case_id, submission.stage, submission.round_no) == (
            ids["case"], "PCT", 1,
        )
        assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1


@pytest.mark.parametrize("action", ["reassign_document", "reassign_submission", "delete_link"])
def test_binding_record_is_append_only(bound_db, action):
    factory, ids, _ = bound_db
    with factory() as session:
        with pytest.raises(IntegrityError, match="APPROVAL_DOCUMENT_LINK_APPEND_ONLY"):
            if action == "reassign_document":
                session.execute(
                    update(InspectionApprovalDocumentLink)
                    .where(InspectionApprovalDocumentLink.id == ids["binding"])
                    .values(document_id=ids["unbound"])
                )
            elif action == "reassign_submission":
                session.execute(
                    update(InspectionApprovalDocumentLink)
                    .where(InspectionApprovalDocumentLink.id == ids["binding"])
                    .values(approval_submission_id=ids["other_pct"])
                )
            else:
                session.execute(
                    delete(InspectionApprovalDocumentLink)
                    .where(InspectionApprovalDocumentLink.id == ids["binding"])
                )
            session.commit()
        session.rollback()
    with factory() as verify:
        link = verify.get(InspectionApprovalDocumentLink, ids["binding"])
        assert link.approval_submission_id == ids["pct"]
        assert link.document_id == ids["document"]
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1


def test_guard_allows_metadata_and_unbound_source_changes(bound_db):
    factory, ids, _ = bound_db
    with factory() as session:
        # Ordinary editing and approval completion still have their prior owners.
        session.execute(
            update(Document).where(Document.id == ids["document"])
            .values(title="Edited display title only")
        )
        session.execute(
            update(Document).where(Document.id == ids["unbound"])
            .values(case_id=ids["other"], family_code="INSPECTION_PT_CT")
        )
        session.execute(
            update(InspectionApprovalSubmission)
            .where(InspectionApprovalSubmission.id == ids["pct"])
            .values(reference="PCT reference edit")
        )
        session.commit()
    with factory() as verify:
        assert verify.get(Document, ids["document"]).title == "Edited display title only"
        unbound = verify.get(Document, ids["unbound"])
        assert unbound.case_id == ids["other"]
        assert unbound.family_code == "INSPECTION_PT_CT"
        assert verify.get(InspectionApprovalSubmission, ids["pct"]).reference == "PCT reference edit"


def test_downgrade_removes_only_protective_triggers_without_rewriting_links(bound_db):
    factory, ids, engine = bound_db
    with engine.begin() as connection:
        _apply_migration(connection, "downgrade")
    with factory() as session:
        session.execute(
            update(Document).where(Document.id == ids["document"])
            .values(case_id=ids["other"])
        )
        session.commit()
    with factory() as verify:
        assert verify.get(Document, ids["document"]).case_id == ids["other"]
        assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
        assert verify.scalar(select(func.count(AuditEvent.id))) == 1
    with engine.begin() as connection:
        _apply_migration(connection, "upgrade")
    with factory() as verify:
        assert verify.scalar(select(func.count(InspectionApprovalDocumentLink.id))) == 1
