from __future__ import annotations

import json
from pathlib import Path


CONTRACT_PATH = Path("artifacts/legacy_audit/db_ktra_domain_contract_v1.json")
REQUIRED_FACT_KEYS = {
    "legacy_source",
    "business_meaning",
    "cardinality",
    "canonical_owner",
    "semantic_type",
    "runtime_writer",
    "runtime_reader",
    "api_contract",
    "compatibility_fields",
    "migration_source",
    "parser_owner",
    "invariants",
    "unresolved_cases",
    "deprecation_plan",
    "implementation_slice",
}


def test_db_ktra_domain_contract_is_complete_and_design_only() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["contract_version"] == 1
    assert contract["status"] == "DESIGN_ONLY"
    assert len(contract["facts"]) == 10
    assert all(REQUIRED_FACT_KEYS <= fact.keys() for fact in contract["facts"])


def test_db_ktra_contract_preserves_the_authoritative_separations() -> None:
    facts = {fact["legacy_source"]: fact for fact in json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))["facts"]}

    assert facts["db.ktra.Kết quả"]["canonical_owner"] == "InspectionOutcome.outcome_result"
    assert "CaseAssessment.assessment_result" in facts["db.ktra.Kết quả"]["invariants"][0]
    minutes = facts["db.ktra.B. bản"]
    assert "minutes_recorded_time" in minutes["canonical_owner"]
    assert "time zone" in minutes["invariants"][-1]
    assert "inspected_on" in minutes["invariants"][1]
    assert "inspected_to_on" in minutes["invariants"][1]
    assert facts["db.ktra.PHIẾU TRÌNH PCT"]["cardinality"] == "0..n PCT submissions per case"
    assert facts["db.ktra.PHIẾU TRÌNH CT"]["cardinality"] == "0..n CT submissions per case"
    assert "completed_on" in facts["db.ktra.PHIẾU TRÌNH PCT"]["invariants"][2]
    assert "same-case PCT" in facts["db.ktra.PHIẾU TRÌNH CT"]["invariants"][2]
    assert "role_code" in facts["db.ktra.T.tra viên"]["semantic_type"]
    assert facts["db.ktra.HẠN KT TUÂN THỦ"]["invariants"][0] == "INFORMATIONAL_ONLY."
    assert facts["db.ktra.ID CC GPs"]["cardinality"] == "0..1 certificate per legacy inspection row"


def test_db_ktra_schema_design_has_no_placeholder_types_or_ambiguous_owners() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    design = Path("docs/DB_KTRA_DOMAIN_CONTRACT_DESIGN.md").read_text(encoding="utf-8")

    assert "VARCHAR(...)" not in design
    assert "minutes_recorded_time TIME NULL" in design
    assert "completed_on DATE NULL" in design
    assert "role_code VARCHAR(16) NOT NULL" in design
    assert "UNIQUE(team_id, sort_order)" in design
    assert "CHECK(sort_order >= 1)" in design
    approval = next(entry for entry in contract["schema_contract"] if entry["table"] == "inspection_approval_submission")
    assert "status" not in {field["name"] for field in approval["fields"]}
    assert "CT parent completed_on is non-NULL" in approval["service_only_invariants"]
