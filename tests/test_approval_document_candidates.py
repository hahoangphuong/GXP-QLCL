"""PCT/CT document choices are not limited to one family checklist selection.

Synthetic in-memory persistence only. Readiness is a projection of the exact
Case-locked bind API's current candidate and permission preconditions.
"""
from __future__ import annotations

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
from backend.app.services.workflow import CaseWorkflowService


def test_every_pct_document_is_a_round_choice_with_canonical_binding_readback():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    catalog = CatalogReadService()
    workflow = CaseWorkflowService()
    manager = build_authenticated_user("candidate-manager", "manager")
    reader = build_authenticated_user("candidate-reader", "reader")
    try:
        with Session(engine) as session:
            company = Company(legal_name="Synthetic multi-PCT choice")
            session.add(company)
            session.flush()
            site = Site(company_id=company.id, site_name="Synthetic site")
            session.add(site)
            session.flush()
            case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            other = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            session.add_all([case, other])
            session.flush()
            p1 = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=1)
            p2 = InspectionApprovalSubmission(case_id=case.id, stage="PCT", round_no=2)
            ct = InspectionApprovalSubmission(case_id=case.id, stage="CT", round_no=1, pct_submission_id=p1.id)
            session.add_all([p1, p2, ct])
            session.flush()
            pct1 = Document(case_id=case.id, family_code="INSPECTION_PT_PCT",
                            document_type_code="INSPECTION_PT_PCT", title="PCT first source")
            pct2 = Document(case_id=case.id, family_code="INSPECTION_PT_PCT",
                            document_type_code="INSPECTION_PT_PCT", title="PCT second source")
            ct_doc = Document(case_id=case.id, family_code="INSPECTION_PT_CT",
                              document_type_code="INSPECTION_PT_CT", title="CT source")
            foreign = Document(case_id=other.id, family_code="INSPECTION_PT_PCT",
                               document_type_code="INSPECTION_PT_PCT", title="Other Case")
            session.add_all([pct1, pct2, ct_doc, foreign])
            session.flush()
            variant = DocumentVariant(document_id=pct2.id, variant_type=DocumentVariantType.SIGNED_PDF,
                                      language_code="vi", is_active=True)
            session.add(variant)
            session.flush()
            session.add(DocumentVersion(
                document_variant_id=variant.id, version_no=1, is_current=True,
                storage_root="synthetic", storage_relative_path="pct2.pdf",
                original_filename="pct2.pdf", checksum_sha256="e" * 64,
            ))
            ids = {
                "case": case.id, "p1": p1.id, "p2": p2.id, "ct": ct.id,
                "pct1": pct1.id, "pct2": pct2.id, "ctdoc": ct_doc.id,
                "foreign": foreign.id,
            }
            session.commit()

        def workspace(user):
            with Session(engine) as session:
                audit_count = session.scalar(select(func.count(AuditEvent.id)))
                result = CaseWorkspaceRead.model_validate(
                    catalog.get_case_workspace(session, case_id=ids["case"], user=user)
                )
                assert session.scalar(select(func.count(AuditEvent.id))) == audit_count
                assert not session.new and not session.dirty
                return result

        initial = workspace(manager)
        options = initial.inspection.approval_document_candidates
        assert {(x.stage, x.document_id) for x in options} == {
            ("PCT", ids["pct1"]), ("PCT", ids["pct2"]), ("CT", ids["ctdoc"]),
        }
        assert ids["foreign"] not in {x.document_id for x in options}
        assert {x.document_id: x.open_available for x in options} == {
            ids["pct1"]: False, ids["pct2"]: True, ids["ctdoc"]: False,
        }
        # The pre-existing checklist intentionally has only one best PCT,
        # but the binding choices must retain both canonical Document UUIDs.
        selected = next(x for x in initial.documents.items
                        if x.parent_scope == "case" and x.family_code == "INSPECTION_PT_PCT")
        assert selected.document_id == ids["pct2"]
        actions = {x.approval_submission_id: x for x in initial.inspection.approval_document_bind_readiness}
        assert set(actions) == {ids["p1"], ids["p2"], ids["ct"]}
        assert actions[ids["p1"]].available and actions[ids["p2"]].available
        assert set(actions[ids["p1"]].eligible_document_ids) == {ids["pct1"], ids["pct2"]}
        assert set(actions[ids["p2"]].eligible_document_ids) == {ids["pct1"], ids["pct2"]}
        assert actions[ids["ct"]].eligible_document_ids == [ids["ctdoc"]]
        assert actions[ids["p1"]].expected_version == 1

        read_only = workspace(reader)
        for action in read_only.inspection.approval_document_bind_readiness:
            assert not action.available
            assert action.reason_code == "missing_permission"
            assert action.eligible_document_ids == []
        assert {x.document_id for x in read_only.inspection.approval_document_candidates} == {
            ids["pct1"], ids["pct2"], ids["ctdoc"],
        }

        with Session(engine) as session:
            linked = workflow.bind_approval_document(
                session, approval_submission_id=ids["p1"],
                document_id=ids["pct1"], expected_version=1,
                reason="Synthetic binding from choice", user=manager,
            )
            assert linked["created"]
            session.commit()

        changed = workspace(manager)
        current = {x.document_id: x for x in changed.inspection.approval_document_candidates}
        assert current[ids["pct1"]].bound_submission_id == ids["p1"]
        assert current[ids["pct2"]].bound_submission_id is None
        actions = {x.approval_submission_id: x for x in changed.inspection.approval_document_bind_readiness}
        assert set(actions[ids["p1"]].eligible_document_ids) == {ids["pct1"], ids["pct2"]}
        assert actions[ids["p1"]].expected_version == linked["row_version"]
        assert actions[ids["p2"]].eligible_document_ids == [ids["pct2"]]
        assert changed.inspection.approval_document_evidence[0].round_document_binding_state == "partially_bound"

        with Session(engine) as session:
            case = session.get(Case, ids["case"])
            case.state = CaseState.CLOSED
            session.commit()

        closed = workspace(manager)
        assert all(not x.available and x.reason_code == "terminal_case"
                   and x.eligible_document_ids == []
                   for x in closed.inspection.approval_document_bind_readiness)
        assert closed.inspection.approval_document_candidates[0].document_id
    finally:
        engine.dispose()
