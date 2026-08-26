from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PHASE5_DIR = ROOT / "artifacts" / "phase5"
AUDIT_PATH = PHASE5_DIR / "template_compatibility_audit.json"
RECON_PATH = PHASE5_DIR / "template_contract_reconciled.json"
DDKD_VARIANTS_PATH = PHASE5_DIR / "ddkd_template_variants.json"
BBTD_VARIANTS_PATH = PHASE5_DIR / "bbtd_template_variants.json"
DDKD_APPENDIX_PATH = PHASE5_DIR / "ddkd_appendix_field_adjudication.json"
JSON_OUT = PHASE5_DIR / "phase5_final_closeout.json"
MD_OUT = PHASE5_DIR / "phase5_final_closeout.md"


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _write_utf8(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload_bytes = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Could not read required artifact: {_display_path(path)}: {exc}") from exc
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON: {_display_path(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object: {_display_path(path)}")
    return payload, sha256(payload_bytes).hexdigest()


def build_summary() -> dict[str, Any]:
    audit, audit_sha256 = load_json(AUDIT_PATH)
    reconciled, reconciled_sha256 = load_json(RECON_PATH)
    ddkd_variants, ddkd_variants_sha256 = load_json(DDKD_VARIANTS_PATH)
    bbtd_variants, bbtd_variants_sha256 = load_json(BBTD_VARIANTS_PATH)
    appendix, appendix_sha256 = load_json(DDKD_APPENDIX_PATH)

    errors: list[str] = []

    registry_family_count = int(audit.get("registry_family_count", 0))
    matched_family_count = int(audit.get("matched_family_count", 0))
    active_template_file_count = int(audit.get("active_file_count", 0))
    family_codes = [item["family_code"] for item in reconciled.get("families", [])]

    if registry_family_count <= 0:
        errors.append("Phase 5 template audit must report a positive registry_family_count.")
    if matched_family_count != registry_family_count:
        errors.append("Phase 5 template audit matched_family_count must equal registry_family_count.")
    if active_template_file_count <= 0:
        errors.append("Phase 5 template audit must report a positive active_template_file_count.")
    if ddkd_variants.get("family_code") != "DDKD_CERTIFICATE":
        errors.append("DDKD variant contract must declare family_code DDKD_CERTIFICATE.")
    if not ddkd_variants.get("variants"):
        errors.append("DDKD variant contract must contain at least one variant.")
    if bbtd_variants.get("family_code") != "INSPECTION_BBTD_HOSO_DK":
        errors.append("BBTD variant contract must declare family_code INSPECTION_BBTD_HOSO_DK.")
    if not bbtd_variants.get("variants"):
        errors.append("BBTD variant contract must contain at least one variant.")
    if appendix.get("family_code") != "DDKD_APPENDIX_OR_DECISION":
        errors.append("DDKD appendix adjudication must declare family_code DDKD_APPENDIX_OR_DECISION.")

    contract_exact_scalar = [
        "INSPECTION_CAPA_LAN_1",
        "INSPECTION_CAPA_LAN_2",
    ]
    contract_variant_exact = [
        "DDKD_CERTIFICATE",
        "INSPECTION_BBTD_HOSO_DK",
    ]
    selection_safe = ["DDKD_APPENDIX_OR_DECISION"]
    promoted = set(contract_exact_scalar) | set(contract_variant_exact) | set(selection_safe)
    payload_passthrough_remaining = sorted(code for code in family_codes if code not in promoted)

    blocked_fields = appendix.get("recommended_next_state", {}).get("still_blocked", [])
    promotable_now = appendix.get("recommended_next_state", {}).get("promotable_now", [])

    phase5_status = "closed" if not errors else "invalid"

    return {
        "generated_on": "2026-08-26",
        "phase5_status": phase5_status,
        "artifact_sources": {
            "template_compatibility_audit": {
                "path": _display_path(AUDIT_PATH),
                "sha256": audit_sha256,
            },
            "template_contract_reconciled": {
                "path": _display_path(RECON_PATH),
                "sha256": reconciled_sha256,
            },
            "ddkd_template_variants": {
                "path": _display_path(DDKD_VARIANTS_PATH),
                "sha256": ddkd_variants_sha256,
            },
            "bbtd_template_variants": {
                "path": _display_path(BBTD_VARIANTS_PATH),
                "sha256": bbtd_variants_sha256,
            },
            "ddkd_appendix_field_adjudication": {
                "path": _display_path(DDKD_APPENDIX_PATH),
                "sha256": appendix_sha256,
            },
        },
        "document_generation_baseline": {
            "registry_family_count": registry_family_count,
            "matched_family_count": matched_family_count,
            "active_template_file_count": active_template_file_count,
            "powerpoint_branch_in_scope": False,
        },
        "runtime_contract_status": {
            "contract_exact_scalar_families": contract_exact_scalar,
            "contract_variant_exact_families": contract_variant_exact,
            "selection_safe_families": selection_safe,
            "payload_passthrough_family_count": len(payload_passthrough_remaining),
            "payload_passthrough_families": payload_passthrough_remaining,
        },
        "variant_contracts": {
            "ddkd_variant_keys": [item["variant_key"] for item in ddkd_variants.get("variants", [])],
            "bbtd_variant_keys": [item["variant_key"] for item in bbtd_variants.get("variants", [])],
        },
        "ddkd_appendix_decision_status": {
            "promotable_now": promotable_now,
            "blocked_fields": blocked_fields,
        },
        "validation_errors": errors,
        "remaining_follow_on": [
            "Real Explorer + Word + direct-save validation on private network in Phase 6",
            "Family-by-family promotion from payload_passthrough to explicit runtime contract",
            "Copy-forward parity for families that transplant prior bookmark/table content",
            "Explicit policy for tolerated missing-bookmark writes, if any are approved",
            "Excel-backed support-document branch adjudication outside the current Word render-safe baseline",
        ],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    baseline = summary["document_generation_baseline"]
    runtime = summary["runtime_contract_status"]
    appendix = summary["ddkd_appendix_decision_status"]
    variants = summary["variant_contracts"]
    lines = [
        "# Phase 5 Final Closeout",
        "",
        "Generated by `tools/build_phase5_final_closeout.py`.",
        "",
        "## Status",
        "",
        f"- Phase 5 status: `{summary['phase5_status']}`",
        f"- Registry families: `{baseline['registry_family_count']}`",
        f"- Matched active families: `{baseline['matched_family_count']}`",
        f"- Active template files audited: `{baseline['active_template_file_count']}`",
        f"- PowerPoint branch in scope: `{baseline['powerpoint_branch_in_scope']}`",
        "",
        "## Provenance",
        "",
    ]
    for source_name, source in summary["artifact_sources"].items():
        lines.append(f"- `{source_name}`: `{source['path']}` sha256=`{source['sha256']}`")
    lines.extend(
        [
            "",
            "## Runtime Contract Status",
            "",
            "- `contract_exact` scalar families: "
            + ", ".join(f"`{item}`" for item in runtime["contract_exact_scalar_families"]),
            "- `contract_variant_exact` families: "
            + ", ".join(f"`{item}`" for item in runtime["contract_variant_exact_families"]),
            "- selection-safe families: "
            + ", ".join(f"`{item}`" for item in runtime["selection_safe_families"]),
            f"- payload-passthrough families remaining: `{runtime['payload_passthrough_family_count']}`",
            "",
            "## Variant Contracts",
            "",
            "- DDKD variants: " + ", ".join(f"`{item}`" for item in variants["ddkd_variant_keys"]),
            "- BBTD variants: " + ", ".join(f"`{item}`" for item in variants["bbtd_variant_keys"]),
            "",
            "## DDKD Appendix/Decision",
            "",
            "- promotable now: " + ", ".join(f"`{item}`" for item in appendix["promotable_now"]),
            "- still blocked: " + ", ".join(f"`{item}`" for item in appendix["blocked_fields"]),
            "",
            "## Validation Errors",
            "",
        ]
    )
    if not summary["validation_errors"]:
        lines.append("- none")
    else:
        for item in summary["validation_errors"]:
            lines.append(f"- {item}")
    lines.extend(["", "## Follow-on", ""])
    for item in summary["remaining_follow_on"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        summary = build_summary()
        _write_utf8(JSON_OUT, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        _write_utf8(MD_OUT, render_markdown(summary))
        print(f"Wrote {JSON_OUT}")
        print(f"Wrote {MD_OUT}")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
