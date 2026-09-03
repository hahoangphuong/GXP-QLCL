from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.evaluation_scope_document_projection import DOCUMENT_SCOPE_BRANCHES
from backend.app.document.evaluation_scope_payload import C5E_SCOPE_FIELD_NAMES, C5E_SCOPE_FAMILIES

OUTPUT = ROOT / "artifacts/legacy_audit/c5e_evaluation_scope_document_payload_integration.json"
SERVICE = ROOT / "backend/app/document/service.py"
ADAPTER = ROOT / "backend/app/document/evaluation_scope_payload.py"
API_SERVICE = ROOT / "backend/app/services/document_api.py"
READ_MODELS = ROOT / "backend/app/read_models.py"
PROJECTION_ARTIFACT = ROOT / "artifacts/legacy_audit/c5e_evaluation_scope_document_projection.json"


def audit() -> dict:
    blockers: list[dict[str, str]] = []
    checks: dict[str, dict[str, object]] = {}

    def check(code: str, passed: bool, evidence: object, message: str) -> None:
        checks[code] = {"status": "PASS" if passed else "BLOCKED", "evidence": evidence}
        if not passed:
            blockers.append({"code": code, "message": message})

    service_text = SERVICE.read_text(encoding="utf-8")
    adapter_text = ADAPTER.read_text(encoding="utf-8")
    api_text = API_SERVICE.read_text(encoding="utf-8")
    read_model_text = READ_MODELS.read_text(encoding="utf-8")
    projection = json.loads(PROJECTION_ARTIFACT.read_text(encoding="utf-8"))

    check(
        "SCALAR_PROJECTION_CONTRACT_READY",
        projection.get("status") == "SCALAR_PROJECTION_CONTRACT_READY" and projection.get("blockers") == [],
        {"status": projection.get("status"), "blockers": projection.get("blockers")},
        "The branch-aware scalar projection contract is not ready.",
    )
    check(
        "SERVICE_ENRICHMENT_ACTIVE",
        "build_document_payload_result" in service_text
        and "assert_no_c5e_scope_field_override" in service_text
        and "enrich_payload_result_with_c5e_scope" in service_text,
        {"path": SERVICE.relative_to(ROOT).as_posix()},
        "Document payload service is not wired through the C.5e enrichment boundary.",
    )
    check(
        "CANONICAL_DB_OWNER_ONLY",
        all(
            needle in adapter_text
            for needle in (
                "CaseEvaluationScope",
                "CaseEvaluationScopeBlock",
                "CaseEvaluationScopeSelection",
                "EvaluationScopeTaxonomyNode",
                'scope.source_classification != "STRUCTURED_VALID"',
                "node_key_by_id.get(selection.taxonomy_node_id)",
            )
        )
        and "CaseEvaluationScopeUnkeyedEntry" not in adapter_text
        and "rendered_prose" not in adapter_text
        and "summary_text" not in adapter_text,
        {
            "historical_prose_oracle": False,
            "workspace_summary_oracle": False,
            "unkeyed_entries_queried": False,
            "taxonomy_key_owner": "taxonomy_node_id -> current taxonomy node key",
        },
        "The payload adapter is not isolated to canonical structured scope/taxonomy ownership.",
    )
    check(
        "CALLER_SCOPE_OVERRIDE_BLOCKED",
        "cannot be supplied" in adapter_text
        and C5E_SCOPE_FIELD_NAMES
        == frozenset({"Daychuyen", "DayChuyen", "Daychuyen2", "GhPviDG", "GhPviCN", "GioiHanPvi", "GioihanPvi"}),
        {"reserved_fields": sorted(C5E_SCOPE_FIELD_NAMES)},
        "Caller-provided scope bookmark values can override the semantic owner.",
    )
    check(
        "GENERIC_REGISTRY_NOT_SCOPE_OWNER",
        "missing_registry_fields" in adapter_text
        and "field_name not in C5E_SCOPE_FIELD_NAMES" in adapter_text
        and "DocumentPayloadField(" in adapter_text,
        {
            "generic_registry_role": "non-scope inventory/validation",
            "scope_fields_appended_after_generic_validation": True,
        },
        "Generic payload registry still behaves as the semantic owner for C.5e scope fields.",
    )
    check(
        "COPY_PT_BRANCH_EXPLICIT",
        "copy_pt: bool = False" in service_text
        and 'copy_pt=bool(payload.get("copy_pt", False))' in api_text
        and "copy_pt: bool = False" in read_model_text,
        {"family": "INSPECTION_PT_CT", "condition": "CopyPT"},
        "PT.CT CopyPT branch condition is not represented explicitly at the API/service boundary.",
    )
    check(
        "BRANCH_FAMILY_SET_EXACT",
        C5E_SCOPE_FAMILIES == frozenset(DOCUMENT_SCOPE_BRANCHES),
        {"family_count": len(C5E_SCOPE_FAMILIES), "families": sorted(C5E_SCOPE_FAMILIES)},
        "Payload integration family coverage diverged from the branch-aware projection owner.",
    )

    status = "SCALAR_PAYLOAD_INTEGRATION_READY" if not blockers else "BLOCKED"
    return {
        "schema_version": "c5e-evaluation-scope-document-payload-integration/v1",
        "status": status,
        "blockers": blockers,
        "checks": checks,
        "semantic_owner": "backend/app/domain/evaluation_scope_document_projection.py",
        "integration_owner": "backend/app/document/evaluation_scope_payload.py",
        "generic_registry_scope_semantic_owner": False,
        "caller_scope_override_authorized": False,
        "historical_prose_oracle_authorized": False,
        "unkeyed_entries_semantic_input_authorized": False,
        "deferred_separate_path": {
            "name": "Input_DC_to_CC certificate detail",
            "status": "NOT_IMPLEMENTED_IN_SCALAR_PAYLOAD_INTEGRATION",
            "compact_summary_substitution_authorized": False,
        },
        "next_safe_slice": "audit and port Input_DC_to_CC certificate-detail structured taxonomy/bookmark path separately",
    }


def main() -> int:
    report = audit()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STATUS={report['status']}")
    print(f"BLOCKERS={len(report['blockers'])}")
    print(f"OUTPUT={OUTPUT}")
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
