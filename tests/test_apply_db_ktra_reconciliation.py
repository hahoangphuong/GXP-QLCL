from __future__ import annotations

from datetime import date
from hashlib import sha256
import json

import pytest

from backend.app.db.models.phase1 import Case, CaseApplication, InspectionOutcome
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
    assert report["entities_changed"] == 3
    repeat = apply.preflight_and_apply(session, {"facts": facts}, [{"ID": "1", "decision_reference": raw}])
    assert repeat["entities_changed"] == 0


def test_live_target_and_apply_cli_are_inert_without_explicit_flag(monkeypatch, tmp_path):
    with pytest.raises(apply.ApplyFenceError, match="without --apply-rehearsal"):
        apply.main(["--plan", str(tmp_path / "p.json"), "--expected-plan-sha256", "0" * 64, "--report-output", str(tmp_path / "r.json")])
    assert "SET TRANSACTION READ ONLY" not in apply.run_apply.__code__.co_consts
