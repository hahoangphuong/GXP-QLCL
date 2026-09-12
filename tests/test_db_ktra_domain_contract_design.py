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
    assert facts["db.ktra.B. bản"]["canonical_owner"].startswith("InspectionOutcome.minutes_recorded_on")
    assert facts["db.ktra.PHIẾU TRÌNH PCT"]["cardinality"] == "0..n PCT submissions per case"
    assert facts["db.ktra.PHIẾU TRÌNH CT"]["cardinality"] == "0..n CT submissions per case"
    assert facts["db.ktra.ID CC GPs"]["cardinality"] == "0..1 certificate per legacy inspection row"
