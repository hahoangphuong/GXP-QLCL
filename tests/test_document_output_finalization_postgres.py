from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from backend.app.db.enums import (
    CaseState,
    DocumentGenerationStatus,
    DocumentVariantType,
)
from backend.app.db.models.phase1 import (
    BusinessEligibilityCertificate,
    Case,
    Company,
    Document,
    DocumentGenerationRun,
    DocumentVariant,
    DocumentVersion,
    Site,
)
import backend.app.document.output_version as output_version_module
from backend.app.document.output_version import (
    OutputVersionAllocation,
    allocate_output_document_version,
    finalize_output_document_version_write,
)
from backend.app.services.document_api import DocumentWorkflowService
from backend.app.storage.filesystem import FilesystemStorageService
from backend.app.storage.types import StorageConfig


DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL.startswith("postgresql"):
    pytest.skip(
        "requires PostgreSQL row-lock semantics",
        allow_module_level=True,
    )


def test_output_finalization_serializes_on_document_variant_before_storage_io(tmp_path):
    engine = create_engine(DATABASE_URL, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    token = uuid4().hex
    inspection_root = tmp_path / "inspection"
    inspection_root.mkdir(parents=True, exist_ok=True)
    storage = FilesystemStorageService(
        StorageConfig(inspection_root=inspection_root)
    )

    company_id = site_id = case_id = document_id = variant_id = version_id = run_id = None
    blocker = None
    try:
        with factory() as session:
            company = Company(legal_name=f"Finalization Lock Co {token}")
            session.add(company)
            session.flush()
            company_id = company.id

            site = Site(
                company_id=company.id,
                site_name=f"Finalization Lock Site {token}",
            )
            session.add(site)
            session.flush()
            site_id = site.id

            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.DRAFT,
            )
            session.add(case)
            session.flush()
            case_id = case.id

            document = Document(
                family_code="FINALIZATION_LOCK_TEST",
                document_type_code="finalization_lock_test",
                title="Finalization lock test",
                case_id=case.id,
            )
            session.add(document)
            session.flush()
            document_id = document.id

            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            variant_id = variant.id

            relative_path = f"finalization-lock/{token}/candidate.docx"
            version = DocumentVersion(
                document_variant_id=variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=relative_path,
                original_filename="candidate.docx",
                checksum_sha256=None,
                is_current=False,
                issued_on=None,
            )
            session.add(version)
            session.flush()
            version_id = version.id

            run = DocumentGenerationRun(
                document_id=document.id,
                template_binding_id=None,
                template_definition_id=None,
                output_document_version_id=version.id,
                status=DocumentGenerationStatus.PENDING,
                source_application="Word",
                requested_by_user_id=None,
                input_payload_redacted="{}",
                error_summary=None,
                idempotency_key=f"finalization-lock-{token}",
            )
            session.add(run)
            session.commit()
            run_id = run.id

            allocation = OutputVersionAllocation(
                document_id=document.id,
                document_variant_id=variant.id,
                document_version_id=version.id,
                generation_run_id=run.id,
                version_no=version.version_no,
                storage_root="inspection",
                storage_relative_path=relative_path,
                original_filename="candidate.docx",
                storage_binding_id=None,
            )

        blocker = factory()
        locked_variant = blocker.execute(
            select(DocumentVariant)
            .where(DocumentVariant.id == variant_id)
            .with_for_update()
        ).scalar_one()
        assert locked_variant.id == variant_id

        with factory() as contender:
            contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
            try:
                finalize_output_document_version_write(
                    contender,
                    storage,
                    allocation,
                    binary_payload=b"must-wait-for-variant-lock",
                )
            except OperationalError as exc:
                assert "lock timeout" in str(exc).lower()
                contender.rollback()
            else:
                raise AssertionError(
                    "Expected finalization to block on the document_variant row lock"
                )

        assert (inspection_root / allocation.storage_relative_path).exists() is False

        blocker.rollback()
        blocker.close()
        blocker = None

        with factory() as session:
            checksum = finalize_output_document_version_write(
                session,
                storage,
                allocation,
                binary_payload=b"serialized-finalization",
            )
            session.commit()

        assert (inspection_root / allocation.storage_relative_path).read_bytes() == b"serialized-finalization"
        with factory() as session:
            run = session.get(DocumentGenerationRun, run_id)
            version = session.get(DocumentVersion, version_id)
            assert run is not None
            assert version is not None
            assert run.status == DocumentGenerationStatus.SUCCEEDED
            assert version.is_current is True
            assert version.checksum_sha256 == checksum
    finally:
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        with factory() as cleanup:
            if run_id is not None:
                cleanup.execute(
                    delete(DocumentGenerationRun).where(
                        DocumentGenerationRun.id == run_id
                    )
                )
            if version_id is not None:
                cleanup.execute(
                    delete(DocumentVersion).where(DocumentVersion.id == version_id)
                )
            if variant_id is not None:
                cleanup.execute(
                    delete(DocumentVariant).where(DocumentVariant.id == variant_id)
                )
            if document_id is not None:
                cleanup.execute(
                    delete(Document).where(Document.id == document_id)
                )
            if case_id is not None:
                cleanup.execute(delete(Case).where(Case.id == case_id))
            if site_id is not None:
                cleanup.execute(delete(Site).where(Site.id == site_id))
            if company_id is not None:
                cleanup.execute(delete(Company).where(Company.id == company_id))
            cleanup.commit()
        engine.dispose()


