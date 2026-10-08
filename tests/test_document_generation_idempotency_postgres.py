from __future__ import annotations

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case,
    Company,
    Document,
    DocumentGenerationRun,
    DocumentVariant,
    Site,
)
from backend.app.document.persistence import (
    DocumentPersistenceError,
    prepare_generation_persistence,
)
from backend.app.document.service_contract import (
    DocumentGenerationPlan,
    DocumentGenerationRequest,
    DocumentPayloadEnvelope,
    DocumentPayloadField,
    TemplateSelectionResult,
)


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires PostgreSQL advisory transaction locks", allow_module_level=True)


def test_concurrent_same_key_preparation_waits_before_document_mutations():
    engine = create_engine(DATABASE_URL, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    token = uuid4().hex
    company_id = site_id = case_id = None
    blocker = contender = None
    try:
        with factory() as seed:
            company = Company(legal_name=f"Idempotency Prepare Co {token}")
            seed.add(company)
            seed.flush()
            company_id = company.id

            site = Site(company_id=company.id, site_name=f"Prepare Site {token}")
            seed.add(site)
            seed.flush()
            site_id = site.id

            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.DRAFT,
            )
            seed.add(case)
            seed.commit()
            case_id = case.id

        plan = DocumentGenerationPlan(
            request=DocumentGenerationRequest(
                family_code="IDEMPOTENCY_CONCURRENT_TEST",
                requested_by_user_id=None,
                case_id=case_id,
                storage_scope="inspection_folder",
                idempotency_key=f"same-key-{token}",
            ),
            template=TemplateSelectionResult(
                family_code="IDEMPOTENCY_CONCURRENT_TEST",
                logical_name="Concurrent preparation",
                template_pattern="concurrent-preparation.dotx",
                source_application="Word",
                storage_scope="inspection_folder",
                host_procedure="Prepare.Test",
                population_procedures=(),
                bookmarks=(),
                copy_forward_dependencies=(),
            ),
            payload=DocumentPayloadEnvelope(
                family_code="IDEMPOTENCY_CONCURRENT_TEST",
                fields=(),
                source_procedures=(),
            ),
            source_dependencies=(),
        )

        blocker = factory()
        first = prepare_generation_persistence(blocker, plan)
        assert first.reused_generation_run is False
        # Keep the first preparation uncommitted so no row with this key is
        # visible to a different connection yet.
        contender = factory()
        contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
        contender_connection = contender.connection()
        contender_mutations: list[str] = []

        def record_contender_sql(conn, cursor, statement, parameters, context, executemany):
            if conn is contender_connection and statement.lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            ):
                contender_mutations.append(statement)

        event.listen(engine, "before_cursor_execute", record_contender_sql)
        try:
            with pytest.raises(OperationalError, match="lock timeout"):
                prepare_generation_persistence(contender, plan)
        finally:
            event.remove(engine, "before_cursor_execute", record_contender_sql)
            contender.rollback()

        # The loser must block at the idempotency owner, not after creating a
        # second document/variant shell and colliding on run uniqueness.
        assert contender_mutations == []

        blocker.commit()

        reused = prepare_generation_persistence(contender, plan)
        assert reused.reused_generation_run is True
        assert reused.generation_run_id == first.generation_run_id
        assert reused.document_id == first.document_id
        assert reused.document_variant_id == first.document_variant_id
        contender.commit()

        # The same key with a genuinely different request still fails closed.
        different_payload = replace(
            plan,
            payload=DocumentPayloadEnvelope(
                family_code=plan.payload.family_code,
                fields=(DocumentPayloadField("changed", "value", "test"),),
                source_procedures=(),
            ),
        )
        with pytest.raises(DocumentPersistenceError, match="different request"):
            prepare_generation_persistence(contender, different_payload)
        contender.rollback()

        with factory() as verify:
            runs = list(
                verify.scalars(
                    select(DocumentGenerationRun).where(
                        DocumentGenerationRun.idempotency_key == plan.request.idempotency_key
                    )
                )
            )
            assert len(runs) == 1
            assert runs[0].id == first.generation_run_id
            documents = list(
                verify.scalars(
                    select(Document).where(
                        Document.family_code == plan.request.family_code,
                        Document.case_id == case_id,
                    )
                )
            )
            assert len(documents) == 1
    finally:
        if contender is not None:
            contender.rollback()
            contender.close()
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        with factory() as cleanup:
            if case_id is not None:
                docs = list(
                    cleanup.scalars(
                        select(Document).where(
                            Document.case_id == case_id,
                            Document.family_code == "IDEMPOTENCY_CONCURRENT_TEST",
                        )
                    )
                )
                for document in docs:
                    cleanup.execute(
                        delete(DocumentGenerationRun).where(
                            DocumentGenerationRun.document_id == document.id
                        )
                    )
                    cleanup.execute(
                        delete(DocumentVariant).where(DocumentVariant.document_id == document.id)
                    )
                    cleanup.delete(document)
                cleanup.flush()
                cleanup.execute(delete(Case).where(Case.id == case_id))
            if site_id is not None:
                cleanup.execute(delete(Site).where(Site.id == site_id))
            if company_id is not None:
                cleanup.execute(delete(Company).where(Company.id == company_id))
            cleanup.commit()
        engine.dispose()
