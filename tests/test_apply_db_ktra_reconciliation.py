from __future__ import annotations

from datetime import date
from hashlib import sha256
import json

import pytest

from backend.app.db.models.phase1 import Case, CaseApplication, InspectionOutcome, InspectionPlan
from backend.app.domain.legacy_db_ktra_reconciliation import parse_legacy_inspection_decision, safe_evidence
from tools import apply_db_ktra_reconciliation as apply


def _fact(name: str, parsed: dict[str, object], classification: str) -> dict[str, object]:
    return {
        "legacy_row": 1, "legacy_case_id": 1, "fact": name,
        "classification": classification, "source_state": parsed["state"],
        "source_raw_hash": safe_evidence(parsed["raw"])["source_raw_hash"],
        "parsed_value": apply._safe_parsed(parsed),
    }


def test_plan_fences_reject_sha_schema_status_and_readonly_provenance(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"schema_version": "wrong", "comparison_status": "NOT_RUN"}), encoding="utf-8")
    with pytest.raises(apply.ApplyFenceError, match="SHA256"):
        apply.load_and_validate_plan(path, "0" * 64)
    digest = sha256(path.read_bytes()).hexdigest()
    with pytest.raises(apply.ApplyFenceError, match="compared"):
        apply.load_and_validate_plan(path, digest)
    path.write_text(json.dumps({"schema_version": apply.PLAN_SCHEMA_VERSION, "comparison_status": "COMPARED", "read_only_connection": {"database": "wrong", "revision": "wrong", "transaction_read_only": False}}), encoding="utf-8")
    with pytest.raises(apply.ApplyFenceError, match="provenance"):
        apply.load_and_validate_plan(path, sha256(path.read_bytes()).hexdigest())


def test_source_replay_rejects_hash_and_parser_mismatch():
    raw = "368/QĐ-QLD ngày 24/08/2016"
    parsed = parse_legacy_inspection_decision(raw)
    fact = _fact("decision_reference", parsed, "SAFE_DIRECT")
    apply.validate_source_replay([fact], [{"ID": "1", "decision_reference": raw}])
    fact["source_raw_hash"] = "0" * 64
    with pytest.raises(apply.ApplyFenceError, match="source replay"):
        apply.validate_source_replay([fact], [{"ID": "1", "decision_reference": raw}])


class _Result:
    def __init__(self, value): self.value = value
    def first(self): return self.value


class _FakeSession:
    def __init__(self, case, application, outcome):
        self.case, self.application, self.outcome = case, application, outcome
        self.assessment = None
        self.plan = None
        self.flushes = 0
    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        return _Result({Case: self.case, CaseApplication: self.application, InspectionOutcome: self.outcome}.get(entity, self.plan))
    def add(self, item):
        item.id = "plan-1"
        item.row_version = 1
        self.plan = item
    def flush(self): self.flushes += 1
    def protected_counts(self):
        return {"inspection_period_segments": 0, "inspection_teams": 0, "inspection_team_members": 0, "approval_submissions": 0, "certificates": 0, "certificate_versions": 0, "certificate_scopes": 0, "capa_cycles": 0}


def test_decision_owner_move_is_atomic_and_idempotent_without_database(monkeypatch):
    raw = "368/QĐ-QLD ngày 24/08/2016"
    parsed = parse_legacy_inspection_decision(raw)
    facts = [
        _fact("decision_reference", parsed, "SAFE_DIRECT"),
        _fact("decision_date", parsed, "SAFE_DIRECT"),
        _fact("decision_legacy_raw", parsed, "SAFE_DIRECT"),
        _fact("application_dossier_reference_contamination", parsed, "CONTAMINATED_EXACT_COPY"),
        _fact("outcome_decision_reference_contamination", parsed, "CONTAMINATED_EXACT_COPY"),
    ]
    monkeypatch.setattr(apply, "EXPECTED_FACT_COUNTS", {name: 1 for name in ("decision_reference", "decision_date", "decision_legacy_raw", "application_dossier_reference_contamination", "outcome_decision_reference_contamination")})
    case = Case(id="case-1", legacy_inspection_id=1, site_id="site-1", gxp_type="GMP")
    application = CaseApplication(id="app-1", case_id="case-1", dossier_reference=raw, row_version=1)
    outcome = InspectionOutcome(id="outcome-1", case_id="case-1", decision_reference=raw, inspected_on=date(2020, 1, 1), row_version=1)
    session = _FakeSession(case, application, outcome)
    report = apply.preflight_and_apply(session, {"facts": facts}, [{"ID": "1", "decision_reference": raw}])
    assert (session.plan.decision_reference, session.plan.decision_date, session.plan.decision_legacy_raw) == ("368/QĐ-QLD", date(2016, 8, 24), raw)
    assert application.dossier_reference is None and outcome.decision_reference is None
    assert outcome.inspected_on == date(2020, 1, 1)
    assert outcome.row_version == 2 and application.row_version == 2
    assert report["entities_changed"] == 3
    assert report["protected_state"]["inspection_period_segments_before"] == 0
    repeat = apply.preflight_and_apply(session, {"facts": facts}, [{"ID": "1", "decision_reference": raw}])
    assert repeat["entities_changed"] == 0


