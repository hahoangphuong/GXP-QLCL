"""Guarded writer for the narrow Snapshot V2 repeatable reconciliation envelope.

This is intentionally separate from the V1 Batch 6 writer.  It writes only a
freshly reconciled, explicitly approved V2 action set and never discovers a
broader write envelope on its own.
"""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, InspectionDecision, InspectionPlan
from backend.app.domain.legacy_db_ktra_repeatable_v2 import parse_v2_repeatable_rows
from tools import reconcile_db_ktra_repeatable_v2 as reconciliation


APPLY_PLAN_SCHEMA_VERSION = "b6b-repeatable-v2-dry-run-apply/v1"
APPLY_REPORT_SCHEMA_VERSION = "b6b-repeatable-v2-apply/v1"
POST_APPLY_DECISION_COUNTS = {
    "expected_structured_count": 1220,
    "existing_structured_count": 1220,
}
POST_APPLY_MINUTES_COUNTS = {
    "expected_structured_count": 1162,
    "existing_structured_count": 1162,
    "EXCEL_SERIAL_DATE_REPRESENTATION_EQUIVALENT": 1149,
}


class ApplyFenceError(RuntimeError):
    """Raised when a V2 apply precondition is not proven exactly."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ApplyFenceError(message)


def safe_error_summary(error: Exception) -> str:
    summary = str(error)
    summary = re.sub(r"(?i)(password|pwd)=([^\s&;]+)", r"\1=[REDACTED]", summary)
    return re.sub(r"(postgresql(?:\+[^:]+)?://)[^/@\s]+@", r"\1[REDACTED]@", summary)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def action_fingerprint(plan: Mapping[str, Any]) -> str:
    """Hash the exact deterministic safe action envelope, never a connection URL."""
    return sha256(_canonical_bytes(plan.get("actions"))).hexdigest()


def load_approved_plan(path: Path, *, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    _require(sha256(raw).hexdigest() == expected_sha256.lower(), "approved action plan SHA256 fence failed")
    payload = json.loads(raw)
    _require(isinstance(payload, dict) and payload.get("schema_version") == APPLY_PLAN_SCHEMA_VERSION, "approved action plan schema is invalid")
    _require(payload.get("write_authorized") is False and payload.get("writer_invoked") is False, "approved action plan is not a dry-run plan")
    _require(isinstance(payload.get("actions"), list), "approved action plan actions are invalid")
    return payload


def _validate_fresh_plan(fresh: Mapping[str, Any], approved: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Accept only the one approved, conflict-free V2 decision insert envelope."""
    owners = fresh["owners"]
    _require(owners["case_universe"]["case_universe_status"] == "PASS", "fresh reconciliation Case universe changed")
    _require(owners["owner_integrity"]["status"] == "PASS", "fresh reconciliation owner integrity changed")
    _require(fresh["reconciliation_outcome"]["hard_semantic_conflicts"]["count"] == 0, "fresh reconciliation has hard semantic conflicts")
    current = fresh["dry_run_apply_plan"]
    _require(current.get("schema_version") == APPLY_PLAN_SCHEMA_VERSION, "fresh dry-run plan schema is invalid")
    _require(action_fingerprint(current) == action_fingerprint(approved), "fresh reconciliation action set differs from approved plan")
    actions = current["actions"]
    _require(len(actions) == 1, "fresh reconciliation does not contain exactly one write action")
    action = actions[0]
    _require(action.get("kind") == "decisions", "fresh reconciliation action kind is unsupported")
    _require(action.get("classification") == "DATA_APPLY_REQUIRED", "fresh reconciliation action is not writable")
    for key in ("legacy_inspection_id", "canonical_case_id", "inspection_plan_id", "source_ordinal"):
        _require(action.get(key) is not None, f"fresh reconciliation action lacks {key}")
    return actions


def _approved_single_action(approved: Mapping[str, Any]) -> dict[str, Any]:
    """Validate only enough approved data to identify rows to lock.

    The source payload itself is never trusted here.  Fresh reconciliation
    after those locks are held proves every semantic field and fingerprint.
    """
    _require(approved.get("schema_version") == APPLY_PLAN_SCHEMA_VERSION, "approved action plan schema is invalid")
    actions = approved.get("actions")
    _require(isinstance(actions, list) and len(actions) == 1, "approved action plan must contain exactly one action")
    action = actions[0]
    _require(isinstance(action, dict) and action.get("kind") == "decisions", "approved action kind is unsupported")
    for key in ("legacy_inspection_id", "canonical_case_id", "inspection_plan_id", "source_ordinal"):
        _require(action.get(key) is not None, f"approved action lacks {key}")
    return action


