from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "artifacts" / "phase5" / "payload_builder_registry.json"
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_evaluation_scope_document_mapping.json"

# Source-derived from active RecordForm.frm statements. Commented VBA is intentionally excluded.
EXPECTED = {
    "INSPECTION_BBTD_HOSO_DK": {"branch": "Tao_BBTD", "active": {"Daychuyen": "DaychuyenDD"}},
    "INSPECTION_QD_KT": {"branch": "Tao_QDKT_KHKT_BBKT:i=2", "active": {}},
    "INSPECTION_KE_HOACH_KT": {"branch": "Tao_QDKT_KHKT_BBKT:i=3", "active": {"Daychuyen": "DC_cu", "GioiHanPvi": "IIf(GHanDC blank, 'Không', GHanDC)"}},
    "INSPECTION_BB_KT": {"branch": "Tao_QDKT_KHKT_BBKT:i=4", "active": {"Daychuyen": "DaychuyenLF", "GhPviDG": "assessment-labeled limitation, default 'Không'", "GhPviCN": "GHanDC, default 'Không'"}},
    "INSPECTION_PT_PCT": {"branch": "Tao_PT_PCT_CT:i=7", "active": {"Daychuyen": "RipDot(DaychuyenX)", "Daychuyen2": "DaychuyenLF", "GioihanPvi": "GHanDC"}},
    "INSPECTION_PT_CT": {"branch": "Tao_PT_PCT_CT:i=8", "active": {"Daychuyen": "RipDot(DaychuyenX) when CopyPT=False", "Daychuyen2": "DaychuyenLF when CopyPT=False", "GioihanPvi": "GHanDC when CopyPT=False"}},
    "RISK_MANAGEMENT_WORKSHEET": {"branch": "Tao_BB_QLRR", "active": {"Daychuyen": "DaychuyenDD"}},
    "ASSESSMENT_MINUTES": {"branch": "Tao_BB_Danhgia", "active": {"DayChuyen": "DaychuyenDD", "GioiHanPvi": "assessment-labeled limitation, default 'Không'"}},
    "CERTIFICATE_DECISION": {"branch": "Tao_QD_CapCC", "active": {}, "commented_only": {"Daychuyen": "DaychuyenX"}},
}


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["payload_builders"]
    by_family = {row["family_code"]: {f["field_name"] for f in row["fields"]} for row in registry}
    findings = []
    for family, spec in EXPECTED.items():
        registered = by_family.get(family, set())
        active = set(spec.get("active", {}))
        commented = set(spec.get("commented_only", {}))
        missing_active = sorted(active - registered)
        registry_false_positive = sorted((registered & {"Daychuyen", "DayChuyen", "Daychuyen2", "GhPviDG", "GhPviCN", "GioiHanPvi", "GioihanPvi"}) - active)
        commented_registered = sorted(commented & registered)
        findings.append({
            "family_code": family,
            "vba_branch": spec["branch"],
            "active_scope_bookmark_mapping": spec.get("active", {}),
            "registered_scope_fields": sorted(registered & {"Daychuyen", "DayChuyen", "Daychuyen2", "GhPviDG", "GhPviCN", "GioiHanPvi", "GioihanPvi"}),
            "missing_active_fields": missing_active,
            "registry_false_positive_fields": registry_false_positive,
            "commented_only_registered_fields": commented_registered,
        })

    blockers = []
    if any(x["missing_active_fields"] for x in findings):
        blockers.append({"code": "ACTIVE_VBA_WRITE_MISSING_FROM_REGISTRY", "message": "At least one active scope bookmark write is absent from the generic payload registry."})
    if any(x["registry_false_positive_fields"] for x in findings):
        blockers.append({"code": "BRANCH_FLATTENING_FALSE_POSITIVES", "message": "Procedure-level registry fields overstate family-specific active writes because branch i=2/3/4 semantics are flattened."})
    if any(x["commented_only_registered_fields"] for x in findings):
        blockers.append({"code": "COMMENTED_VBA_COUNTED_AS_ACTIVE", "message": "At least one registry field originates only from commented-out VBA."})
    blockers.append({"code": "CERTIFICATE_DETAIL_PATH_NOT_COMPACT_SUMMARY", "message": "Input_DC_to_CC renders structured taxonomy rows/bookmarks directly; compact summary_text is not an authorized substitute for certificate detail content."})

    payload = {
        "schema_version": "c5e-evaluation-scope-document-mapping-audit/v1",
        "status": "BLOCKED_FOR_PRODUCTION_DOCUMENT_SCOPE_MAPPING" if blockers else "READY_FOR_CONTROLLED_DOCUMENT_SCOPE_MAPPING",
        "semantic_owner": "active legacy VBA RecordForm/DCForm document-generation paths",
        "compact_summary_reuse_authorized": False,
        "findings": findings,
        "blockers": blockers,
        "next_safe_slice": "build branch-aware document-scope projection contract from canonical CaseEvaluationScope without using historical prose or generic summary_text as an oracle",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STATUS={payload['status']}")
    print(f"BLOCKERS={len(blockers)}")
    print(f"OUTPUT={OUTPUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
