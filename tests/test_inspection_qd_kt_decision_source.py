"""Offline QĐKT source selection; never render or write a document."""
from dataclasses import replace
from datetime import date, datetime

import pytest

from backend.app.document.inspection_qd_kt_decision_source import (
    QdKtDecisionSourceBlocked,
    QdKtSourceDecision,
    require_unique_qdkt_source,
)

DAY = date(2026, 10, 20)
SOURCE = QdKtSourceDecision(
    id="decision-1", ordinal=1, reference="42/QĐ-KT",
    decision_on=DAY, legacy_raw="42/QĐ-KT 20/10/2026",
    relation_type=None, related_decision_id=None,
)


def select(decisions=(SOURCE,), **override):
    values = {
        "plan_decision_reference": SOURCE.reference,
        "plan_decision_date": SOURCE.decision_on,
        "plan_decision_legacy_raw": SOURCE.legacy_raw,
    }
    values.update(override)
    return require_unique_qdkt_source(decisions, **values)


def test_one_source_matching_scalar_projection_is_only_admitted_case():
    atoms = select()
    assert (atoms.source_decision_id, atoms.reference, atoms.decision_on, atoms.legacy_raw) == (
        SOURCE.id, SOURCE.reference, DAY, SOURCE.legacy_raw
    )


@pytest.mark.parametrize("decisions", [
    (),
    (SOURCE, replace(SOURCE, id="decision-2", ordinal=2)),
    (replace(SOURCE, id="",),),
    (replace(SOURCE, ordinal=2),),
    (replace(SOURCE, reference=" 42/QĐ-KT"),),
    (replace(SOURCE, reference=""),),
    (replace(SOURCE, legacy_raw=" "),),
    (replace(SOURCE, decision_on=datetime(2026, 10, 20, 0, 0)),),
    (replace(SOURCE, relation_type="REPLACES", related_decision_id="earlier"),),
    (replace(SOURCE, related_decision_id="earlier"),),
])
def test_incomplete_ambiguous_or_replacement_source_fails_closed(decisions):
    with pytest.raises(QdKtDecisionSourceBlocked):
        select(decisions)


@pytest.mark.parametrize("override", [
    {"plan_decision_reference": None},
    {"plan_decision_reference": "43/QĐ-KT"},
    {"plan_decision_date": None},
    {"plan_decision_date": date(2026, 10, 21)},
    {"plan_decision_legacy_raw": None},
    {"plan_decision_legacy_raw": "changed source"},
])
def test_missing_or_stale_scalar_projection_never_silently_falls_back(override):
    with pytest.raises(QdKtDecisionSourceBlocked, match="DECISION_PROJECTION_MISMATCH"):
        select(**override)


def test_db_adapter_reads_existing_inspection_decisions_without_writing(tmp_path):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from backend.app.db.base import Base
    from backend.app.db.enums import CaseState
    from backend.app.db.models.phase1 import (
        Case, Company, Site, InspectionPlan, InspectionDecision,
    )
    from backend.app.document.inspection_qd_kt_decision_source import (
        read_unique_qdkt_source_for_plan,
    )

    engine = create_engine(f"sqlite:///{(tmp_path / 'qdkt-source.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Synthetic company")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Synthetic site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        db.add(case)
        db.flush()
        plan = InspectionPlan(
            case_id=case.id,
            decision_reference=SOURCE.reference,
            decision_date=SOURCE.decision_on,
            decision_legacy_raw=SOURCE.legacy_raw,
        )
        db.add(plan)
        db.flush()
        plan_id = plan.id
        assert not db.scalars(
            select(InspectionDecision).where(InspectionDecision.inspection_plan_id == plan_id)
        ).all()
        with pytest.raises(QdKtDecisionSourceBlocked, match="SOURCE_DECISION_CARDINALITY_UNPROVEN"):
            read_unique_qdkt_source_for_plan(db, plan)

        row = InspectionDecision(
            inspection_plan_id=plan_id,
            ordinal=1,
            reference=SOURCE.reference,
            decision_on=SOURCE.decision_on,
            legacy_raw=SOURCE.legacy_raw,
        )
        db.add(row)
        db.flush()
        assert read_unique_qdkt_source_for_plan(db, plan).source_decision_id == row.id

        plan.decision_reference = "stale projection"
        with pytest.raises(QdKtDecisionSourceBlocked, match="DECISION_PROJECTION_MISMATCH"):
            read_unique_qdkt_source_for_plan(db, plan)
        db.rollback()

    engine.dispose()
