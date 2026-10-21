"""Regression: a stale KHKT generation run must not bypass the Case owner.

The persisted run/versions are synthetic and only exercise SQLite database
lineage. No template bytes, storage writes, VM or live/rehearsal DB are used.
The public PREPARE and RENDER entrypoint services must both reject a retry
after a different operation commits a current, openable KHKT version.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentGenerationStatus, DocumentVariantType
from backend.app.db.models.phase1 import (
    AppUser,
    AuditEvent,
    Case,
    Company,
    Document,
    DocumentGenerationRun,
    DocumentVariant,
    DocumentVersion,
    Site,
)
from backend.app.services.document_api import DocumentWorkflowService


FAMILY = "INSPECTION_KE_HOACH_KT"


@pytest.mark.parametrize(
    ("run_status", "has_pending_allocation"),
    (
        (DocumentGenerationStatus.PENDING, False),
        (DocumentGenerationStatus.PENDING, True),
        (DocumentGenerationStatus.FAILED, True),
    ),
)
def test_prepared_khkt_run_cannot_resume_after_another_current_version(
    tmp_path, run_status, has_pending_allocation,
):
    engine = create_engine(
        f"sqlite:///{(tmp_path / ('khkt-stale-' + run_status.value + '-' + str(has_pending_allocation) + '.db')).as_posix()}",
        future=True,
    )
    Base.metadata.create_all(engine)
    user = build_authenticated_user(
        "unpersisted-stale-retry", permissions={"document.read", "document.write"},
    )
    service = DocumentWorkflowService()
    key = f"stale-khkt-{run_status.value}-{has_pending_allocation}"

    try:
        # Earlier transaction: a PREPARE run exists, and optionally already
        # has an allocated but noncurrent DocumentVersion (no output bytes).
        with Session(engine) as seed:
            company = Company(legal_name="Synthetic company")
            seed.add(company)
            seed.flush()
            site = Site(company_id=company.id, site_name="Synthetic site")
            seed.add(site)
            seed.flush()
            case = Case(
                site_id=site.id, gxp_type="GLP", state=CaseState.DRAFT,
                opened_year=2026,
            )
            seed.add(case)
            seed.flush()
            case_id = case.id

            document = Document(
                family_code=FAMILY,
                document_type_code=FAMILY,
                case_id=case_id,
            )
            seed.add(document)
            seed.flush()
            variant = DocumentVariant(
                document_id=document.id,
                variant_type=DocumentVariantType.EDITABLE_DOCX,
                language_code="vi",
            )
            seed.add(variant)
            seed.flush()
            actor = AppUser(username="original-preparer", is_active=True)
            seed.add(actor)
            seed.flush()
            allocation_id = None
            if has_pending_allocation:
                pending = DocumentVersion(
                    document_variant_id=variant.id,
                    version_no=1,
                    storage_root="inspection",
                    storage_relative_path="synthetic/stale-pending.docx",
                    original_filename="KHKT pending.docx",
                    checksum_sha256=None,
                    is_current=False,
                )
                seed.add(pending)
                seed.flush()
                allocation_id = pending.id

            run = DocumentGenerationRun(
                document_id=document.id,
                document_variant_id=variant.id,
                template_binding_id=None,
                template_definition_id=None,
                output_document_version_id=allocation_id,
                status=run_status,
                source_application="Word",
                requested_by_user_id=actor.id,
                input_payload_redacted="{}",
                error_summary="previous render failed" if run_status == DocumentGenerationStatus.FAILED else None,
                idempotency_key=key,
            )
            seed.add(run)
            seed.commit()
            run_id = run.id
            document_id = document.id
            variant_id = variant.id

        # Subsequent independent transaction: another generation path has
        # finalized an openable current version of the same Case/family.
        with Session(engine) as winner:
            version = DocumentVersion(
                document_variant_id=variant_id,
                version_no=2 if has_pending_allocation else 1,
                storage_root="inspection",
                storage_relative_path="synthetic/other-current.docx",
                original_filename="KHKT current.docx",
                checksum_sha256="b" * 64,
                is_current=True,
            )
            winner.add(version)
            winner.commit()
            current_id = version.id

        base_payload = {
            "family_code": FAMILY,
            "case_id": case_id,
            "gxp_type": "GLP",
            "storage_scope": "inspection_folder",
            "language_code": "vi",
            "idempotency_key": key,
            "payload": {},
            "strict_payload": True,
            "output_filename": "3. Kế hoạch kiểm tra GLP.docx",
        }

        # A retry of this exact old idempotency key, whether via PREPARE or
        # RENDER, must stop at the same Case owner before run reuse/reset.
        for operation in ("prepare", "render"):
            with Session(engine) as session:
                endpoint = (
                    service.prepare_generation
                    if operation == "prepare"
                    else service.render_template_docx
                )
                with pytest.raises(HTTPException, match="already exists") as exc:
                    endpoint(
                        session,
                        storage=object(),
                        payload=base_payload,
                        user=user,
                    )
                assert exc.value.status_code == 409
                assert len(session.new) == 0
                assert len(session.dirty) == 0
                session.rollback()

            with Session(engine) as verify:
                old = verify.get(DocumentGenerationRun, run_id)
                assert old is not None
                assert old.document_id == document_id
                assert old.status == run_status
                assert old.idempotency_key == key
                assert old.output_document_version_id == allocation_id
                assert old.error_summary == (
                    "previous render failed"
                    if run_status == DocumentGenerationStatus.FAILED else None
                )
                assert len(list(verify.scalars(select(DocumentGenerationRun)))) == 1
                assert len(list(verify.scalars(select(Document)))) == 1
                assert len(list(verify.scalars(select(DocumentVariant)))) == 1
                assert len(list(verify.scalars(select(AppUser)))) == 1
                assert len(list(verify.scalars(select(AuditEvent)))) == 0
                versions = list(
                    verify.scalars(
                        select(DocumentVersion).order_by(DocumentVersion.version_no)
                    )
                )
                assert len(versions) == (2 if has_pending_allocation else 1)
                assert sum(v.is_current for v in versions) == 1
                current = next(v for v in versions if v.is_current)
                assert current.id == current_id
                assert current.checksum_sha256 == "b" * 64
                assert current.storage_relative_path == "synthetic/other-current.docx"
                if has_pending_allocation:
                    assert versions[0].id == allocation_id
                    assert versions[0].is_current is False
                    assert versions[0].checksum_sha256 is None
    finally:
        engine.dispose()
