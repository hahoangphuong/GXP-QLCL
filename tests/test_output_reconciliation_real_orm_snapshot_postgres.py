"""Real-ORM concurrency contract for multi-SELECT output reconciliation.

Disposable PostgreSQL records only. The two SELECTs are separated by a
concurrent committed DocumentGenerationRun status update. No storage access.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
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


class _AfterFirstSelect:
    """Delegate to a real Session while injecting a writer's commit once."""

    def __init__(self, session, writer):
        self.session = session
        self.writer = writer
        self.calls = 0
        self.no_autoflush = session.no_autoflush

    def execute(self, statement):
        rows = self.session.execute(statement)
        self.calls += 1
        if self.calls == 1:
            # Materialize first query before the concurrent write is visible.
            captured = list(rows)
            self.writer()
            return captured
        return rows


@pytest.mark.parametrize(
    ("isolation", "expected_status"),
    [("READ COMMITTED", "succeeded"), ("REPEATABLE READ", "pending")],
)
def test_real_output_reconciliation_observes_caller_isolation(
    isolation, expected_status,
):
    engine = create_engine(DATABASE_URL, future=True)
    token = uuid4().hex
    locator = OutputLocator(
        "inspection", f"snapshot-reconciliation/{token}/output.docx",
    )
    ids = {}
    try:
        with Session(engine) as seed:
            company = Company(legal_name=f"Snapshot Evidence Co {token}")
            seed.add(company)
            seed.flush()
            ids["company"] = company.id
            site = Site(company_id=company.id, site_name=f"Snapshot Site {token}")
            seed.add(site)
            seed.flush()
            ids["site"] = site.id
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            seed.add(case)
            seed.flush()
            ids["case"] = case.id
            document = Document(
                family_code="OUTPUT_SNAPSHOT_EVIDENCE_TEST",
                document_type_code="output_snapshot_evidence",
                title="Output snapshot evidence",
                case_id=case.id,
            )
            seed.add(document)
            seed.flush()
            ids["document"] = document.id
            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            seed.add(variant)
            seed.flush()
            ids["variant"] = variant.id
            version = DocumentVersion(
                document_variant_id=variant.id, version_no=1,
                storage_binding_id=None, storage_root=locator.root,
                storage_relative_path=locator.relative_path,
                original_filename="output.docx",
                checksum_sha256=None, is_current=False, issued_on=None,
            )
            seed.add(version)
            seed.flush()
            ids["version"] = version.id
            run = DocumentGenerationRun(
                document_id=document.id, document_variant_id=variant.id,
                template_binding_id=None, template_definition_id=None,
                output_document_version_id=version.id,
                status=DocumentGenerationStatus.PENDING,
                source_application="Word", requested_by_user_id=None,
                input_payload_redacted="{}", error_summary=None,
                idempotency_key=f"snapshot-reconciliation-{token}",
            )
            seed.add(run)
            seed.flush()
            ids["run"] = run.id
            seed.commit()

        def commit_concurrent_status_change():
            with Session(engine) as writer:
                run = writer.get(DocumentGenerationRun, ids["run"])
                assert run is not None
                run.status = DocumentGenerationStatus.SUCCEEDED
                writer.commit()

        # Caller owns connection isolation and transaction lifetime.
        with engine.connect().execution_options(isolation_level=isolation) as conn:
            with Session(bind=conn, autoflush=False) as reader:
                with reader.begin():
                    report = reconcile_output_locators(
                        _AfterFirstSelect(reader, commit_concurrent_status_change),
                        [locator],
                    )
                    assert report.items[0].versions[0].generation_run_statuses == (
                        expected_status,
                    )
                    assert report.items[0].review_flags == tuple(sorted(
                        ("checksum_not_recorded",)
                        if expected_status == "succeeded"
                        else ("checksum_not_recorded", "generation_run_not_succeeded")
                    ))
                    assert report.db_snapshot_consistency == "caller_transaction_unverified"
                    assert report.deletion_authorized is False
    finally:
        if ids:
            with Session(engine) as cleanup:
                if "run" in ids:
                    cleanup.execute(delete(DocumentGenerationRun).where(
                        DocumentGenerationRun.id == ids["run"]
                    ))
                if "version" in ids:
                    cleanup.execute(delete(DocumentVersion).where(
                        DocumentVersion.id == ids["version"]
                    ))
                if "variant" in ids:
                    cleanup.execute(delete(DocumentVariant).where(
                        DocumentVariant.id == ids["variant"]
                    ))
                if "document" in ids:
                    cleanup.execute(delete(Document).where(
                        Document.id == ids["document"]
                    ))
                if "case" in ids:
                    cleanup.execute(delete(Case).where(Case.id == ids["case"]))
                if "site" in ids:
                    cleanup.execute(delete(Site).where(Site.id == ids["site"]))
                if "company" in ids:
                    cleanup.execute(delete(Company).where(Company.id == ids["company"]))
                cleanup.commit()
        engine.dispose()
