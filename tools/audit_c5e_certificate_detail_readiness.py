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
ACTIVE_VBA = ROOT / "tests/fixtures/c5e_certificate_detail/Input_DC_to_CC.active.bas"
KEY_TO_BOOKMARK_VBA = ROOT / "tests/fixtures/c5e_certificate_detail/helpers/Key2Bookmark.bas"
DESTINATION_ASSETS = ROOT / "backend/app/document/c5e_certificate_destination_assets.json"
SOURCE_ASSETS = ROOT / "backend/app/document/c5e_certificate_detail_source_assets.json"
CAPTURED_DESTINATION_STRUCTURE_ROOT = ROOT / "tests/fixtures/c5e_certificate_detail"



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
    active_body = _read(ACTIVE_VBA) if ACTIVE_VBA.is_file() else ""
    bookmark_helper = (
        _read(KEY_TO_BOOKMARK_VBA)
        if KEY_TO_BOOKMARK_VBA.is_file() else ""
    )
    exact_active_body_retained = (
        active_body.lstrip().startswith("Private Function Input_DC_to_CC(")
        and "wdDoc2.Bookmarks(Key2Bookmark(" in active_body
        and "Range.FormattedText" in active_body
        and "Private Function Key2Bookmark(" in bookmark_helper
        and 'Key2Bookmark = "L" & Replace(' in bookmark_helper
    )
    checks.append(
        {
            "code": "DURABLE_VBA_EVIDENCE",
            "pass": function_map_has_commented_variant and exact_active_body_retained,
            "evidence": {
                "function_map": "docs/VBA_FUNCTION_MAP.md",
                "captured_active_body": "tests/fixtures/c5e_certificate_detail/Input_DC_to_CC.active.bas",
                "captured_key2bookmark_helper": "tests/fixtures/c5e_certificate_detail/helpers/Key2Bookmark.bas",
                "commented_variant_recorded": function_map_has_commented_variant,
                "exact_active_Input_DC_to_CC_body_retained": exact_active_body_retained,
                "original_vba_binary_authenticity_verified": False,
            },
        }
    )
    if not exact_active_body_retained:
        blockers.append(
            {
                "code": "ACTIVE_INPUT_DC_TO_CC_BODY_NOT_DURABLY_CAPTURED",
                "message": (
                    "The captured active Input_DC_to_CC body/helper is missing or inconsistent. "
                    "Do not reconstruct from compact summary or commented VBA variants."
                ),
                "evidence": "tests/fixtures/c5e_certificate_detail/Input_DC_to_CC.active.bas",
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

    # The Phase-5 general-information registry is NOT the active owner of Pvi.
    # Dedicated destination assets and their captured bookmark structures are.
    destination_payload = (
        json.loads(_read(DESTINATION_ASSETS)) if DESTINATION_ASSETS.is_file() else {}
    )
    destination_assets = destination_payload.get("assets", [])
    captured_destinations: list[str] = []
    for asset in destination_assets:
        if not isinstance(asset, dict):
            continue
        gxp_type = asset.get("gxp_type")
        filename = asset.get("filename")
        if gxp_type not in {"GMP", "GLP"} or not isinstance(filename, str):
            continue
        structure_path = CAPTURED_DESTINATION_STRUCTURE_ROOT / (
            filename.replace(".dotx", ".structure.json")
        )
        if not structure_path.is_file():
            continue
        structure = json.loads(_read(structure_path))
        pvi_matches = [
            bookmark
            for part in structure.get("parts", [])
            if part.get("part") == "word/document.xml"
            for bookmark in part.get("bookmarks", [])
            if bookmark.get("name") == "Pvi"
        ]
        if (
            structure.get("template_filename") == filename
            and structure.get("template_sha256") == asset.get("checksum_sha256")
            and len(pvi_matches) == 1
        ):
            captured_destinations.append(gxp_type)

    source_payload = (
        json.loads(_read(SOURCE_ASSETS)) if SOURCE_ASSETS.is_file() else {}
    )
    source_pairs = {
        (asset.get("source_variant"), asset.get("gxp_type"))
        for asset in source_payload.get("assets", [])
        if isinstance(asset, dict) and isinstance(asset.get("sha256"), str)
        and len(asset["sha256"]) == 64
    }
    complete_source_asset_contract = (
        source_payload.get("schema_version")
        == "c5e-certificate-detail-source-assets/v1"
        and source_pairs == {
            (variant, gxp)
            for variant in ("certificate_9", "appendix_z3")
            for gxp in ("GMP", "GLP", "GSP")
        }
        and len(source_payload.get("assets", [])) == 6
    )
    registry_detail_ready = (
        len(cert_entries) == 1
        and destination_payload.get("schema_version")
        == "c5e-certificate-destination-assets-v1"
        and {asset.get("gxp_type") for asset in destination_assets} == {"GMP", "GLP"}
        and sorted(captured_destinations) == ["GLP", "GMP"]
        and "GSP" in destination_payload.get("unsupported_gxp_types", {})
        and complete_source_asset_contract
    )
    checks.append(
        {
            "code": "CERTIFICATE_DETAIL_TEMPLATE_CONTRACT",
            "pass": registry_detail_ready,
            "evidence": {
                "family_code": CERT_FAMILY,
                "entry_count": len(cert_entries),
                "registered_general_bookmarks": cert_bookmarks,
                "legacy_curated_registry_detail_bookmarks": detail_bookmarks,
                "dedicated_captured_destinations": sorted(captured_destinations),
                "dedicated_destination_asset_contract": "backend/app/document/c5e_certificate_destination_assets.json",
                "source_asset_registry_complete": complete_source_asset_contract,
                "gsp_destination_supported": False,
                "destination_binary_loaded_from_runtime_storage": False,
            },
        }
    )
    if not registry_detail_ready:
        blockers.append(
            {
                "code": "CERTIFICATE_DETAIL_TEMPLATE_REGIONS_NOT_PROVEN",
                "message": (
                    "Dedicated GMP/GLP destination Pvi geometry or six-source asset registry "
                    "is missing/inconsistent; general-information bookmarks cannot substitute."
                ),
                "evidence": "backend/app/document/c5e_certificate_destination_assets.json",
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
        "schema_version": "c5e-certificate-detail-readiness/v3",
        "status": (
            "SOURCE_CONTRACT_IMPLEMENTED_LIVE_NOT_VERIFIED"
            if not blockers
            else "SOURCE_CONTRACT_EVIDENCE_INCOMPLETE"
        ),
        "runtime_storage_source_assets_verified": False,
        "runtime_storage_destination_assets_verified": False,
        "authenticated_real_case_docx_render_verified": False,
        "gsp_destination_supported": False,
        "deployment_authorized": False,
        "semantic_target": "active VBA Input_DC_to_CC certificate-detail structured taxonomy/bookmark path",
        "compact_summary_substitution_authorized": False,
        "scalar_projection_substitution_authorized": False,
        "historical_prose_oracle_authorized": False,
        "unkeyed_entries_semantic_input_authorized": False,
        "commented_Input_DC_to_CC2_as_active_oracle_authorized": False,
        "checks": checks,
        "blockers": blockers,
        "required_evidence_to_unblock": [
            "checksum-verified source and destination Word binaries in authorized runtime template storage",
            "authenticated real-Case certificate generation and resulting DOCX artifact verification",
            "separately source and hash-verify GSP destination template before enabling GSP",
        ],
        "next_safe_slice": (
            "verify runtime storage and authenticated certificate output only after authorized "
            "environment access; never infer successful rendering from source fixtures or CI"
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
