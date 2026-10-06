from __future__ import annotations

from copy import deepcopy

import pytest

from tools.audit_inspection_ke_hoach_kt_business_inputs import build_business_input_audit


def _source_audit() -> dict[str, object]:
    return {
        "status": "SOURCE_INSPECTION_KE_HOACH_KT_I3_CAPTURED",
        "target_i": 3,
        "required_writes": {
            name: {"effective_write": {"physical_bookmark": name}}
            for name in ("Daychuyen", "GioiHanPvi", "Diachicoso", "TieuchuanKT")
        },
        "required_section_suppressions": {
            name: {"operation_type": "DELETE"}
            for name in ("PVCepha", "PVPeni", "PVDuoclieu", "PVTiem", "PVNhomat", "PVNangmem", "PVSuibot")
        },
    }


def test_khkt_business_input_audit_separates_canonical_owners_from_rendering_semantics():
    source = _source_audit()
    before = deepcopy(source)

    report = build_business_input_audit(source)

    assert source == before
    assert report["schema_version"] == "inspection-ke-hoach-kt-business-input-audit/v2"
    assert report["status"] == "BUSINESS_INPUT_OWNERS_PROVEN_RENDERING_BLOCKED"
    assert report["summary"] == {
        "owner_proven": 10,
        "rendering_contract_proven": 5,
        "rendering_contract_missing": 1,
        "schema_migration_required": False,
        "contextual_create_readiness": "BUSINESS_INPUT_CONTRACT_MISSING",
    }
    owners = report["business_input_fields"]
    assert owners["TieuchuanKT"]["owner"] == "Case.applicable_standard"
    assert owners["HsDK"]["owner"] == "CaseApplication.dossier_code"
    assert owners["NgaynopHsDK"]["owner"] == "CaseApplication.submitted_on"
    assert owners["QDKT"]["owner"] == "InspectionPlan.decision_reference"
    assert owners["NgayQDKT"]["owner"] == "InspectionPlan.decision_date"
    assert owners["Daychuyen"]["owner"].startswith("CaseEvaluationScope projection")
    assert owners["GioiHanPvi"]["owner"].startswith("CaseEvaluationScope projection")

    rendering_contracts = report["rendering_contracts"]
    scope_contract = rendering_contracts["scope_section_suppression"]
    assert scope_contract["classification"] == "RENDERING_CONTRACT_PROVEN"
    assert "inspection_ke_hoach_kt_scope_suppression" in scope_contract["owner"]
    assert rendering_contracts["TTx/TT3x/TT3Del"]["classification"] == "RENDERING_CONTRACT_PROVEN"
    assert rendering_contracts["TT_VKNx/TT_SYTx"]["owner"].endswith(
        "inspection_ke_hoach_kt_team_projection"
    )
    assert rendering_contracts["Diadiemx"]["owner"].endswith(
        "inspection_ke_hoach_kt_province_projection"
    )
    assert rendering_contracts["VKNx"]["classification"] == "RENDERING_CONTRACT_PROVEN"

    blockers = report["rendering_blockers"]
    assert set(blockers) == {"Fulldate"}
    assert "scope_section_suppression" not in blockers
    assert "TTx/TT3x/TT3Del" not in blockers
    assert "TT_VKNx/TT_SYTx" not in blockers
    assert report["invariants"]["runtime_readiness_changed"] is False


def test_khkt_business_input_audit_accepts_legacy_source_audit_delete_key_for_compatibility():
    source = _source_audit()
    source["required_section_deletes"] = source.pop("required_section_suppressions")
    assert build_business_input_audit(source)["summary"]["owner_proven"] == 10


def test_khkt_business_input_audit_fails_closed_when_source_contract_drifts():
    source = _source_audit()
    del source["required_writes"]["TieuchuanKT"]
    with pytest.raises(RuntimeError, match="missing required KHKT write"):
        build_business_input_audit(source)

    source = _source_audit()
    source["required_section_suppressions"].pop("PVTiem")
    with pytest.raises(RuntimeError, match="section-suppression set changed"):
        build_business_input_audit(source)


def test_khkt_business_input_audit_rejects_wrong_source_branch():
    source = _source_audit()
    source["target_i"] = 2
    with pytest.raises(RuntimeError, match="branch i=3"):
        build_business_input_audit(source)
