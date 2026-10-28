"""Integration evidence for exact output lineage on PostgreSQL UUID columns.

All rows are created inside a disposable, rolled-back transaction. No
storage service or production data is read or modified.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState, DocumentGenerationStatus, DocumentVariantType
from backend.app.db.models.phase1 import (
    Case, Company, Document, DocumentGenerationRun, DocumentVariant,
    DocumentVersion, Site,
)
from backend.app.document.output_reconciliation import (
    OutputLocator, reconcile_output_locators,
)


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip("requires PostgreSQL test database", allow_module_level=True)


def test_reconciliation_uses_typed_uuid_and_exact_locator_on_postgres():
    engine = create_engine(DATABASE_URL, future=True)
    token = uuid4().hex
    path = f"output-reconciliation/{token}/candidate.docx"
    try:
        with Session(engine, autoflush=False) as session:
            company = Company(legal_name=f"Reconciliation Co {token}")
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name=f"Reconciliation Site {token}")
            session.add(site)
            session.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            session.add(case)
            session.flush()
            document = Document(
                family_code="OUTPUT_RECONCILIATION_TEST",
                document_type_code="output_reconciliation_test",
                title="Output reconciliation test",
                case_id=case.id,
            )
            session.add(document)
            session.flush()
            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            version = DocumentVersion(
                document_variant_id=variant.id, version_no=1,
                storage_binding_id=None,
                storage_root="inspection", storage_relative_path=path,
                original_filename="candidate.docx",
                checksum_sha256=None, is_current=False, issued_on=None,
            )
            session.add(version)
            session.flush()
            run = DocumentGenerationRun(
                document_id=document.id, document_variant_id=variant.id,
                template_binding_id=None, template_definition_id=None,
                output_document_version_id=version.id,
                status=DocumentGenerationStatus.PENDING,
                source_application="Word", requested_by_user_id=None,
                input_payload_redacted="{}", error_summary=None,
                idempotency_key=f"output-reconciliation-{token}",
            )
            session.add(run)
            session.flush()

            report = reconcile_output_locators(session, [
                OutputLocator("inspection", path),
                OutputLocator("dkkd", path),
            ])
            missing, matched = report.items
            assert missing.locator.root == "dkkd"
            assert missing.classification == "no_exact_document_version_reference"
            assert missing.review_flags == ("no_exact_db_reference",)
            assert matched.locator.root == "inspection"
            assert matched.classification == "registered_exact_document_version_locator"
            assert matched.versions[0].version_id == str(version.id)
            assert matched.versions[0].generation_run_ids == (str(run.id),)
            assert matched.versions[0].generation_run_statuses == ("pending",)
            assert matched.review_flags == (
                "checksum_not_recorded", "generation_run_not_succeeded",
            )
            assert report.db_snapshot_consistency == "caller_transaction_unverified"
            assert report.deletion_authorized is False
            # The caller retains ownership of the transaction and rolls back.
            session.rollback()
        with Session(engine) as verify:
            assert verify.get(DocumentVersion, version.id) is None
            verify.rollback()
    finally:
        engine.dispose()