def test_output_finalization_locks_generation_run_before_storage_io(tmp_path):
    engine = create_engine(DATABASE_URL, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    token = uuid4().hex
    inspection_root = tmp_path / "inspection"
    inspection_root.mkdir(parents=True, exist_ok=True)
    storage = FilesystemStorageService(
        StorageConfig(inspection_root=inspection_root)
    )

    company_id = site_id = case_id = document_id = variant_id = version_id = run_id = None
    blocker = None
    try:
        with factory() as session:
            company = Company(legal_name=f"Finalization Run Lock Co {token}")
            session.add(company)
            session.flush()
            company_id = company.id

            site = Site(
                company_id=company.id,
                site_name=f"Finalization Run Lock Site {token}",
            )
            session.add(site)
            session.flush()
            site_id = site.id

            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.DRAFT,
            )
            session.add(case)
            session.flush()
            case_id = case.id

            document = Document(
                family_code="FINALIZATION_RUN_LOCK_TEST",
                document_type_code="finalization_run_lock_test",
                title="Finalization generation-run lock test",
                case_id=case.id,
            )
            session.add(document)
            session.flush()
            document_id = document.id

            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            variant_id = variant.id

            relative_path = f"finalization-run-lock/{token}/candidate.docx"
            version = DocumentVersion(
                document_variant_id=variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=relative_path,
                original_filename="candidate.docx",
                checksum_sha256=None,
                is_current=False,
                issued_on=None,
            )
            session.add(version)
            session.flush()
            version_id = version.id

            run = DocumentGenerationRun(
                document_id=document.id,
                template_binding_id=None,
                template_definition_id=None,
                output_document_version_id=version.id,
                status=DocumentGenerationStatus.PENDING,
                source_application="Word",
                requested_by_user_id=None,
                input_payload_redacted="{}",
                error_summary=None,
                idempotency_key=f"finalization-run-lock-{token}",
            )
            session.add(run)
            session.commit()
            run_id = run.id

            allocation = OutputVersionAllocation(
                document_id=document.id,
                document_variant_id=variant.id,
                document_version_id=version.id,
                generation_run_id=run.id,
                version_no=version.version_no,
                storage_root="inspection",
                storage_relative_path=relative_path,
                original_filename="candidate.docx",
                storage_binding_id=None,
            )

        blocker = factory()
        locked_run = blocker.execute(
            select(DocumentGenerationRun)
            .where(DocumentGenerationRun.id == run_id)
            .with_for_update()
        ).scalar_one()
        locked_run.status = DocumentGenerationStatus.CANCELLED
        locked_run.error_summary = "concurrent cancellation"
        blocker.flush()

        with factory() as contender:
            contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
            try:
                finalize_output_document_version_write(
                    contender,
                    storage,
                    allocation,
                    binary_payload=b"must-wait-for-generation-run-lock",
                )
            except OperationalError as exc:
                assert "lock timeout" in str(exc).lower()
                contender.rollback()
            else:
                raise AssertionError(
                    "Expected finalization to block on the document_generation_run row lock"
                )

        assert (inspection_root / allocation.storage_relative_path).exists() is False

        with factory() as verify:
            run = verify.get(DocumentGenerationRun, run_id)
            version = verify.get(DocumentVersion, version_id)
            assert run is not None
            assert version is not None
            assert run.status == DocumentGenerationStatus.PENDING
            assert version.is_current is False
            assert version.checksum_sha256 is None
            assert version.issued_on is None
    finally:
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        with factory() as cleanup:
            if run_id is not None:
                cleanup.execute(
                    delete(DocumentGenerationRun).where(
                        DocumentGenerationRun.id == run_id
                    )
                )
            if version_id is not None:
                cleanup.execute(
                    delete(DocumentVersion).where(DocumentVersion.id == version_id)
                )
            if variant_id is not None:
                cleanup.execute(
                    delete(DocumentVariant).where(DocumentVariant.id == variant_id)
                )
            if document_id is not None:
                cleanup.execute(
                    delete(Document).where(Document.id == document_id)
                )
            if case_id is not None:
                cleanup.execute(delete(Case).where(Case.id == case_id))
            if site_id is not None:
                cleanup.execute(delete(Site).where(Site.id == site_id))
            if company_id is not None:
                cleanup.execute(delete(Company).where(Company.id == company_id))
            cleanup.commit()
        engine.dispose()


