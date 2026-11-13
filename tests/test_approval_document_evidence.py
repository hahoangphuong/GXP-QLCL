"""Case-level PCT/CT document visibility must never invent submission-round links."""
from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, Document, DocumentVariant, DocumentVersion,
    InspectionApprovalSubmission, Site,
)
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService


def test_document_inventory_reports_case_family_without_binding_it_to_pct_ct_rounds():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    catalog = CatalogReadService()
    user = build_authenticated_user("approval-document-reader", "manager")
    try:
        with Session(engine) as setup:
            company = Company(legal_name="Synthetic approval documentary evidence")
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic documentary site")
            setup.add(site)
            setup.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.CERTIFIED)
            other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.CERTIFIED)
            setup.add_all([case, other])
            setup.flush()
            pct1 = InspectionApprovalSubmission(
                case_id=case.id, stage="PCT", round_no=1,
                completed_on=date(2026, 11, 11),
            )
            pct2 = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=2)
            setup.add_all([pct1, pct2])
            setup.flush()
            ct = InspectionApprovalSubmission(
                case_id=case.id, stage="CT", round_no=1, pct_submission_id=pct1.id,
                completed_on=date(2026, 11, 12),
            )
            setup.add(ct)
            pct_doc = Document(
                case_id=case.id, family_code="INSPECTION_PT_PCT",
                document_type_code="INSPECTION_PT_PCT", title="Case-level PCT form",
            )
            other_ct_doc = Document(
                case_id=other.id, family_code="INSPECTION_PT_CT",
                document_type_code="INSPECTION_PT_CT", title="Unrelated Case CT",
            )
            setup.add_all([pct_doc, other_ct_doc])
            setup.flush()
            variant = DocumentVariant(
                document_id=pct_doc.id, variant_type=DocumentVariantType.SIGNED_PDF,
                language_code="vi", is_active=True,
            )
            setup.add(variant)
            setup.flush()
            version = DocumentVersion(
                document_variant_id=variant.id, version_no=1, is_current=True,
                storage_root="synthetic", storage_relative_path="pct-case.pdf",
                original_filename="pct-case.pdf", checksum_sha256="a" * 64,
            )
            setup.add(version)
            ids = (case.id, other.id, pct1.id, pct2.id, ct.id, pct_doc.id, other_ct_doc.id)
            setup.commit()

        case_id, other_id, pct1_id, pct2_id, ct_id, pct_doc_id, other_ct_doc_id = ids
        for _ in range(2):
            # Only committed data; no synthesized approval/document association.
            with Session(engine) as session:
                initial_audit = session.scalar(select(func.count(AuditEvent.id)))
                workspace = CaseWorkspaceRead.model_validate(
                    catalog.get_case_workspace(session, case_id=case_id, user=user)
                )
                records = workspace.inspection.approval_document_evidence
                assert [row.stage for row in records] == ["PCT", "CT"]
                pct, ct = records
                assert pct.family_code == "INSPECTION_PT_PCT"
                assert pct.case_document_status == "available"
                assert pct.selected_case_document_id == pct_doc_id
                assert pct.selected_case_document_open_available is True
                assert pct.round_document_binding_state == "not_modelled"
                assert pct.submission_ids == [pct1_id, pct2_id]
                assert pct.completed_submission_ids == [pct1_id]

                assert ct.family_code == "INSPECTION_PT_CT"
                assert ct.case_document_status == "missing"
                assert ct.selected_case_document_id is None
                assert ct.selected_case_document_open_available is False
                assert ct.round_document_binding_state == "not_modelled"
                assert ct.submission_ids == [ct_id]
                assert ct.completed_submission_ids == [ct_id]

                assert next(
                    row for row in workspace.inspection.approval_submissions
                    if row.approval_submission_id == ct_id
                ).pct_submission_id == pct1_id
                assert session.scalar(select(func.count(AuditEvent.id))) == initial_audit == 0
                assert not session.new and not session.dirty

        with Session(engine) as session:
            other_workspace = CaseWorkspaceRead.model_validate(
                catalog.get_case_workspace(session, case_id=other_id, user=user)
            )
            other_pct, other_ct = other_workspace.inspection.approval_document_evidence
            assert other_pct.case_document_status == "missing"
            assert other_pct.submission_ids == []
            assert other_ct.case_document_status == "available"
            assert other_ct.selected_case_document_id == other_ct_doc_id
            assert other_ct.selected_case_document_open_available is False
            assert other_ct.submission_ids == []

        # A newly indexed Case-level CT document still cannot be assigned
        # to the already completed CT round without a canonical foreign key.
        with Session(engine) as session:
            new_ct_doc = Document(
                case_id=case_id, family_code="INSPECTION_PT_CT",
                document_type_code="INSPECTION_PT_CT", title="Case-level CT form",
            )
            session.add(new_ct_doc)
            session.commit()
            ct_doc_id = new_ct_doc.id

        with Session(engine) as session:
            workspace = CaseWorkspaceRead.model_validate(
                catalog.get_case_workspace(session, case_id=case_id, user=user)
            )
            ct = workspace.inspection.approval_document_evidence[1]
            assert ct.case_document_status == "available"
            assert ct.selected_case_document_id == ct_doc_id
            assert ct.selected_case_document_open_available is False
            assert ct.round_document_binding_state == "not_modelled"
            assert ct.submission_ids == [ct_id]
    finally:
        engine.dispose()
