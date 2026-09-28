"""VM-only PostgreSQL integration coverage for the guarded B6B V2 writer.

This module deliberately has no SQLite fallback.  The disposable-database
script enables it explicitly after applying the real Alembic chain.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import itertools
import os
import threading

import pytest
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState
from backend.app.db.models.phase1 import (
    Case,
    Company,
    InspectionDecision,
    InspectionOutcome,
    InspectionPlan,
    Site,
)
from backend.app.domain.legacy_snapshot_v2 import SCHEMA_VERSION, snapshot_bytes
from tools import apply_db_ktra_repeatable_v2 as apply
from tools import reconcile_db_ktra_repeatable_v2 as reconciliation


if os.environ.get("B6B_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set B6B_POSTGRES_INTEGRATION=1 to run disposable PostgreSQL coverage", allow_module_level=True)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError("B6B PostgreSQL integration requires an explicit PostgreSQL DATABASE_URL")

pytestmark = pytest.mark.b6b_postgres_integration
_legacy_ids = itertools.count(900001)


def _snapshot(legacy_id: int, *, decision_raw: str = "376/QD-QLD ngày 29/08/2016;") -> tuple[dict[str, object], str]:
    header = ["ID", "LOẠI KT", "ID CƠ SỞ", "Q. định", "B. bản"]
    cells = lambda values: [{"column_ordinal": index, "raw_value": value} for index, value in enumerate(values, 1)]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "sheets": [{"sheet_name": "db.ktra", "raw_rows": [
            {"source_row_number": 4, "cells": cells(header)},
            {"source_row_number": 5, "cells": cells([legacy_id, "GMP", 1, decision_raw, "-"])},
        ]}],
    }
    return payload, sha256(snapshot_bytes(payload)).hexdigest()


@pytest.fixture()
def postgres_engine():
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == reconciliation.REQUIRED_REVISION
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def owner_topology(postgres_engine):
    legacy_id = next(_legacy_ids)
    with Session(postgres_engine) as session:
        company = Company(legal_name=f"B6B disposable company {legacy_id}")
        session.add(company)
        session.flush()
        site = Site(company_id=company.id, site_name=f"B6B disposable site {legacy_id}")
        session.add(site)
        session.flush()
        case = Case(legacy_inspection_id=legacy_id, site_id=site.id, gxp_type="GMP", state=CaseState.DRAFT)
        session.add(case)
        session.flush()
        plan = InspectionPlan(
            case_id=case.id,
            decision_reference="376/QD-QLD",
            decision_date=date(2016, 8, 29),
            decision_legacy_raw="376/QD-QLD ngày 29/08/2016;",
        )
        outcome = InspectionOutcome(case_id=case.id)
        session.add_all((plan, outcome))
        session.flush()
        assert company.id is not None
        assert site.id is not None
        assert case.id is not None
        assert plan.id is not None
        assert outcome.id is not None
        topology = {
            "legacy_id": legacy_id,
            "case_id": case.id,
            "plan_id": plan.id,
            "outcome_id": outcome.id,
            "site_id": site.id,
            "company_id": company.id,
            "additional_case_ids": [],
        }
        session.commit()
        yield topology
        # A failed scenario can leave its Session transaction aborted.  Start
        # cleanup from a known state and remove children before their owners.
        session.rollback()
        try:
            session.execute(text("DELETE FROM inspection_decision WHERE inspection_plan_id = :plan_id"), {"plan_id": topology["plan_id"]})
            session.execute(text("DELETE FROM inspection_minutes_record WHERE inspection_outcome_id = :outcome_id"), {"outcome_id": topology["outcome_id"]})
            session.execute(text("DELETE FROM inspection_period_segment WHERE inspection_outcome_id = :outcome_id"), {"outcome_id": topology["outcome_id"]})
            session.execute(text("DELETE FROM inspection_outcome WHERE id = :outcome_id"), {"outcome_id": topology["outcome_id"]})
            session.execute(text("DELETE FROM inspection_plan WHERE id = :plan_id"), {"plan_id": topology["plan_id"]})
            session.execute(text("DELETE FROM \"case\" WHERE id = :case_id"), {"case_id": topology["case_id"]})
            for additional_case_id in topology["additional_case_ids"]:
                session.execute(text("DELETE FROM \"case\" WHERE id = :case_id"), {"case_id": additional_case_id})
            session.execute(text("DELETE FROM site WHERE id = :site_id"), {"site_id": topology["site_id"]})
            session.execute(text("DELETE FROM company WHERE id = :company_id"), {"company_id": topology["company_id"]})
            session.commit()
        except Exception:
            session.rollback()
            raise


def _approved(session: Session, snapshot: dict[str, object], digest: str, monkeypatch):
    monkeypatch.setattr(reconciliation, "CANONICAL_SNAPSHOT_SHA256", digest)
    canonical, decisions, minutes, integrity = reconciliation._read_canonical(session)
    topology = reconciliation.topology_evidence_for_canonical(canonical, owner_integrity=integrity)
    report = reconciliation.build_reconciliation(
        snapshot, canonical, decisions, minutes, expected_snapshot_sha256=digest,
        topology_evidence=topology, owner_integrity=integrity,
    )
    return report["dry_run_apply_plan"], topology


def _post_apply_report(session: Session, snapshot: dict[str, object], digest: str):
    canonical, decisions, minutes, integrity = reconciliation._read_canonical(session)
    topology = reconciliation.topology_evidence_for_canonical(canonical, owner_integrity=integrity)
    return reconciliation.build_reconciliation(
        snapshot, canonical, decisions, minutes, expected_snapshot_sha256=digest,
        topology_evidence=topology, owner_integrity=integrity,
    )


def _validate_disposable_post_apply(report: dict[str, object]) -> None:
    apply.validate_post_apply_reconciliation_contract(
        report,
        decision_counts={"expected_structured_count": 1, "existing_structured_count": 1},
        minutes_counts={
            "expected_structured_count": 0,
            "existing_structured_count": 0,
            "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT": 0,
        },
        expected_outcome_status="PASS_EXACT",
    )


def test_postgres_owner_topology_captures_all_generated_owner_ids(owner_topology):
    for key in ("case_id", "plan_id", "outcome_id", "site_id", "company_id"):
        assert owner_topology[key] is not None


def test_postgres_schema_seed_apply_commit_and_post_apply_reconciliation(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        assert len(approved["actions"]) == 1
        session.rollback()
        with session.begin():
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
    with Session(postgres_engine) as session:
        assert len(list(session.scalars(select(InspectionDecision).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"])))) == 1
        post_apply = _post_apply_report(session, snapshot, digest)
        assert post_apply["reconciliation_outcome"]["data_apply_required"]["count"] == 0
        _validate_disposable_post_apply(post_apply)


def test_postgres_rollback_and_stale_or_conflicting_apply_fail_closed(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        with pytest.raises(RuntimeError, match="injected rollback"):
            with session.begin():
                apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
                raise RuntimeError("injected rollback")
        assert session.scalar(select(InspectionDecision.id).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"]).limit(1)) is None
        session.rollback()
        with session.begin():
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
        with pytest.raises(apply.ApplyFenceError):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)


def test_postgres_conflicting_target_business_key_fails_closed(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        session.add(InspectionDecision(
            inspection_plan_id=owner_topology["plan_id"], ordinal=1, reference="conflict",
            decision_on=date(2016, 8, 29), legacy_raw="conflict",
        ))
        session.commit()
        with pytest.raises(apply.ApplyFenceError):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)


def test_postgres_for_update_owner_lock_blocks_competing_owner_change(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session_a, Session(postgres_engine) as session_b:
        approved, _topology = _approved(session_a, snapshot, digest, monkeypatch)
        session_a.rollback()
        with session_a.begin():
            apply._lock_approved_owners(session_a, approved["actions"][0])
            with session_b.begin():
                session_b.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(OperationalError):
                    session_b.execute(
                        update(InspectionPlan)
                        .where(InspectionPlan.id == owner_topology["plan_id"])
                        .values(decision_reference="competing change")
                    )


def test_postgres_owner_drift_after_approval_rejects_before_insert(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        replacement_case = Case(
            legacy_inspection_id=next(_legacy_ids), site_id=owner_topology["site_id"], gxp_type="GMP", state=CaseState.DRAFT
        )
        session.add(replacement_case)
        session.flush()
        assert replacement_case.id is not None
        replacement_case_id = replacement_case.id
        owner_topology["additional_case_ids"].append(replacement_case_id)
        session.get(InspectionPlan, owner_topology["plan_id"]).case_id = replacement_case_id
        session.commit()
        with pytest.raises(apply.ApplyFenceError, match="InspectionPlan owner changed"):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
        assert session.scalar(select(InspectionDecision.id).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"]).limit(1)) is None
        session.get(InspectionPlan, owner_topology["plan_id"]).case_id = owner_topology["case_id"]
        session.delete(replacement_case)
        owner_topology["additional_case_ids"].remove(replacement_case_id)
        session.commit()


def test_postgres_altered_approved_action_fingerprint_rejects_before_insert(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        action = {**approved["actions"][0], "expected": {**approved["actions"][0]["expected"], "reference": "altered"}}
        altered = {**approved, "actions": [action]}
        with pytest.raises(apply.ApplyFenceError):
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=altered)
        assert session.scalar(select(InspectionDecision.id).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"]).limit(1)) is None


def test_postgres_topology_drift_rejects_before_insert(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        with pytest.raises(reconciliation.ReconciliationFenceError, match="topology"):
            apply.guarded_apply(
                session, snapshot, topology_evidence={**topology, "case_count": topology["case_count"] + 1}, approved_plan=approved
            )
        assert session.scalar(select(InspectionDecision.id).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"]).limit(1)) is None


def test_postgres_snapshot_evidence_drift_rejects_before_insert(postgres_engine, owner_topology, monkeypatch):
    snapshot_a, digest_a = _snapshot(owner_topology["legacy_id"])
    snapshot_b, digest_b = _snapshot(owner_topology["legacy_id"], decision_raw="377/QD-QLD ngày 29/08/2016;")
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot_a, digest_a, monkeypatch)
        session.rollback()
        monkeypatch.setattr(reconciliation, "CANONICAL_SNAPSHOT_SHA256", digest_b)
        with pytest.raises(apply.ApplyFenceError):
            apply.guarded_apply(session, snapshot_b, topology_evidence=topology, approved_plan=approved)
        assert session.scalar(select(InspectionDecision.id).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"]).limit(1)) is None


def test_postgres_competing_writer_after_lock_release_cannot_bypass_fresh_semantic_fence(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as approver:
        approved, topology = _approved(approver, snapshot, digest, monkeypatch)
        approver.rollback()
    attempted = threading.Event()
    completed = threading.Event()
    errors: list[Exception] = []

    def competing_writer() -> None:
        try:
            with Session(postgres_engine) as session:
                with session.begin():
                    attempted.set()
                    session.add(InspectionDecision(
                        inspection_plan_id=owner_topology["plan_id"], ordinal=1, reference="competing",
                        decision_on=date(2016, 8, 29), legacy_raw="competing",
                    ))
                    session.flush()
        except Exception as exc:  # pragma: no cover - asserted below on the VM.
            errors.append(exc)
        finally:
            completed.set()

    with Session(postgres_engine) as lock_holder:
        with lock_holder.begin():
            apply._lock_approved_owners(lock_holder, approved["actions"][0])
            thread = threading.Thread(target=competing_writer)
            thread.start()
            assert attempted.wait(timeout=2)
            assert not completed.wait(timeout=0.2)
        assert completed.wait(timeout=5)
    thread.join(timeout=1)
    assert not errors
    with Session(postgres_engine) as writer:
        with pytest.raises(apply.ApplyFenceError, match="hard semantic conflicts"):
            apply.guarded_apply(writer, snapshot, topology_evidence=topology, approved_plan=approved)
        records = list(writer.scalars(select(InspectionDecision).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"])))
        assert [(item.reference, item.ordinal) for item in records] == [("competing", 1)]


def test_postgres_post_commit_semantic_validator_exercises_success_and_failure_paths(postgres_engine, owner_topology, monkeypatch):
    snapshot, digest = _snapshot(owner_topology["legacy_id"])
    with Session(postgres_engine) as session:
        approved, topology = _approved(session, snapshot, digest, monkeypatch)
        session.rollback()
        with session.begin():
            apply.guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
    with Session(postgres_engine) as session:
        post_apply = _post_apply_report(session, snapshot, digest)
        _validate_disposable_post_apply(post_apply)
        with pytest.raises(apply.ApplyFenceError, match="existing_structured_count"):
            apply.validate_post_apply_reconciliation_contract(
                post_apply,
                decision_counts={"expected_structured_count": 1, "existing_structured_count": 2},
                minutes_counts={
                    "expected_structured_count": 0,
                    "existing_structured_count": 0,
                    "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT": 0,
                },
                expected_outcome_status="PASS_EXACT",
            )
        assert session.scalar(select(InspectionDecision.id).where(InspectionDecision.inspection_plan_id == owner_topology["plan_id"]).limit(1)) is not None
