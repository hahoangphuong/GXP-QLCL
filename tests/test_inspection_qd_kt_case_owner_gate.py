"""Case-scoped QĐKT source selection, without side effects or renderer access."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import Case, Company, Site, InspectionPlan, InspectionDecision
from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionSourceBlocked, read_unique_qdkt_source_for_case,
)

DAY = date(2026, 10, 20)


def test_qdkt_case_binding_blocks_cross_case_and_missing_plan(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'case-qdkt.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Test legal name")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Test facility")
        db.add(site)
        db.flush()
        cases = [
            Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
            for _ in range(2)
        ]
        db.add_all(cases)
        db.flush()
        first_id, second_id = cases[0].id, cases[1].id
        plan = InspectionPlan(
            case_id=first_id, decision_reference="42/QD",
            decision_date=DAY, decision_legacy_raw="42/QD 20/10/2026",
        )
        db.add(plan)
        db.flush()
        decision = InspectionDecision(
            inspection_plan_id=plan.id, ordinal=1, reference="42/QD",
            decision_on=DAY, legacy_raw="42/QD 20/10/2026",
        )
        db.add(decision)
        db.flush()

        assert read_unique_qdkt_source_for_case(db, case_id=first_id).source_decision_id == decision.id
        with pytest.raises(QdKtDecisionSourceBlocked, match="CASE_INSPECTION_PLAN_NOT_UNIQUE"):
            read_unique_qdkt_source_for_case(db, case_id=second_id)
        with pytest.raises(QdKtDecisionSourceBlocked, match="CASE_NOT_FOUND"):
            read_unique_qdkt_source_for_case(db, case_id="nonexistent")
        with pytest.raises(QdKtDecisionSourceBlocked, match="CASE_ID_MISSING"):
            read_unique_qdkt_source_for_case(db, case_id="")

        assert db.dirty == set()
        assert db.new == set()
        db.rollback()
    engine.dispose()


def test_qdkt_case_binding_does_not_flush_pending_new_decision(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'pending-qdkt.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Pending company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Pending site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        db.add(case)
        db.flush()
        plan = InspectionPlan(case_id=case.id, decision_reference="12/QD",
                              decision_date=DAY, decision_legacy_raw="12/QD 20/10/2026")
        db.add(plan)
        db.flush()
        db.add(InspectionDecision(inspection_plan_id=plan.id, ordinal=1,
                                  reference="12/QD", decision_on=DAY,
                                  legacy_raw="12/QD 20/10/2026"))
        pending_count = len(db.new)
        with pytest.raises(QdKtDecisionSourceBlocked, match="SOURCE_DECISION_CARDINALITY_UNPROVEN"):
            read_unique_qdkt_source_for_case(db, case_id=case.id)
        assert len(db.new) == pending_count
        db.rollback()
    engine.dispose()