def test_live_target_and_apply_cli_are_inert_without_explicit_flag(monkeypatch, tmp_path):
    report_path = tmp_path / "r.json"
    with pytest.raises(apply.ApplyFenceError, match="without --apply-rehearsal"):
        apply.main(["--plan", str(tmp_path / "p.json"), "--expected-plan-sha256", "0" * 64, "--report-output", str(report_path)])
    assert json.loads(report_path.read_text(encoding="utf-8"))["failure_stage"] == "validation"
    assert "SET TRANSACTION READ ONLY" not in apply.run_apply.__code__.co_consts


def test_null_idempotency_contract_is_explicit():
    assert apply._require_same_or_empty(None, None, "x") is False
    assert apply._require_same_or_empty(None, date(2026, 1, 1), "x") is True
    assert apply._require_same_or_empty(date(2026, 1, 1), date(2026, 1, 1), "x") is False
    with pytest.raises(apply.ApplyFenceError, match="conflict"):
        apply._require_same_or_empty(date(2026, 1, 1), date(2026, 1, 2), "x")


def test_new_plans_are_tracked_by_python_identity_without_version_bumps():
    first = InspectionPlan(case_id="case-1")
    second = InspectionPlan(case_id="case-2")
    persisted = InspectionOutcome(id="outcome-1", case_id="case-1", row_version=4)
    changed = {id(first): first, id(second): second, id(persisted): persisted}

    apply._bump_changed_entities(changed, {id(first), id(second)})

    assert id(first) != id(second)
    assert first.row_version is None and second.row_version is None
    assert persisted.row_version == 5


def test_protected_state_rejects_any_excluded_mutation():
    case = Case(id="case-1", legacy_inspection_id=1, site_id="site-1", gxp_type="GMP", state="OPEN")
    outcome = InspectionOutcome(id="outcome-1", case_id="case-1", inspected_on=date(2026, 1, 1), inspected_to_on=date(2026, 1, 2), inspection_period_state="CONFIRMED")
    counts = {"inspection_period_segments": 1, "inspection_teams": 2, "inspection_team_members": 3, "approval_submissions": 4, "certificates": 5, "certificate_versions": 6, "certificate_scopes": 7, "capa_cycles": 8}
    before = apply._protected_evidence([case], [outcome], counts)

    assert apply._verify_protected_state(before, [case], [outcome], counts)["certificates_after"] == 5
    outcome.inspected_to_on = date(2026, 1, 3)
    with pytest.raises(apply.ApplyFenceError, match="protected"):
        apply._verify_protected_state(before, [case], [outcome], counts)


def test_failure_report_is_written_without_connecting_to_database(monkeypatch, tmp_path):
    report_path = tmp_path / "failure.json"
    plan_path = tmp_path / "bad.json"
    plan_path.write_text("{}", encoding="utf-8")
    with pytest.raises(apply.ApplyFenceError):
        apply.main(["--dry-run-rehearsal", "--plan", str(plan_path), "--expected-plan-sha256", sha256(plan_path.read_bytes()).hexdigest(), "--report-output", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["transaction_committed"] is False
    assert report["failure_stage"] == "validation"
    assert report["plan_validated"] is False


def test_failure_report_redacts_connection_credentials_without_connecting(monkeypatch, tmp_path):
    report_path = tmp_path / "failure.json"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")
    error = apply.ApplyExecutionError(
        "postgresql://operator:secret@db.example/gxp",
        {"failure_stage": "live_transaction", "transaction_rolled_back": True},
    )
    monkeypatch.setattr(apply, "load_and_validate_plan", lambda *_args: (_ for _ in ()).throw(error))

    with pytest.raises(apply.ApplyExecutionError):
        apply.main(["--dry-run-rehearsal", "--plan", str(plan_path), "--expected-plan-sha256", sha256(plan_path.read_bytes()).hexdigest(), "--report-output", str(report_path)])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "secret" not in report["error_summary"]
    assert "[REDACTED]" in report["error_summary"]


def test_dry_run_writes_rollback_evidence_without_a_database_connection(monkeypatch, tmp_path):
    report_path = tmp_path / "dry-run.json"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")
    plan = {"facts": []}
    monkeypatch.setattr(apply, "load_and_validate_plan", lambda *_args: plan)
    monkeypatch.setattr(apply, "validate_snapshot_provenance", lambda *_args: [])
    monkeypatch.setattr(apply, "_eligible_facts", lambda *_args: [])
    monkeypatch.setenv("DATABASE_URL", "postgresql://not-used")
    observed: dict[str, object] = {}

    def fake_run(_database_url, _plan, _snapshot_rows, *, dry_run):
        observed["dry_run"] = dry_run
        return {
            "database": apply.REHEARSAL_DATABASE,
            "revision": apply.REQUIRED_REVISION,
            "transaction_committed": False,
            "transaction_rolled_back": True,
        }

    monkeypatch.setattr(apply, "run_apply", fake_run)
    assert apply.main(["--dry-run-rehearsal", "--plan", str(plan_path), "--expected-plan-sha256", sha256(plan_path.read_bytes()).hexdigest(), "--report-output", str(report_path)]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert observed == {"dry_run": True}
    assert report["dry_run"] is True and report["transaction_rolled_back"] is True
