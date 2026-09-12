from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "artifacts" / "legacy_audit" / "inspection_case_lifecycle_owner_matrix.json"
CONTRACT_PATH = ROOT / "artifacts" / "legacy_audit" / "inspection_case_lifecycle_canonical_owner_contract.json"
MODEL_PATH = ROOT / "backend" / "app" / "db" / "models" / "phase1.py"


def _class_fields() -> dict[str, set[str]]:
    tree = ast.parse(MODEL_PATH.read_text(encoding="utf-8"))
    classes: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        fields: set[str] = set()
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.add(item.target.id)
        classes[node.name] = fields
    return classes


def _load() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _load_contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_lifecycle_matrix_status_and_guardrails_are_fail_closed():
    report = _load()
    assert report["schema_version"] == "inspection-case-lifecycle-owner-matrix/v1"
    assert report["status"] == "BUSINESS_LIFECYCLE_CONFIRMED_SCHEMA_RECONCILED"
    assert report["guardrails"] == {
        "legacy_display_prose_is_truth": False,
        "compatibility_projection_proves_owner": False,
        "schema_change_authorized": False,
        "document_readiness_authorized": False,
    }
    assert report["decision"]["schema_migration"] == "NOT_YET_AUTHORIZED"


def test_every_existing_owner_is_present_in_current_model_source():
    report = _load()
    classes = _class_fields()
    existing = {
        "OWNER_PROVEN_EXISTING",
        "OWNER_PROVEN_EXISTING_WITH_NAMING_REVIEW",
    }
    for owner in report["owners"]:
        if owner["classification"] not in existing:
            continue
        model = owner["model"]
        field = owner["field"]
        assert model in classes, owner
        assert field in classes[model], owner
        for supporting in owner.get("supporting_fields", []):
            supporting_model, supporting_field = supporting.split(".", 1)
            assert supporting_model in classes, supporting
            assert supporting_field in classes[supporting_model], supporting


def test_model_extension_rows_are_real_gaps_not_existing_fields():
    report = _load()
    classes = _class_fields()
    for owner in report["owners"]:
        if owner["classification"] != "OWNER_NEEDS_MODEL_EXTENSION":
            continue
        model = owner["model"]
        field = owner["field"]
        assert model in classes, owner
        assert field not in classes[model], owner
        for compatibility in owner.get("current_compatibility_fields", []):
            compatibility_model, compatibility_field = compatibility.split(".", 1)
            assert compatibility_model in classes, compatibility
            assert compatibility_field in classes[compatibility_model], compatibility


def test_new_entity_is_not_silently_claimed_to_exist():
    report = _load()
    classes = _class_fields()
    new_entity_rows = [owner for owner in report["owners"] if owner["classification"] == "OWNER_NEEDS_NEW_ENTITY"]
    assert [owner["key"] for owner in new_entity_rows] == ["approval_submission"]
    assert new_entity_rows[0]["model"] not in classes
    assert report["planned_new_entity"]["fixed_pct_ct_columns_recommended"] is False


def test_lifecycle_has_no_duplicate_semantic_keys():
    report = _load()
    keys = [owner["key"] for owner in report["owners"]]
    assert len(keys) == len(set(keys))


def test_qdkt_owner_stays_planning_phase_and_not_outcome_truth():
    report = _load()
    by_key = {owner["key"]: owner for owner in report["owners"]}
    reference = by_key["inspection_decision_reference"]
    decision_date = by_key["inspection_decision_date"]
    assert reference["model"] == "InspectionPlan"
    assert decision_date["model"] == "InspectionPlan"
    assert reference["classification"] == "OWNER_NEEDS_MODEL_EXTENSION"
    assert decision_date["classification"] == "OWNER_NEEDS_MODEL_EXTENSION"
    assert "InspectionOutcome.decision_reference" in reference["current_compatibility_fields"]


def test_capa_is_one_repeatable_owner_not_round_specific_schema():
    report = _load()
    by_key = {owner["key"]: owner for owner in report["owners"]}
    assert by_key["capa_round"] == {
        "key": "capa_round",
        "lifecycle": "capa",
        "model": "CapaCycle",
        "field": "round_no",
        "classification": "OWNER_PROVEN_EXISTING",
    }
    assert by_key["capa_incoming_reference"]["model"] == "CapaCycle"
    assert by_key["capa_incoming_reference"]["classification"] == "OWNER_NEEDS_MODEL_EXTENSION"