def fresh_preflight(
    session: Session,
    snapshot: Mapping[str, Any],
    *,
    topology_evidence: Mapping[str, Any],
    approved_plan: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Rebuild the V2 reconciliation immediately before opening a write path."""
    canonical, decisions, minutes, owner_integrity = reconciliation._read_canonical(session)
    fresh = reconciliation.build_reconciliation(
        snapshot,
        canonical,
        decisions,
        minutes,
        expected_snapshot_sha256=reconciliation.CANONICAL_SNAPSHOT_SHA256,
        topology_evidence=topology_evidence,
        owner_integrity=owner_integrity,
    )
    return fresh, _validate_fresh_plan(fresh, approved_plan)


def _source_decision(action: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = {
        row["legacy_inspection_id"]: row
        for row in parse_v2_repeatable_rows(snapshot, expected_snapshot_sha256=reconciliation.CANONICAL_SNAPSHOT_SHA256)
    }
    source = rows.get(action["legacy_inspection_id"])
    _require(source is not None and source["decisions"]["state"] == "KNOWN", "approved decision source is no longer structured")
    ordinal = action["source_ordinal"]
    _require(isinstance(ordinal, int) and ordinal >= 1, "approved decision source ordinal is invalid")
    occurrences = source["decisions"]["occurrences"]
    _require(ordinal <= len(occurrences), "approved decision source ordinal is absent")
    occurrence = occurrences[ordinal - 1]
    _require(reconciliation._safe_occurrence(occurrence) == action["expected"], "approved decision evidence differs from Snapshot V2")
    _require(occurrence.get("relation_type") is None, "decision relation apply is not approved in this envelope")
    return occurrence


def _one(session: Session, statement: Any, message: str) -> Any:
    values = list(session.scalars(statement))
    _require(len(values) == 1, message)
    return values[0]


def _lock_approved_owners(session: Session, approved_action: Mapping[str, Any]) -> tuple[Case, InspectionPlan]:
    """Acquire target locks before any semantic authorization is rebuilt."""
    case = _one(
        session,
        select(Case)
        .where(Case.legacy_inspection_id == approved_action["legacy_inspection_id"])
        .with_for_update(),
        "approved action Case owner is not unique",
    )
    _require(case.id == approved_action["canonical_case_id"], "approved action Case owner changed")
    _require(case.legacy_inspection_id == approved_action["legacy_inspection_id"], "approved action Case legacy identity changed")
    plan = _one(
        session,
        select(InspectionPlan).where(InspectionPlan.id == approved_action["inspection_plan_id"]).with_for_update(),
        "approved action InspectionPlan owner is not unique",
    )
    _require(plan.case_id == case.id, "approved action InspectionPlan owner changed")
    return case, plan


def guarded_apply(
    session: Session,
    snapshot: Mapping[str, Any],
    *,
    topology_evidence: Mapping[str, Any],
    approved_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Insert the one fenced decision in one caller-owned explicit transaction."""
    _require(not session.new and not session.dirty and not session.deleted, "B6B apply requires a clean SQLAlchemy Session")
    approved_action = _approved_single_action(approved_plan)
    # Lock first: the fresh semantic proof below must see the same protected
    # target owner state that the eventual insert uses.
    case, plan = _lock_approved_owners(session, approved_action)
    fresh, actions = fresh_preflight(
        session, snapshot, topology_evidence=topology_evidence, approved_plan=approved_plan
    )
    action = actions[0]
    _require(action["canonical_case_id"] == case.id, "fresh reconciliation Case owner changed")
    _require(action["inspection_plan_id"] == plan.id, "fresh reconciliation InspectionPlan owner changed")
    _require(case.legacy_inspection_id == action["legacy_inspection_id"], "fresh reconciliation Case legacy identity changed")
    _require(plan.case_id == case.id, "fresh reconciliation InspectionPlan ownership changed")
    occurrence = _source_decision(action, snapshot)
    existing = list(
        session.scalars(
            select(InspectionDecision)
            .where(InspectionDecision.inspection_plan_id == plan.id, InspectionDecision.ordinal == action["source_ordinal"])
            .with_for_update()
        )
    )
    _require(not existing, "approved action target business key is no longer absent")
    inserted = InspectionDecision(
        inspection_plan_id=plan.id,
        ordinal=occurrence["ordinal"],
        reference=occurrence["reference"],
        decision_on=occurrence["decision_on"],
        legacy_raw=occurrence["legacy_raw"],
        relation_type=None,
        related_decision_id=None,
    )
    session.add(inserted)
    session.flush()
    return {
        "fresh_reconciliation": fresh,
        "action_fingerprint": action_fingerprint(approved_plan),
        "inserted": {
            "id": inserted.id,
            "inspection_plan_id": inserted.inspection_plan_id,
            "ordinal": inserted.ordinal,
            "reference": inserted.reference,
            "decision_on": inserted.decision_on.isoformat(),
        },
    }


def verify_write_target(connection: Any) -> None:
    """Keep write target/revision fences exact; never permit SQLite or production."""
    _require(connection.execute(text("SELECT current_database()")).scalar_one() == reconciliation.REHEARSAL_DATABASE, "B6B apply connected to an unexpected database")
    _require(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == reconciliation.REQUIRED_REVISION, "B6B apply requires the expected Alembic revision")


def validate_post_apply_reconciliation_contract(
    post_apply: Mapping[str, Any],
    *,
    decision_counts: Mapping[str, int],
    minutes_counts: Mapping[str, int],
    expected_outcome_status: str,
) -> None:
    """Validate one immutable reconciliation expectation contract.

    Production passes the approved whole-workbook contract below.  The
    disposable PostgreSQL integration uses a deliberately smaller immutable
    contract to exercise this same post-commit semantic control path.
    """
    owners = post_apply.get("owners", {})
    _require(owners.get("case_universe", {}).get("case_universe_status") == "PASS", "post-apply Case universe failed")
    _require(owners.get("owner_integrity", {}).get("status") == "PASS", "post-apply owner integrity failed")
    outcome = post_apply.get("reconciliation_outcome", {})
    _require(outcome.get("hard_semantic_conflicts", {}).get("count") == 0, "post-apply has hard semantic conflicts")
    _require(outcome.get("data_apply_required", {}).get("count") == 0, "post-apply still requires data apply")
    _require(post_apply.get("dry_run_apply_plan", {}).get("actions") == [], "post-apply still has write actions")
    decisions = post_apply.get("decisions", {})
    minutes = post_apply.get("minutes", {})
    for key, expected in decision_counts.items():
        _require(decisions.get(key) == expected, f"post-apply decisions {key} is unexpected")
    for key, expected in minutes_counts.items():
        if key in minutes:
            _require(minutes.get(key) == expected, f"post-apply minutes {key} is unexpected")
        else:
            _require(minutes.get("classification_counts", {}).get(key) == expected, f"post-apply minutes {key} is unexpected")
    zero_counts = (
        "MISSING_IN_DB", "EXTRA_IN_DB", "FIELD_MISMATCH", "OWNER_MISMATCH",
        "RELATION_MISMATCH", "CANONICAL_CASE_MISSING", "UNEXPECTED_OWNER_MISSING",
    )
    for section, report in (("decisions", decisions), ("minutes", minutes)):
        counts = report.get("classification_counts", {})
        for key in zero_counts:
            _require(counts.get(key, 0) == 0, f"post-apply {section} {key} is nonzero")
    _require(outcome.get("status") == expected_outcome_status, "post-apply outcome status is unexpected")


def validate_post_apply_reconciliation(post_apply: Mapping[str, Any]) -> None:
    """Require the exact approved production parity after the one commit."""
    validate_post_apply_reconciliation_contract(
        post_apply,
        decision_counts=POST_APPLY_DECISION_COUNTS,
        minutes_counts=POST_APPLY_MINUTES_COUNTS,
        expected_outcome_status="INCOMPLETE_EVIDENCE",
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish the latest lifecycle result without a partially-written file."""
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded Snapshot V2 B6B repeatable apply.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--snapshot", type=Path, default=reconciliation.SNAPSHOT)
    parser.add_argument("--topology-evidence", type=Path, required=True)
    parser.add_argument("--expected-topology-sha256", required=True)
    parser.add_argument("--approved-action-plan", type=Path, required=True)
    parser.add_argument("--expected-approved-action-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Explicitly authorize the one fenced rehearsal write.")
    args = parser.parse_args(argv)
    try:
        reconciliation.validate_target_url(args.database_url)
        snapshot = reconciliation.load_verified_snapshot_file(args.snapshot.resolve())
        topology = reconciliation.load_verified_topology_file(
            args.topology_evidence.resolve(), expected_sha256=args.expected_topology_sha256
        )
        approved = load_approved_plan(
            args.approved_action_plan.resolve(), expected_sha256=args.expected_approved_action_sha256
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        # The pre-apply run is deliberately read-only and is persisted before
        # any optional write connection is opened.
        pre_apply = reconciliation.run(args.database_url, snapshot, topology_evidence=topology)
        _validate_fresh_plan(pre_apply, approved)
        _write_json(args.output_dir / "b6b_v2_pre_apply_reconciliation.json", pre_apply)
        _write_json(args.output_dir / "b6b_v2_approved_action_fingerprint.json", {
            "action_count": len(approved["actions"]),
            "action_fingerprint": action_fingerprint(approved),
            "snapshot_sha256": reconciliation.CANONICAL_SNAPSHOT_SHA256,
        })
        if not args.apply:
            _write_json(args.output_dir / "b6b_v2_apply_result.json", {
                "schema_version": APPLY_REPORT_SCHEMA_VERSION,
                "status": "DRY_RUN_ONLY",
                "transaction_committed": False,
                "database_mutated": False,
                "writer_invoked": False,
                "action_count": len(approved["actions"]),
                "action_fingerprint": action_fingerprint(approved),
                "snapshot_sha256": reconciliation.CANONICAL_SNAPSHOT_SHA256,
            })
            return 0
        engine = create_engine(args.database_url, future=True)
        apply_result: dict[str, Any] = {
            "schema_version": APPLY_REPORT_SCHEMA_VERSION,
            "writer_invoked": True,
            "transaction_committed": False,
            "database_mutated": False,
            "action_count": len(approved["actions"]),
            "action_fingerprint": action_fingerprint(approved),
            "snapshot_sha256": reconciliation.CANONICAL_SNAPSHOT_SHA256,
        }
        commit_started = False
        try:
            with Session(engine) as session:
                try:
                    verify_write_target(session.connection())
                    applied = guarded_apply(session, snapshot, topology_evidence=topology, approved_plan=approved)
                    commit_started = True
                    session.commit()
                except Exception as exc:
                    if commit_started:
                        # A driver may fail after the server accepted COMMIT;
                        # never invent a rollback or mutation outcome.
                        apply_result.update({
                            "status": "WRITE_TRANSACTION_COMMIT_ERROR_OUTCOME_UNCONFIRMED",
                            "transaction_committed": None,
                            "database_mutated": None,
                            "safe_error": safe_error_summary(exc),
                        })
                    else:
                        session.rollback()
                        apply_result.update({
                            "status": "WRITE_TRANSACTION_ROLLED_BACK",
                            "database_mutated": False,
                            "safe_error": safe_error_summary(exc),
                        })
                    _write_json(args.output_dir / "b6b_v2_apply_result.json", apply_result)
                    return 3
            apply_result.update({
                "status": "COMMITTED_PENDING_POST_APPLY_VERIFICATION",
                "transaction_committed": True,
                "database_mutated": True,
                "action_fingerprint": applied["action_fingerprint"],
                "inserted": applied["inserted"],
            })
        finally:
            engine.dispose()
        try:
            post_apply = reconciliation.run(args.database_url, snapshot, topology_evidence=topology)
        except Exception as exc:
            _write_json(args.output_dir / "b6b_v2_apply_result.json", {
                **apply_result,
                "status": "POST_APPLY_RECONCILIATION_ERROR",
                "safe_error": safe_error_summary(exc),
            })
            return 4
        _write_json(args.output_dir / "b6b_v2_post_apply_reconciliation.json", post_apply)
        try:
            validate_post_apply_reconciliation(post_apply)
        except ApplyFenceError as exc:
            _write_json(args.output_dir / "b6b_v2_apply_result.json", {
                **apply_result,
                "status": "POST_APPLY_VERIFICATION_FAILED",
                "post_apply_verification_error": safe_error_summary(exc),
            })
            return 4
        _write_json(args.output_dir / "b6b_v2_apply_result.json", {
            **apply_result,
            "status": "APPLY_VERIFIED_SUCCESS",
        })
        return 0
    except Exception as exc:
        raise SystemExit(f"B6B V2 apply failed: {safe_error_summary(exc)}") from None


if __name__ == "__main__":
    raise SystemExit(main())
