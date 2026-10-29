"""Real PostgreSQL: a successful file write is not an atomic database commit.

All records use a disposable CI database and are explicitly removed. The
physical target is isolated under pytest tmp_path, never NAS or production.
"""
from __future__ import annotations

import os
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState, DocumentGenerationStatus, DocumentVariantType
from backend.app.db.models.phase1 import (
    Case, Company, Document, DocumentGenerationRun, DocumentVariant,
    DocumentVersion, Site,
)
from backend.app.document.output_reconciliation import (
    OutputLocator, reconcile_output_locators,
)
from backend.app.document.output_version import (
    OutputVersionAllocation, finalize_output_document_version_write,
)
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig, StorageTargetExistsError


DATABASE_URL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="requires disposable PostgreSQL integration database",
)


@pytest.mark.parametrize("retry_scenario", ["identical", "different", "externally_replaced"])
@pytest.mark.parametrize("first_attempt", ["successful_flush", "write_then_raise", "checksum_raises", "checksum_mismatch", "db_flush_then_raise"])
def test_file_remains_after_successful_finalization_when_caller_rolls_back(tmp_path, retry_scenario, first_attempt, monkeypatch):
    assert DATABASE_URL.startswith("postgresql")
    engine = create_engine(DATABASE_URL, future=True)
    token = uuid4().hex
    inspection_root = tmp_path / "inspection"
    inspection_root.mkdir()
    storage = FilesystemStorageService(StorageConfig(inspection_root=inspection_root))
    path = f"rollback-gap/{token}/rendered.docx"
    payload = b"test-only-finalized-file-not-a-legally-issued-document"
    ids = {}
    try:
        # Commit the allocation metadata first, simulating a separately
        # persisted pending generation before render/finalization.
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            company = Company(legal_name=f"Rollback gap company {token}")
            session.add(company)
            session.flush()
            ids["company"] = company.id
            site = Site(company_id=company.id, site_name=f"Rollback gap site {token}")
            session.add(site)
            session.flush()
            ids["site"] = site.id
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            session.add(case)
            session.flush()
            ids["case"] = case.id
            document = Document(
                family_code="OUTPUT_ROLLBACK_GAP_TEST",
                document_type_code="output_rollback_gap_test",
                title="Output rollback gap integration",
                case_id=case.id,
            )
            session.add(document)
            session.flush()
            ids["document"] = document.id
            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            ids["variant"] = variant.id
            version = DocumentVersion(
                document_variant_id=variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=path,
                original_filename="rendered.docx",
                checksum_sha256=None,
                is_current=False,
                issued_on=None,
            )
            session.add(version)
            session.flush()
            ids["version"] = version.id
            run = DocumentGenerationRun(
                document_id=document.id,
                document_variant_id=variant.id,
                template_binding_id=None,
                template_definition_id=None,
                output_document_version_id=version.id,
                status=DocumentGenerationStatus.PENDING,
                source_application="Word",
                requested_by_user_id=None,
                input_payload_redacted="{}",
                error_summary=None,
                idempotency_key=f"output-rollback-gap-{token}",
            )
            session.add(run)
            session.flush()
            ids["run"] = run.id
            session.commit()

        allocation = OutputVersionAllocation(
            document_id=ids["document"],
            document_variant_id=ids["variant"],
            document_version_id=ids["version"],
            generation_run_id=ids["run"],
            version_no=1,
            storage_root="inspection",
            storage_relative_path=path,
            original_filename="rendered.docx",
            storage_binding_id=None,
        )

        # A published target remains outside the database transaction
        # whether the caller rolls back or the storage checksum path fails.
        original_write = storage.write_stream
        original_checksum = storage.checksum
        if first_attempt == "write_then_raise":
            def write_then_raise(*args, **kwargs):
                original_write(*args, **kwargs)
                raise OSError("injected post-publication write failure")
            monkeypatch.setattr(storage, "write_stream", write_then_raise)
        elif first_attempt == "checksum_raises":
            def checksum_raises(*args, **kwargs):
                raise OSError("injected checksum failure")
            monkeypatch.setattr(storage, "checksum", checksum_raises)
        elif first_attempt == "checksum_mismatch":
            monkeypatch.setattr(storage, "checksum", lambda *args, **kwargs: "0" * 64)

        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            if first_attempt == "db_flush_then_raise":
                original_flush = session.flush
                def db_flush_then_raise(*args, **kwargs):
                    # SQL flush has reached PostgreSQL, but the caller
                    # observes an error before the transaction commits.
                    original_flush(*args, **kwargs)
                    assert session.get(DocumentGenerationRun, ids["run"]).status == (
                        DocumentGenerationStatus.SUCCEEDED
                    )
                    raise OSError("injected failure after SQL flush")
                monkeypatch.setattr(session, "flush", db_flush_then_raise)
            if first_attempt == "successful_flush":
                result = finalize_output_document_version_write(
                    session, storage, allocation, binary_payload=payload,
                )
                assert result == sha256(payload).hexdigest()
                assert session.get(DocumentGenerationRun, ids["run"]).status == (
                    DocumentGenerationStatus.SUCCEEDED
                )
            else:
                with pytest.raises((OSError, RuntimeError)):
                    finalize_output_document_version_write(
                        session, storage, allocation, binary_payload=payload,
                    )
            assert (inspection_root / path).read_bytes() == payload
            session.rollback()

        monkeypatch.setattr(storage, "write_stream", original_write)
        monkeypatch.setattr(storage, "checksum", original_checksum)

        # A retry cannot adopt an existing target regardless of payload
        # equality, nor assume a competing writer kept the same bytes.
        # The replacement scenario simulates a separate writer, not an
        # authorized cleanup or overwrite by the document pipeline.
        retry_payload = payload
        expected_physical_bytes = payload
        if retry_scenario == "different":
            retry_payload = b"different-rendered-document-not-issued"
        elif retry_scenario == "externally_replaced":
            expected_physical_bytes = b"independent-writer-replaced-path"
            (inspection_root / path).write_bytes(expected_physical_bytes)
        with Session(engine, autoflush=False, expire_on_commit=False) as retry:
            with pytest.raises(StorageTargetExistsError):
                finalize_output_document_version_write(
                    retry, storage, allocation, binary_payload=retry_payload,
                )
            retry.rollback()
        assert (inspection_root / path).read_bytes() == expected_physical_bytes

        # DB and storage have now diverged. Never infer physical ownership
        # from the DB-only reconciliation report or attempt cleanup.
        assert (inspection_root / path).read_bytes() == expected_physical_bytes
        with Session(engine, autoflush=False) as session:
            version = session.get(DocumentVersion, ids["version"])
            run = session.get(DocumentGenerationRun, ids["run"])
            assert version.checksum_sha256 is None
            assert version.is_current is False
            assert version.issued_on is None
            assert run.status == DocumentGenerationStatus.PENDING

            report = reconcile_output_locators(
                session, [OutputLocator("inspection", path)],
            )
            item = report.items[0]
            assert item.classification == "registered_exact_document_version_locator"
            assert "checksum_not_recorded" in item.review_flags
            assert "generation_run_not_succeeded" in item.review_flags
            assert item.physical_storage_state == "not_observed"
            assert report.physical_generation_ownership == "unverified"
            assert report.cleanup_verdict == "not_evaluated"
            assert report.deletion_authorized is False
            session.rollback()
    finally:
        if ids:
            with Session(engine) as cleanup:
                for table, key in (
                    (DocumentGenerationRun, "run"),
                    (DocumentVersion, "version"),
                    (DocumentVariant, "variant"),
                    (Document, "document"),
                    (Case, "case"),
                    (Site, "site"),
                    (Company, "company"),
                ):
                    if key in ids:
                        cleanup.execute(delete(table).where(table.id == ids[key]))
                cleanup.commit()
        engine.dispose()