def test_output_allocation_serializes_version_number_assignment_on_document_variant(tmp_path):
    engine = create_engine(DATABASE_URL, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    token = uuid4().hex
    dkkd_root = tmp_path / "dkkd"
    dkkd_root.mkdir(parents=True, exist_ok=True)
    storage = FilesystemStorageService(
        StorageConfig(
            inspection_root=tmp_path / "inspection",
            dkkd_root=dkkd_root,
        )
    )

    company_id = site_id = case_id = dkkd_id = document_id = variant_id = run_id = version_id = None
    blocker = None
    try:
        with factory() as session:
            company = Company(legal_name=f"Allocation Lock Co {token}")
            session.add(company)
            session.flush()
            company_id = company.id

            site = Site(
                company_id=company.id,
                site_name=f"Allocation Lock Site {token}",
                legacy_site_id=910000000 + int(token[:6], 16) % 80000000,
            )
            session.add(site)
            session.flush()
            site_id = site.id

            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.DRAFT,
            )
            session.add(case)
            session.flush()
            case_id = case.id

            dkkd = BusinessEligibilityCertificate(
                site_id=site.id,
                company_id=company.id,
                latest_flag=False,
            )
            session.add(dkkd)
            session.flush()
            dkkd_id = dkkd.id

            document = Document(
                family_code="ALLOCATION_LOCK_TEST",
                document_type_code="allocation_lock_test",
                title="Allocation lock test",
                business_eligibility_certificate_id=dkkd.id,
            )
            session.add(document)
            session.flush()
            document_id = document.id

            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            variant_id = variant.id

            run = DocumentGenerationRun(
                document_id=document.id,
                template_binding_id=None,
                template_definition_id=None,
                output_document_version_id=None,
                status=DocumentGenerationStatus.PENDING,
                source_application="Word",
                requested_by_user_id=None,
                input_payload_redacted="{}",
                error_summary=None,
                idempotency_key=f"allocation-lock-{token}",
            )
            session.add(run)
            session.commit()
            run_id = run.id

            folder_name = f"Allocation Lock Site {token} ({site.legacy_site_id})"
            (dkkd_root / folder_name).mkdir(parents=True, exist_ok=True)

            prepared = SimpleNamespace(
                persisted_state=SimpleNamespace(
                    generation_run_id=run.id,
                    document_variant_id=variant.id,
                    document_id=document.id,
                ),
                generation_plan=SimpleNamespace(
                    template=SimpleNamespace(storage_scope="dkkd_folder"),
                    request=SimpleNamespace(
                        case_id=None,
                        business_eligibility_certificate_id=dkkd.id,
                    ),
                ),
            )

        blocker = factory()
        locked_run = blocker.execute(
            select(DocumentGenerationRun)
            .where(DocumentGenerationRun.id == run_id)
            .with_for_update()
        ).scalar_one()
        assert locked_run.id == run_id

        with factory() as contender:
            contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
            try:
                allocate_output_document_version(
                    contender,
                    storage,
                    prepared,
                    output_filename="candidate.docx",
                )
            except OperationalError as exc:
                assert "lock timeout" in str(exc).lower()
                contender.rollback()
            else:
                raise AssertionError(
                    "Expected allocation to block on the generation_run row lock"
                )

        with factory() as verify:
            run = verify.get(DocumentGenerationRun, run_id)
            assert run is not None
            assert run.output_document_version_id is None
            assert list(
                verify.scalars(
                    select(DocumentVersion).where(
                        DocumentVersion.document_variant_id == variant_id
                    )
                )
            ) == []

        blocker.rollback()
        blocker.close()
        blocker = None

        blocker = factory()
        locked_variant = blocker.execute(
            select(DocumentVariant)
            .where(DocumentVariant.id == variant_id)
            .with_for_update()
        ).scalar_one()
        assert locked_variant.id == variant_id

        with factory() as contender:
            contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
            try:
                allocate_output_document_version(
                    contender,
                    storage,
                    prepared,
                    output_filename="candidate.docx",
                )
            except OperationalError as exc:
                assert "lock timeout" in str(exc).lower()
                contender.rollback()
            else:
                raise AssertionError(
                    "Expected allocation to block before assigning version_no"
                )

        with factory() as verify:
            run = verify.get(DocumentGenerationRun, run_id)
            assert run is not None
            assert run.output_document_version_id is None
            versions = list(
                verify.scalars(
                    select(DocumentVersion).where(
                        DocumentVersion.document_variant_id == variant_id
                    )
                )
            )
            assert versions == []

        blocker.rollback()
        blocker.close()
        blocker = None

        with factory() as session:
            allocation = allocate_output_document_version(
                session,
                storage,
                prepared,
                output_filename="candidate.docx",
            )
            session.commit()
            version_id = allocation.document_version_id

        assert allocation.version_no == 1
        with factory() as session:
            run = session.get(DocumentGenerationRun, run_id)
            version = session.get(DocumentVersion, version_id)
            assert run is not None
            assert version is not None
            assert run.output_document_version_id == version.id
            assert version.document_variant_id == variant_id
            assert version.version_no == 1
    finally:
        if blocker is not None:
            blocker.rollback()
            blocker.close()
        with factory() as cleanup:
            if run_id is not None:
                cleanup.execute(
                    delete(DocumentGenerationRun).where(
                        DocumentGenerationRun.id == run_id
                    )
                )
            if version_id is not None:
                cleanup.execute(
                    delete(DocumentVersion).where(DocumentVersion.id == version_id)
                )
            if variant_id is not None:
                cleanup.execute(
                    delete(DocumentVersion).where(
                        DocumentVersion.document_variant_id == variant_id
                    )
                )
                cleanup.execute(
                    delete(DocumentVariant).where(DocumentVariant.id == variant_id)
                )
            if document_id is not None:
                cleanup.execute(delete(Document).where(Document.id == document_id))
            if dkkd_id is not None:
                cleanup.execute(
                    delete(BusinessEligibilityCertificate).where(
                        BusinessEligibilityCertificate.id == dkkd_id
                    )
                )
            if case_id is not None:
                cleanup.execute(delete(Case).where(Case.id == case_id))
            if site_id is not None:
                cleanup.execute(delete(Site).where(Site.id == site_id))
            if company_id is not None:
                cleanup.execute(delete(Company).where(Company.id == company_id))
            cleanup.commit()
        engine.dispose()


