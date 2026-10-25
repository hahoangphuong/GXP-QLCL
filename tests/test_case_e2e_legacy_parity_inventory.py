"""Parity inventory integrity checks; NOT runtime E2E acceptance tests."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "artifacts/legacy_audit/case_e2e_parity_acceptance_v1.json"


def test_parity_inventory_has_no_fabricated_uat_or_production_claims():
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    steps = data["steps"]
    assert len(steps) >= 10
    assert len({step["id"] for step in steps}) == len(steps)
    assert all(step["uat_state"] == "not_verified" for step in steps)
    assert all(step["production_parity"] is False for step in steps)


def test_each_claim_of_source_coverage_has_existing_files_and_symbols():
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    for item in data["steps"]:
        backend = ROOT / item["backend_path"]
        assert backend.is_file(), item["id"]
        if item["code_state"] == "supported_in_code":
            frontend = ROOT / item["frontend_path"]
            assert frontend.is_file(), item["id"]
            assert item["frontend_symbol"] in frontend.read_text(encoding="utf-8"), item["id"]
        assert item["release_blocker"].strip(), item["id"]


def test_qdkt_and_reports_cannot_be_declared_ready_by_source_inventory():
    steps = {x["id"]: x for x in json.loads(INVENTORY.read_text(encoding="utf-8"))["steps"]}
    assert steps["qdkt_draft"]["code_state"] == "blocked"
    assert steps["qdkt_approved"]["code_state"] == "internal_only"
    assert steps["report_export"]["code_state"] == "placeholder"
    for key in ("qdkt_draft", "qdkt_approved", "report_export"):
        assert steps[key]["production_parity"] is False
