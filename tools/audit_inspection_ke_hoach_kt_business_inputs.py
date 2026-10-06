from __future__ import annotations

"""Owner-level audit for the INSPECTION_KE_HOACH_KT business input contract.

The source trace proves what legacy VBA branch i=3 reads/writes. This module
maps those source endpoints to existing canonical owners only where the
repository already has an explicit owner contract. Rendering/formatting
semantics stay separate and fail closed until their own contracts exist.
"""

from copy import deepcopy
from typing import Any

FAMILY_CODE = "INSPECTION_KE_HOACH_KT"

# These mappings are supported by the current canonical schema/import/runtime
# ownership. Do not add a field here merely because a similarly named value
# exists somewhere else.
PROVEN_BUSINESS_OWNERS: dict[str, dict[str, str]] = {
    "Tencoso": {"owner": "Site.site_name", "source": "GetTT_CsCty.TenCtydd"},
    "Diadiem": {"owner": "Site.province_name", "source": "GetTT_CsCty.Tinhthanh"},
    "Diachicoso": {"owner": "Site.site_address", "source": "GetTT_CsCty.DiachiDD"},
    "HsDK": {"owner": "CaseApplication.dossier_code", "source": "GetTT_Ktra.s_MaHsDk"},
    "NgaynopHsDK": {"owner": "CaseApplication.submitted_on", "source": "GetTT_Ktra.s_NgaynopHsDk"},
    "QDKT": {"owner": "InspectionPlan.decision_reference", "source": "GetTT_Ktra.QDKT"},
    "NgayQDKT": {"owner": "InspectionPlan.decision_date", "source": "GetTT_Ktra.NgayQDKT"},
    "TieuchuanKT": {"owner": "Case.applicable_standard", "source": "GetTT_Ktra.s_LoaiKT"},
    "Daychuyen": {"owner": "CaseEvaluationScope projection: DC_cu", "source": "Get_DCx.DC_cu"},
    "GioiHanPvi": {"owner": "CaseEvaluationScope projection: GHanDC", "source": "Get_DCx.GHanDC"},
}

# A rendering contract belongs here only after both source semantics and the
# modern owner/structural implementation have been proven.
PROVEN_RENDERING_CONTRACTS: dict[str, dict[str, str]] = {
    "scope_section_suppression": {
        "owner": "backend.app.document.inspection_ke_hoach_kt_scope_suppression",
        "reason": (
            "legacy InStr(..., vbTextCompare) decisions are projected from Daychuyen; "
            "effective template contracts own physical targets and "
            "docx_bookmark_range owns structural deletion"
        ),
    },
    "TTx/TT3x/TT3Del": {
        "owner": "backend.app.document.inspection_ke_hoach_kt_team_projection",
        "reason": (
            "canonical InspectionTeamMember sort_order plus InspectorProfile.roster_group "
            "reconstruct the legacy core TTviên list and its exact TT_ext/CRLF tail semantics"
        ),
    },
    "TT_VKNx/TT_SYTx": {
        "owner": "backend.app.document.inspection_ke_hoach_kt_team_projection",
        "reason": (
            "source-proven roster groups partition the three central-institute named ranges "
            "from the provincial-health named range without parsing display text"
        ),
    },
    "Diadiemx": {
        "owner": "backend.app.document.inspection_ke_hoach_kt_province_projection",
        "reason": (
            "source-backed Dia_danh_x reference preserves the exact 63-row province order, "
            "display-prefix column, historical TP rewrite, and LCase_FirstChar behavior"
        ),
    },
    "VKNx": {
        "owner": "backend.app.document.inspection_ke_hoach_kt_province_projection",
        "reason": (
            "Daychuyen is the source-proven DC_cu value and the province reference preserves "
            "the exact Get_VKN index-32 boundary; unknown provinces fail closed"
        ),
    },
    "Fulldate": {
        "owner": "backend.app.document.inspection_ke_hoach_kt_generation_date",
        "reason": (
            "legacy writes FormatDateS(Date, 1); the modern business-calendar policy is "
            "explicitly Asia/Ho_Chi_Minh and rejects timezone-naive generation timestamps"
        ),
    },
}

# These are not missing database columns. They require a renderer/projection
# contract before contextual create may be enabled.
RENDERING_BLOCKERS: dict[str, dict[str, str]] = {}


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a mapping")
    return value


def build_business_input_audit(source_audit: dict[str, Any]) -> dict[str, Any]:
    if source_audit.get("status") != "SOURCE_INSPECTION_KE_HOACH_KT_I3_CAPTURED":
        raise RuntimeError("unexpected KHKT source-audit status")
    if source_audit.get("target_i") != 3:
        raise RuntimeError("KHKT source audit must target legacy branch i=3")

    required_writes = _require_mapping(source_audit.get("required_writes"), "required_writes")
    required_suppressions = _require_mapping(
        source_audit.get("required_section_suppressions", source_audit.get("required_section_deletes")),
        "required_section_suppressions",
    )
    for name in ("Daychuyen", "GioiHanPvi", "Diachicoso", "TieuchuanKT", "Fulldate"):
        if name not in required_writes:
            raise RuntimeError(f"source audit is missing required KHKT write: {name}")
    expected_suppressions = {
        "PVCepha", "PVPeni", "PVDuoclieu", "PVTiem", "PVNhomat", "PVNangmem", "PVSuibot"
    }
    if set(required_suppressions) != expected_suppressions:
        raise RuntimeError("source audit KHKT section-suppression set changed")

    fields = {
        name: {
            "classification": "OWNER_PROVEN",
            **deepcopy(spec),
        }
        for name, spec in PROVEN_BUSINESS_OWNERS.items()
    }
    rendering_contracts = {
        name: {
            "classification": "RENDERING_CONTRACT_PROVEN",
            **deepcopy(spec),
        }
        for name, spec in PROVEN_RENDERING_CONTRACTS.items()
    }
    blockers = {
        name: {
            "classification": "RENDERING_CONTRACT_MISSING",
            **deepcopy(spec),
        }
        for name, spec in RENDERING_BLOCKERS.items()
    }
    return {
        "schema_version": "inspection-ke-hoach-kt-business-input-audit/v2",
        "family_code": FAMILY_CODE,
        "status": (
            "BUSINESS_INPUT_OWNERS_AND_RENDERING_CONTRACTS_PROVEN"
            if not blockers
            else "BUSINESS_INPUT_OWNERS_PROVEN_RENDERING_BLOCKED"
        ),
        "business_input_fields": fields,
        "rendering_contracts": rendering_contracts,
        "rendering_blockers": blockers,
        "summary": {
            "owner_proven": len(fields),
            "rendering_contract_proven": len(rendering_contracts),
            "rendering_contract_missing": len(blockers),
            "schema_migration_required": False,
            "contextual_create_readiness": "BUSINESS_INPUT_CONTRACT_MISSING",
        },
        "invariants": {
            "source_audit_modified": False,
            "runtime_readiness_changed": False,
            "frontend_business_logic_added": False,
            "schema_changed": False,
        },
    }
