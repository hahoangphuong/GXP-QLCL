"""PostgreSQL-only concurrency gate for the typed KHKT Case CREATE owner.

Uses a fresh private CI schema and separate transactions. No template/storage
bytes, production/rehearsal tables, or actual document rendering are touched.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    Case,
    Company,
    Document,
    DocumentVariant,
    DocumentVersion,
    Site,
)
from backend.app.services.document_api import DocumentWorkflowService


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires isolated PostgreSQL transaction locks", allow_module_level=True)


def test_typed_and_generic_khkt_render_serialize_on_case_and_observe_committed_version():
    """A competing generic render blocks before any mutation, then sees HTTP 409.

    First transaction holds Case row FOR UPDATE while the second attempts the
    generic render entrypoint with a bounded lock timeout. The winner then commits a
    fully locatable KHKT document version. The retry must see that committed
    version and reject creation instead of issuing another render payload.
    """
    # Protect operational databases even when someone invokes this test with
    # an inherited DATABASE_URL outside GitHub's disposable PostgreSQL job.
    database_name = make_url(DATABASE_URL).database
    if database_name != "gxp_qlcl_test":
        pytest.fail(
            "KHKT concurrency test requires the CI disposable gxp_qlcl_test "
            f"database; received {database_name!r}. No database mutations performed."
        )

    schema = "khkt_lock_ci_" + uuid4().hex
    admin = create_engine(DATABASE_URL, future=True)
    engine = None
    blocker = contender = None
    schema_created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True
        engine = create_engine(
            DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
            future=True,
        )
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM pg_tables "
                    "WHERE schemaname = :schema AND tablename = 'case'"
                ),
                {"schema": schema},
            ) == 1
        factory = sessionmaker(
            bind=engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        with factory() as seed:
            company = Company(legal_name="KHKT concurrent synthetic company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="KHKT synthetic site")
            seed.add(site)
            seed.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.DRAFT)
            seed.add_all([case, other])
            seed.commit()
            case_id, other_id = case.id, other.id

        service = DocumentWorkflowService()
        blocker = factory()
        first = service.build_case_inspection_plan_render_payload(
            blocker, case_id=case_id, idempotency_key="khkt-first",
        )
        assert first["case_id"] == case_id
        assert first["gxp_type"] == "GMP"
        assert first["family_code"] == "INSPECTION_KE_HOACH_KT"

        generic_payload = {
            "family_code": "INSPECTION_KE_HOACH_KT",
            "case_id": case_id,
            "gxp_type": "GMP",
            "storage_scope": "inspection_folder",
            "idempotency_key": "generic-competing-create",
            "output_filename": "3. Kế hoạch kiểm tra GMP.docx",
            "payload": {},
            "strict_payload": True,
        }
        generic_user = build_authenticated_user(
            "unpersisted-khkt-generic", permissions={"document.write"},
        )

        contender = factory()
        contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = contender.connection()
        contender_mutations: list[str] = []

        def capture_mutations(connection, cursor, statement, parameters, context, executemany):
            if connection is contender_connection and statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            ):
                contender_mutations.append(statement)

        event.listen(engine, "before_cursor_execute", capture_mutations)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                service.render_template_docx(
                    contender,
                    storage=object(),
                    payload=generic_payload,
                    user=generic_user,
                )
        finally:
            event.remove(engine, "before_cursor_execute", capture_mutations)
            contender.rollback()
        assert contender_mutations == [], "competing CREATE must not mutate before Case lock"

        # Locking is scoped to this Case, not a global KHKT family lock.
        contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
        other_payload = service.build_case_inspection_plan_render_payload(
            contender, case_id=other_id, idempotency_key="khkt-unrelated",
        )
        assert other_payload["case_id"] == other_id
        assert other_payload["gxp_type"] == "GLP"
        contender.rollback()

        # Simulate the winner's committed render lineage while it owns the
        # Case lock. This test intentionally does not touch StorageService.
        document = Document(
            family_code="INSPECTION_KE_HOACH_KT",
            document_type_code="INSPECTION_KE_HOACH_KT",
            case_id=case_id,
        )
        blocker.add(document)
        blocker.flush()
        variant = DocumentVariant(
            document_id=document.id,
            variant_type=DocumentVariantType.EDITABLE_DOCX,
            language_code="vi",
        )
        blocker.add(variant)
        blocker.flush()
        winner_version = DocumentVersion(
            document_variant_id=variant.id,
            version_no=1,
            storage_root="inspection",
            storage_relative_path="synthetic/khkt-winner.docx",
            original_filename="Synthetic KHKT.docx",
            checksum_sha256="a" * 64,
            is_current=True,
        )
        blocker.add(winner_version)
        blocker.commit()

        with pytest.raises(HTTPException, match="already exists") as conflict:
            service.render_template_docx(
                contender,
                storage=object(),
                payload=generic_payload,
                user=generic_user,
            )
        assert conflict.value.status_code == 409
        contender.rollback()

        with factory() as verify:
            documents = list(
                verify.scalars(select(Document).where(
                    Document.case_id == case_id,
                    Document.family_code == "INSPECTION_KE_HOACH_KT",
                ))
            )
            assert len(documents) == 1
            versions = list(
                verify.scalars(
                    select(DocumentVersion)
                    .join(DocumentVariant)
                    .where(DocumentVariant.document_id == documents[0].id)
                )
            )
            assert len(versions) == 1
            assert versions[0].is_current is True
            assert versions[0].storage_relative_path == "synthetic/khkt-winner.docx"
    finally:
        if contender is not None:
            contender.rollback()
            contender.close()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        if engine is not None:
            engine.dispose()
        try:
            if schema_created:
                with admin.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            admin.dispose()
