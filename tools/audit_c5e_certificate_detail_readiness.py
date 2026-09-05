from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_certificate_detail_readiness.json"

FUNCTION_MAP = ROOT / "docs" / "VBA_FUNCTION_MAP.md"
TEMPLATE_REGISTRY = ROOT / "artifacts" / "phase5" / "template_registry.curated.json"
DOCX_RENDERER = ROOT / "backend" / "app" / "document" / "docx_template_render.py"
CERTIFICATE_RUNTIME = ROOT / "backend" / "app" / "document" / "c5e_certificate_detail_runtime.py"
CERTIFICATE_PROJECTION = ROOT / "backend" / "app" / "document" / "c5e_certificate_detail_semantic_projection.py"
SCALAR_PROJECTION = ROOT / "backend" / "app" / "domain" / "evaluation_scope_document_projection.py"
SCALAR_INTEGRATION = ROOT / "backend" / "app" / "document" / "evaluation_scope_payload.py"

CERT_FAMILY = "CERTIFICATE_ISSUANCE_WORD"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def audit() -> dict[str, object]:
    blockers: list[dict[str, object]] = []
    checks: list[dict[str, object]] = []

    function_map_text = _read(FUNCTION_MAP) if FUNCTION_MAP.is_file() else ""
    function_map_has_commented_variant = (
        "`Input_DC_to_CC2`" in function_map_text
        and "commented legacy variant" in function_map_text
    )
    exact_active_body_retained = (
        "Sub Input_DC_to_CC(" in function_map_text
        or "Function Input_DC_to_CC(" in function_map_text
    )
    checks.append(
        {
            "code": "DURABLE_VBA_EVIDENCE",
            "pass": function_map_has_commented_variant and exact_active_body_retained,
            "evidence": {
                "function_map": "docs/VBA_FUNCTION_MAP.md",
                "commented_variant_recorded": function_map_has_commented_variant,
                "exact_active_Input_DC_to_CC_body_retained": exact_active_body_retained,
            },
        }
    )
    if not exact_active_body_retained:
        blockers.append(
            {
                "code": "ACTIVE_INPUT_DC_TO_CC_BODY_NOT_DURABLY_CAPTURED",
                "message": (
                    "The repository does not retain the exact active Input_DC_to_CC VBA body. "
                    "Do not reconstruct certificate-detail row semantics from procedure names, "
                    "compact summary behavior, or the commented Input_DC_to_CC2 variant."
                ),
                "evidence": "docs/VBA_FUNCTION_MAP.md records Input_DC_to_CC2 as a commented legacy variant only.",
            }
        )

    registry_payload = json.loads(_read(TEMPLATE_REGISTRY))
    cert_entries = [
        item for item in registry_payload.get("entries", [])
        if item.get("family_code") == CERT_FAMILY
    ]
    cert_entry = cert_entries[0] if len(cert_entries) == 1 else None
    cert_bookmarks = [] if cert_entry is None else list(cert_entry.get("bookmarks") or [])
    known_general_bookmarks = {
        "Chuthich", "ChuthichE", "DiachiCoso", "DiachiCosoE",
        "DiachiVPCty", "DiachiVPCtyE", "NgayKT1", "NgayKT2",
        "NoEU_Del", "NoPICS_Del", "NoWHO_Del", "OECD_Del",
        "TenCoso", "TenCosoE", "TenCty", "TenCtyE", "WHO_Del",
    }
    detail_bookmarks = sorted(set(cert_bookmarks) - known_general_bookmarks)
    registry_detail_ready = len(cert_entries) == 1 and bool(detail_bookmarks)
    checks.append(
        {
            "code": "CERTIFICATE_DETAIL_TEMPLATE_CONTRACT",
            "pass": registry_detail_ready,
            "evidence": {
                "family_code": CERT_FAMILY,
                "entry_count": len(cert_entries),
                "registered_bookmarks": cert_bookmarks,
                "candidate_detail_bookmarks_beyond_general_fields": detail_bookmarks,
            },
        }
    )
    if not registry_detail_ready:
        blockers.append(
            {
                "code": "CERTIFICATE_DETAIL_TEMPLATE_REGIONS_NOT_PROVEN",
                "message": (
                    "The curated CERTIFICATE_ISSUANCE_WORD template contract contains only the "
                    "known general-information bookmarks; no taxonomy-detail row/region contract "
                    "is durably proven for Input_DC_to_CC."
                ),
                "evidence": "artifacts/phase5/template_registry.curated.json",
            }
        )

    renderer_text = _read(DOCX_RENDERER)
    runtime_text = _read(CERTIFICATE_RUNTIME) if CERTIFICATE_RUNTIME.is_file() else ""
    projection_text = _read(CERTIFICATE_PROJECTION) if CERTIFICATE_PROJECTION.is_file() else ""
    has_generic_table_region = all(
        token in renderer_text
        for token in (
            "def _apply_table_regions(",
            "region_bookmark_name",
            "_find_table_row_with_region_bookmark",
            "deepcopy(template_row)",
        )
    )
    has_dedicated_runtime_owner = (
        "def build_certificate_detail_runtime_docx(" in runtime_text
        and "project_certificate_detail_semantic_operations" in projection_text
        and "build_certificate_detail_runtime_docx" in renderer_text
    )
    checks.append(
        {
            "code": "DOCX_RENDERER_CAPABILITY_BOUNDARY",
            "pass": has_generic_table_region and has_dedicated_runtime_owner,
            "evidence": {
                "generic_table_region_clone_supported": has_generic_table_region,
                "dedicated_certificate_detail_runtime_owner_present": has_dedicated_runtime_owner,
                "renderer": "backend/app/document/docx_template_render.py",
                "runtime_owner": "backend/app/document/c5e_certificate_detail_runtime.py",
                "semantic_owner": "backend/app/document/c5e_certificate_detail_semantic_projection.py",
            },
        }
    )
    if not has_dedicated_runtime_owner:
        blockers.append(
            {
                "code": "INPUT_DC_TO_CC_RENDER_CONTRACT_NOT_IMPLEMENTED",
                "message": (
                    "No dedicated Input_DC_to_CC certificate-detail runtime/semantic owner is wired "
                    "into template rendering. Generic table cloning must not be treated as equivalent."
                ),
                "evidence": [
                    "backend/app/document/c5e_certificate_detail_runtime.py",
                    "backend/app/document/c5e_certificate_detail_semantic_projection.py",
                    "backend/app/document/docx_template_render.py",
                ],
            }
        )

    scalar_text = _read(SCALAR_PROJECTION) if SCALAR_PROJECTION.is_file() else ""
    integration_text = _read(SCALAR_INTEGRATION) if SCALAR_INTEGRATION.is_file() else ""
    scalar_does_not_claim_detail = all(
        token not in scalar_text and token not in integration_text
        for token in (
            "project_certificate_detail_semantic_operations",
            "build_certificate_detail_runtime_docx",
            "CERTIFICATE_DETAIL_DESTINATION_BOOKMARK",
        )
    )
    checks.append(
        {
            "code": "SCALAR_DETAIL_SEPARATION",
            "pass": scalar_does_not_claim_detail,
            "evidence": {
                "scalar_projection_and_payload_do_not_claim_certificate_detail_owner": scalar_does_not_claim_detail,
                "dedicated_owner": "backend/app/document/c5e_certificate_detail_semantic_projection.py",
            },
        }
    )
    if not scalar_does_not_claim_detail:
        blockers.append(
            {
                "code": "SCALAR_DETAIL_BOUNDARY_VIOLATION",
                "message": (
                    "Certificate detail must remain separate from C.5e scalar projection/payload integration."
                ),
                "evidence": [
                    "backend/app/domain/evaluation_scope_document_projection.py",
                    "backend/app/document/evaluation_scope_payload.py",
                ],
            }
        )

    report = {
        "schema_version": "c5e-certificate-detail-readiness/v2",
        "status": (
            "READY_FOR_CERTIFICATE_DETAIL_IMPLEMENTATION"
            if not blockers
            else "BLOCKED_PENDING_EXACT_VBA_AND_TEMPLATE_EVIDENCE"
        ),
        "semantic_target": "active VBA Input_DC_to_CC certificate-detail structured taxonomy/bookmark path",
        "compact_summary_substitution_authorized": False,
        "scalar_projection_substitution_authorized": False,
        "historical_prose_oracle_authorized": False,
        "unkeyed_entries_semantic_input_authorized": False,
        "commented_Input_DC_to_CC2_as_active_oracle_authorized": False,
        "checks": checks,
        "blockers": blockers,
        "required_evidence_to_unblock": [
            "exact active Input_DC_to_CC VBA procedure body and directly called helpers",
            "exact certificate template row/bookmark structure used by that procedure",
            "row-level mapping from selected taxonomy node/custom description to destination bookmark/row behavior",
            "proof of formatting/copy rules that must survive server-side DOCX rendering",
        ],
        "next_safe_slice": (
            "durably capture the remaining exact legacy/template evidence needed by this historical audit; "
            "do not alter the implemented certificate-detail runtime merely to satisfy stale readiness assumptions"
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = audit()
    print(f"STATUS={report['status']}")
    print(f"BLOCKERS={len(report['blockers'])}")
    print(f"OUTPUT={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