def test_output_allocation_run_lock_refreshes_preloaded_generation_run_identity():
    engine = create_engine(DATABASE_URL, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    token = uuid4().hex
    company_id = site_id = case_id = document_id = variant_id = version_id = run_id = None
    contender = None
    try:
        with factory() as session:
            company = Company(legal_name=f"Allocation Refresh Co {token}")
            session.add(company)
            session.flush()
            company_id = company.id

            site = Site(
                company_id=company.id,
                site_name=f"Allocation Refresh Site {token}",
            )
            session.add(site)
            session.flush()
            site_id = site.id

            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.DRAFT,
            )
            session.add(case)
            session.flush()
            case_id = case.id

            document = Document(
                family_code="ALLOCATION_REFRESH_TEST",
                document_type_code="allocation_refresh_test",
                title="Allocation refresh test",
                case_id=case.id,
            )
            session.add(document)
            session.flush()
            document_id = document.id

            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            variant_id = variant.id

            run = DocumentGenerationRun(
                document_id=document.id,
                template_binding_id=None,
                template_definition_id=None,
                output_document_version_id=None,
                status=DocumentGenerationStatus.PENDING,
                source_application="Word",
                requested_by_user_id=None,
                input_payload_redacted="{}",
                error_summary=None,
                idempotency_key=f"allocation-refresh-{token}",
            )
            session.add(run)
            session.commit()
            run_id = run.id

        contender = factory()
        stale_run = contender.get(DocumentGenerationRun, run_id)
        assert stale_run is not None
        assert stale_run.output_document_version_id is None

        with factory() as winner:
            version = DocumentVersion(
                document_variant_id=variant_id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=f"allocation-refresh/{token}/candidate.docx",
                original_filename="candidate.docx",
                checksum_sha256=None,
                is_current=False,
                issued_on=None,
            )
            winner.add(version)
            winner.flush()
            version_id = version.id
            winner_run = winner.get(DocumentGenerationRun, run_id)
            assert winner_run is not None
            winner_run.output_document_version_id = version.id
            winner.commit()

        refreshed_run = output_version_module._lock_generation_run_for_output_allocation(
            contender,
            run_id,
        )
        assert refreshed_run is stale_run
        assert refreshed_run.output_document_version_id == version_id
        contender.rollback()
        contender.close()
        contender = None
    finally:
        if contender is not None:
            contender.rollback()
            contender.close()
        with factory() as cleanup:
            if run_id is not None:
                cleanup.execute(
                    delete(DocumentGenerationRun).where(
                        DocumentGenerationRun.id == run_id
                    )
                )
            if version_id is not None:
                cleanup.execute(
                    delete(DocumentVersion).where(DocumentVersion.id == version_id)
                )
            if variant_id is not None:
                cleanup.execute(
                    delete(DocumentVariant).where(DocumentVariant.id == variant_id)
                )
            if document_id is not None:
                cleanup.execute(delete(Document).where(Document.id == document_id))
            if case_id is not None:
                cleanup.execute(delete(Case).where(Case.id == case_id))
            if site_id is not None:
                cleanup.execute(delete(Site).where(Site.id == site_id))
            if company_id is not None:
                cleanup.execute(delete(Company).where(Company.id == company_id))
            cleanup.commit()
        engine.dispose()