def test_certificate_truth_is_version_owned():
    report = _load()
    by_key = {owner["key"]: owner for owner in report["owners"]}
    for key in ("certificate_number", "certificate_issue_date", "certificate_expiry_date"):
        assert by_key[key]["model"] == "CertificateVersion"
        assert by_key[key]["classification"] == "OWNER_PROVEN_EXISTING"


def test_canonical_owner_contract_is_design_only_and_has_no_legacy_write_authority():
    report = _load_contract()
    assert report["schema_version"] == "inspection-case-lifecycle-canonical-owner-contract/v1"
    assert report["status"] == "DESIGN_ONLY_NO_SCHEMA_OR_BACKFILL"
    assert report["decision"] == {
        "schema_changes": "NOT_IMPLEMENTED_BY_TASK_CONSTRAINT",
        "importer_changes": "IMPLEMENTED_NGAY_KTRA_EXCLUSIVE_PERIOD_MAPPING",
        "backfill": "NOT_PERFORMED",
        "qd_kt_readiness": "BUSINESS_INPUT_CONTRACT_MISSING",
        "reason": "structured planning decision reference/date and other active inputs remain unowned; do not enable create/readiness or parse composite legacy prose",
    }
    assert report["guardrails"] == {
        "database_mutated": False,
        "workbook_mutated": False,
        "nas_mutated": False,
        "legacy_prose_is_runtime_truth": False,
        "current_date_fallback_allowed": False,
        "display_prose_parsed_as_truth": False,
    }


def test_canonical_contract_keeps_decision_and_bbkt_gaps_explicit():
    owners = {owner["canonical_fact"]: owner for owner in _load_contract()["owners"]}
    assert owners["inspection_decision_reference"]["status"] == "OWNER_MISSING_COMPATIBILITY_FIELDS_EXIST"
    assert owners["inspection_decision_date"]["status"] == "OWNER_MISSING"
    assert owners["inspection_decision_reference"]["semantic_owner"] == "InspectionPlan.decision_reference (future field)"
    assert owners["inspection_decision_reference"]["compatibility_fields"] == [
        "InspectionPlan.decision_document_hint",
        "CaseApplication.dossier_reference",
        "InspectionOutcome.decision_reference",
    ]
    assert owners["bbkt_reference"]["status"] == "OWNER_NAME_MISMATCH"
    assert owners["bbkt_reference"]["legacy_source"] == "db.ktra B. bản"
    assert owners["bbkt_reference"]["invariant"] == "B. bản must not be imported as a reference until semantics are proven"


def test_canonical_contract_records_all_legacy_misrouting_paths():
    paths = _load_contract()["legacy_misrouting_paths"]
    assert [
        (path["legacy_source"], path["current_target_model"], path["current_target_field"])
        for path in paths
    ] == [
        ("db.ktra Q. định", "CaseApplication", "dossier_reference"),
        ("db.ktra Q. định", "InspectionOutcome", "decision_reference"),
        ("db.ktra B. bản", "InspectionOutcome", "bbkt_reference"),
        ("db.ktra B. bản", "InspectionOutcome", "inspected_on"),
    ]
    date_path = paths[3]
    assert date_path["transform"] == (
        "historical import: parse_date(bbkt_reference) or parse_date(inspected_at); "
        "current import: parse_legacy_inspection_period(inspected_at)"
    )
    assert date_path["precedence"] == (
        "historical B. bản-first path is preserved only as provenance evidence; "
        "current importer exclusively uses Ngày K.tra"
    )
    assert date_path["future_policy"] == "never use B. bản as actual inspection date; use proven Ngày K.tra mapping"


def test_actual_inspection_owner_is_distinct_from_imported_value_provenance():
    owner = {item["canonical_fact"]: item for item in _load_contract()["owners"]}["actual_inspection_period"]
    assert owner["status"] == "OWNER_MODEL_EXTENDED"
    assert "MULTI_SEGMENT_MODEL_MIGRATION_REQUIRED" in owner["backfill_strategy_status"]
    assert "no min/max envelope" in owner["invariant"]
    assert _load_contract()["decision"]["backfill"] == "NOT_PERFORMED"
