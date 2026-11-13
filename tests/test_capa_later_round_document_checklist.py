"""Case document checklist must preserve real CAPA cycle owners after round two."""
from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import AuditEvent, CapaCycle, Case, Company, Document, Site
from backend.app.read_models import CaseWorkspaceRead
from backend.app.services.catalog import CatalogReadService


def test_later_capa_rounds_show_real_documents_without_fabricating_template_families():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    catalog = CatalogReadService()
    user = build_authenticated_user("synthetic-capa-documents", "manager")
    try:
        with Session(engine) as setup:
            company = Company(legal_name="Synthetic multi-round CAPA")
            setup.add(company)
            setup.flush()
            site = Site(company_id=company.id, site_name="Synthetic site")
            setup.add(site)
            setup.flush()
            selected = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
            other = Case(site_id=site.id, gxp_type="GLP", state=CaseState.INSPECTION_COMPLETED)
            setup.add_all([selected, other])
            setup.flush()
            rounds = [
                CapaCycle(case_id=selected.id, round_no=n, status="accepted", result="accepted")
                for n in (1, 2, 3, 4)
            ]
            foreign = CapaCycle(case_id=other.id, round_no=3, status="accepted", result="accepted")
            setup.add_all([*rounds, foreign])
            setup.flush()
            # A legacy family label does not override the canonical cycle FK.
            doc3 = Document(
                capa_cycle_id=rounds[2].id, family_code="INSPECTION_CAPA_LAN_2",
                document_type_code="INSPECTION_CAPA_LAN_2", title="Evidence for third cycle",
            )
            foreign_doc = Document(
                capa_cycle_id=foreign.id, family_code="INSPECTION_CAPA_LAN_2",
                document_type_code="INSPECTION_CAPA_LAN_2", title="Other Case evidence",
            )
            setup.add_all([doc3, foreign_doc])
            setup.commit()
            ids = (selected.id, other.id, *(row.id for row in rounds), doc3.id, foreign_doc.id)

        case_id, other_id, round1, round2, round3, round4, doc3_id, foreign_doc_id = ids
        for _ in range(2):
            with Session(engine) as session:
                audit_before = session.scalar(select(func.count(AuditEvent.id)))
                workspace = CaseWorkspaceRead.model_validate(
                    catalog.get_case_workspace(session, case_id=case_id, user=user)
                )
                capa = [item for item in workspace.documents.items if item.parent_scope == "capa_cycle"]
                by_cycle = {}
                for item in capa:
                    by_cycle.setdefault(item.parent_id, []).append(item)
                assert set(by_cycle) == {round1, round2, round3, round4}
                assert by_cycle[round1][0].family_code == "INSPECTION_CAPA_LAN_1"
                assert by_cycle[round2][0].family_code == "INSPECTION_CAPA_LAN_2"
                assert by_cycle[round1][0].status == by_cycle[round2][0].status == "missing"
                assert len(by_cycle[round3]) == 1
                actual = by_cycle[round3][0]
                assert actual.family_code == "INSPECTION_CAPA_LAN_2"
                assert actual.document_id == doc3_id
                assert actual.status == "available"
                assert actual.label.startswith("CAPA lần 3")
                assert "Evidence for third cycle" in actual.label
                assert len(by_cycle[round4]) == 1
                missing = by_cycle[round4][0]
                assert missing.family_code is None
                assert missing.document_id is None
                assert missing.status == "missing"
                assert missing.label == "Tài liệu CAPA lần 4"
                assert foreign_doc_id not in {item.document_id for item in capa}
                assert not any(
                    action.parent_id in {round3, round4}
                    for action in workspace.contextual_document_actions
                )
                assert session.scalar(select(func.count(AuditEvent.id))) == audit_before == 0
                assert not session.new and not session.dirty

        with Session(engine) as session:
            foreign_workspace = CaseWorkspaceRead.model_validate(
                catalog.get_case_workspace(session, case_id=other_id, user=user)
            )
            foreign_capa = [
                item for item in foreign_workspace.documents.items
                if item.parent_scope == "capa_cycle"
            ]
            assert len(foreign_capa) == 1
            assert foreign_capa[0].document_id == foreign_doc_id
            assert foreign_capa[0].label.startswith("CAPA lần 3")

        with Session(engine) as session:
            doc4 = Document(
                capa_cycle_id=round4, family_code="SYNTHETIC_CAPA_REVIEW",
                document_type_code="SYNTHETIC_CAPA_REVIEW", title="Fourth round review",
            )
            session.add(doc4)
            session.commit()
            doc4_id = doc4.id

        with Session(engine) as session:
            workspace = CaseWorkspaceRead.model_validate(
                catalog.get_case_workspace(session, case_id=case_id, user=user)
            )
            matching = [
                item for item in workspace.documents.items
                if item.parent_scope == "capa_cycle" and item.parent_id == round4
            ]
            assert len(matching) == 1
            assert matching[0].document_id == doc4_id
            assert matching[0].family_code == "SYNTHETIC_CAPA_REVIEW"
            assert matching[0].status == "available"
            assert matching[0].label == "CAPA lần 4 — Fourth round review"
    finally:
        engine.dispose()