def test_postgres_rejects_multiple_current_versions_for_one_document_variant():
    engine = create_engine(DATABASE_URL, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    token = uuid4().hex
    company_id = site_id = case_id = document_id = variant_id = first_version_id = noncurrent_version_id = None
    try:
        with factory() as session:
            company = Company(legal_name=f"Current Uniqueness Co {token}")
            session.add(company)
            session.flush()
            company_id = company.id

            site = Site(
                company_id=company.id,
                site_name=f"Current Uniqueness Site {token}",
            )
            session.add(site)
            session.flush()
            site_id = site.id

            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.DRAFT,
            )
            session.add(case)
            session.flush()
            case_id = case.id

            document = Document(
                family_code="CURRENT_UNIQUENESS_TEST",
                document_type_code="current_uniqueness_test",
                title="Current uniqueness test",
                case_id=case.id,
            )
            session.add(document)
            session.flush()
            document_id = document.id

            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            variant_id = variant.id

            first_current = DocumentVersion(
                document_variant_id=variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=f"current-uniqueness/{token}/current.docx",
                original_filename="current.docx",
                checksum_sha256="first-current",
                is_current=True,
                issued_on=None,
            )
            noncurrent = DocumentVersion(
                document_variant_id=variant.id,
                version_no=2,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=f"current-uniqueness/{token}/history.docx",
                original_filename="history.docx",
                checksum_sha256="history",
                is_current=False,
                issued_on=None,
            )
            session.add_all([first_current, noncurrent])
            session.commit()
            first_version_id = first_current.id
            noncurrent_version_id = noncurrent.id

        with factory() as contender:
            second_current = DocumentVersion(
                document_variant_id=variant_id,
                version_no=3,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=f"current-uniqueness/{token}/second-current.docx",
                original_filename="second-current.docx",
                checksum_sha256="second-current",
                is_current=True,
                issued_on=None,
            )
            contender.add(second_current)
            with pytest.raises(IntegrityError) as exc_info:
                contender.flush()
            assert "ux_document_version_current_per_variant" in str(exc_info.value)
            contender.rollback()

        with factory() as verify:
            current_ids = tuple(
                verify.scalars(
                    select(DocumentVersion.id).where(
                        DocumentVersion.document_variant_id == variant_id,
                        DocumentVersion.is_current.is_(True),
                    )
                )
            )
            assert current_ids == (first_version_id,)
            assert verify.get(DocumentVersion, noncurrent_version_id) is not None
    finally:
        with factory() as cleanup:
            if variant_id is not None:
                cleanup.execute(
                    delete(DocumentVersion).where(
                        DocumentVersion.document_variant_id == variant_id
                    )
                )
                cleanup.execute(
                    delete(DocumentVariant).where(DocumentVariant.id == variant_id)
                )
            if document_id is not None:
                cleanup.execute(delete(Document).where(Document.id == document_id))
            if case_id is not None:
                cleanup.execute(delete(Case).where(Case.id == case_id))
            if site_id is not None:
                cleanup.execute(delete(Site).where(Site.id == site_id))
            if company_id is not None:
                cleanup.execute(delete(Company).where(Company.id == company_id))
            cleanup.commit()
        engine.dispose()


