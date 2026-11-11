"""A long-lived Session must not use stale period ORM children after Case lock.

The tests use an isolated file-backed SQLite database and two sessions.
A second writer changes the canonical segment without bumping its parent
Outcome version (as may occur during legacy data repair). This is not
authorization to replace a different period identity or falsify audit BEFORE.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app.auth import build_authenticated_user
from backend.app.db.base import Base
from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    AuditEvent, Case, Company, InspectionOutcome, InspectionPeriodSegment, Site,
)
from backend.app.services.workflow import CaseWorkflowService


def _setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'inspection_period_children.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(legal_name="Synthetic two-session period owner")
        db.add(company)
        db.flush()
        site = Site(company_id=company.id, site_name="Two-session synthetic Site")
        db.add(site)
        db.flush()
        case = Case(site_id=site.id, gxp_type="GMP", state=CaseState.INSPECTION_COMPLETED)
        db.add(case)
        db.flush()
        outcome = InspectionOutcome(
            case_id=case.id, inspection_period_state="KNOWN",
            inspected_on=date(2026, 10, 1), inspected_to_on=date(2026, 10, 1),
        )
        db.add(outcome)
        db.flush()
        segment = InspectionPeriodSegment(
            inspection_outcome_id=outcome.id, ordinal=1,
            started_on=date(2026, 10, 1), ended_on=date(2026, 10, 1),
        )
        db.add(segment)
        db.commit()
        return engine, case.id, outcome.id, segment.id, outcome.row_version


def test_compatibility_writer_rechecks_changed_segment_ordinal_before_replace(tmp_path):
    engine, case_id, outcome_id, segment_id, expected_version = _setup(tmp_path)
    user = build_authenticated_user("period-owner-manager", "manager")
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as contender:
            stale = contender.get(InspectionPeriodSegment, segment_id)
            assert stale is not None and stale.ordinal == 1
            with Session(engine) as writer:
                canonical = writer.get(InspectionPeriodSegment, segment_id)
                canonical.ordinal = 2
                writer.commit()

            # One canonical segment with a non-1 ordinal is invalid, even if
            # this Session had previously loaded the segment as ordinal=1.
            with pytest.raises(HTTPException) as exc:
                CaseWorkflowService().upsert_inspection_outcome(
                    contender, case_id=case_id, expected_version=expected_version,
                    inspected_on=date(2026, 10, 3), inspected_to_on=date(2026, 10, 3),
                    decision_reference=None, bbkt_reference=None, outcome_result=None,
                    reason="Two-session stale ordinal regression", user=user,
                    fields_set={"inspected_on", "inspected_to_on"},
                )
            assert exc.value.status_code == 409
            assert "invalid canonical single-segment ordinal" in str(exc.value.detail)
            contender.rollback()
        with Session(engine) as verify:
            canonical = verify.get(InspectionPeriodSegment, segment_id)
            assert canonical.ordinal == 2
            assert canonical.started_on == date(2026, 10, 1)
            assert verify.get(InspectionOutcome, outcome_id).row_version == expected_version
            assert verify.scalar(select(func.count(AuditEvent.id))) == 0
    finally:
        engine.dispose()


def test_period_replace_audit_before_uses_fresh_committed_segment_dates(tmp_path):
    engine, case_id, outcome_id, segment_id, expected_version = _setup(tmp_path)
    user = build_authenticated_user("period-owner-manager", "manager")
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as contender:
            stale = contender.get(InspectionPeriodSegment, segment_id)
            assert stale is not None and stale.started_on == date(2026, 10, 1)
            with Session(engine) as writer:
                canonical = writer.get(InspectionPeriodSegment, segment_id)
                canonical.started_on = date(2026, 10, 2)
                canonical.ended_on = date(2026, 10, 2)
                writer.commit()

            result = CaseWorkflowService().upsert_inspection_period_segments(
                contender, case_id=case_id, expected_version=expected_version,
                segments=[{"ordinal": 1, "started_on": date(2026, 10, 3),
                           "ended_on": date(2026, 10, 3)}],
                reason="Two-session canonical audit regression", user=user,
            )
            assert result["row_version"] > expected_version
            contender.commit()
        with Session(engine) as verify:
            event = verify.scalar(select(AuditEvent).where(
                AuditEvent.action == "inspection_period_segments.replace",
            ))
            assert event is not None
            before = json.loads(event.old_values_json)
            after = json.loads(event.new_values_json)
            assert before["segments"] == [{
                "ordinal": 1, "started_on": "2026-10-02", "ended_on": "2026-10-02",
            }]
            assert after["segments"] == [{
                "ordinal": 1, "started_on": "2026-10-03", "ended_on": "2026-10-03",
            }]
            canonical = verify.scalars(select(InspectionPeriodSegment).where(
                InspectionPeriodSegment.inspection_outcome_id == outcome_id,
            )).all()
            assert len(canonical) == 1
            assert canonical[0].started_on == date(2026, 10, 3)
    finally:
        engine.dispose()
