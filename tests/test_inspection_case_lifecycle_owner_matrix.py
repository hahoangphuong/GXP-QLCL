from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "artifacts" / "legacy_audit" / "inspection_case_lifecycle_owner_matrix.json"
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