def test_postgres_render_state_restore_swaps_current_versions_without_transient_uniqueness_violation():
    engine = create_engine(DATABASE_URL, future=True)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    token = uuid4().hex
    company_id = site_id = case_id = document_id = variant_id = baseline_id = candidate_id = None
    try:
        with factory() as session:
            company = Company(legal_name=f"Restore Current Co {token}")
            session.add(company)
            session.flush()
            company_id = company.id

            site = Site(
                company_id=company.id,
                site_name=f"Restore Current Site {token}",
            )
            session.add(site)
            session.flush()
            site_id = site.id

            case = Case(
                site_id=site.id,
                gxp_type="GMP",
                state=CaseState.DRAFT,
            )
            session.add(case)
            session.flush()
            case_id = case.id

            document = Document(
                family_code="RESTORE_CURRENT_TEST",
                document_type_code="restore_current_test",
                title="Restore current test",
                case_id=case.id,
            )
            session.add(document)
            session.flush()
            document_id = document.id

            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
                is_active=True,
            )
            session.add(variant)
            session.flush()
            variant_id = variant.id

            baseline = DocumentVersion(
                document_variant_id=variant.id,
                version_no=1,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=f"restore-current/{token}/baseline.docx",
                original_filename="baseline.docx",
                checksum_sha256="baseline",
                is_current=True,
                issued_on=None,
            )
            candidate = DocumentVersion(
                document_variant_id=variant.id,
                version_no=2,
                storage_binding_id=None,
                storage_root="inspection",
                storage_relative_path=f"restore-current/{token}/candidate.docx",
                original_filename="candidate.docx",
                checksum_sha256="candidate",
                is_current=False,
                issued_on=None,
            )
            session.add_all([baseline, candidate])
            session.commit()
            baseline_id = baseline.id
            candidate_id = candidate.id

        with factory() as session:
            baseline = session.get(DocumentVersion, baseline_id)
            candidate = session.get(DocumentVersion, candidate_id)
            assert baseline is not None
            assert candidate is not None

            baseline.is_current = False
            candidate.is_current = True
            session.flush()

            allocated = SimpleNamespace(
                allocated=SimpleNamespace(
                    output_allocation=SimpleNamespace(
                        document_variant_id=variant_id,
                        document_version_id=candidate_id,
                    )
                )
            )
            DocumentWorkflowService._restore_render_version_state(
                session,
                allocated,
                (baseline_id,),
                output_was_current_before_render=False,
            )
            session.commit()

        with factory() as verify:
            baseline = verify.get(DocumentVersion, baseline_id)
            candidate = verify.get(DocumentVersion, candidate_id)
            assert baseline is not None
            assert candidate is not None
            assert baseline.is_current is True
            assert candidate.is_current is False
            assert candidate.checksum_sha256 is None
            assert candidate.issued_on is None
    finally:
        with factory() as cleanup:
            if variant_id is not None:
                cleanup.execute(
                    delete(DocumentVersion).where(
                        DocumentVersion.document_variant_id == variant_id
                    )
                )
                cleanup.execute(
                    delete(DocumentVariant).where(DocumentVariant.id == variant_id)
                )
            if document_id is not None:
                cleanup.execute(delete(Document).where(Document.id == document_id))
            if case_id is not None:
                cleanup.execute(delete(Case).where(Case.id == case_id))
            if site_id is not None:
                cleanup.execute(delete(Site).where(Site.id == site_id))
            if company_id is not None:
                cleanup.execute(delete(Company).where(Company.id == company_id))
            cleanup.commit()
        engine.dispose()
