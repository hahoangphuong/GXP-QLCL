from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVENANCE = ROOT / "artifacts" / "legacy_audit" / "inspection_qd_kt_input_provenance.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "legacy_audit" / "inspection_qd_kt_business_semantics.json"
EXPECTED_SOURCE_SHA256 = "6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7"

# Business-semantic evidence supplied by the product owner/user. This is kept
# separate from source-derived VBA provenance so the two evidence classes are
# never conflated.
BUSINESS_SEMANTIC_OVERLAY = {
    "QDKT": {
        "evidence_kind": "USER_CONFIRMED_BUSINESS_SEMANTICS",
        "business_input_owner": "user-authored QĐKT composite text input",
        "business_meaning": "QĐKT decision reference/number",
        "composite_input_contains": ["QDKT", "NgayQDKT"],
        "modern_owner_candidate": "InspectionPlan QĐKT decision metadata",
        "raw_preservation_candidate": "InspectionPlan.decision_document_hint",
        "owner_classification": "OWNER_PARTIAL",
        "blocker": (
            "business meaning and shared user-authored composite input are confirmed, "
            "but InspectionPlan has no structured QĐKT decision-reference field yet; "
            "do not reuse InspectionOutcome.decision_reference without lifecycle proof"
        ),
    },
    "NgayQDKT": {
        "evidence_kind": "USER_CONFIRMED_BUSINESS_SEMANTICS",
        "business_input_owner": "user-authored QĐKT composite text input",
        "business_meaning": "QĐKT decision date",
        "composite_input_contains": ["QDKT", "NgayQDKT"],
        "modern_owner_candidate": "InspectionPlan QĐKT decision metadata",
        "raw_preservation_candidate": "InspectionPlan.decision_document_hint",
        "owner_classification": "OWNER_PARTIAL",
        "blocker": (
            "business meaning and shared user-authored composite input are confirmed, "
            "but no structured QĐKT decision-date owner exists on InspectionPlan"
        ),
    },
}


def build_business_semantics(provenance: dict[str, object]) -> dict[str, object]:
    if provenance.get("source_zip_sha256") != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("unexpected legacy source SHA256")
    fields = provenance.get("fields")
    if not isinstance(fields, dict):
        raise RuntimeError("source provenance has no fields mapping")

    resolved_fields = deepcopy(fields)
    for field_name, overlay in BUSINESS_SEMANTIC_OVERLAY.items():
        field = resolved_fields.get(field_name)
        if not isinstance(field, dict):
            raise RuntimeError(f"source provenance missing field: {field_name}")
        # Preserve source-derived facts; add a separately labelled business layer.
        field["business_semantic_evidence"] = deepcopy(overlay)
        field["modern_owner_candidate"] = overlay["modern_owner_candidate"]
        field["owner_classification"] = overlay["owner_classification"]
        field["blocker"] = overlay["blocker"]

    classifications = ("OWNER_PROVEN", "OWNER_PARTIAL", "OWNER_BLOCKED")
    counts = {
        key: sum(
            1
            for value in resolved_fields.values()
            if isinstance(value, dict) and value.get("owner_classification") == key
        )
        for key in classifications
    }

    return {
        "schema_version": "inspection-qd-kt-business-semantics/v1",
        "status": "BUSINESS_SEMANTIC_OVERLAY_PARTIAL",
        "source_provenance_schema_version": provenance.get("schema_version"),
        "source_zip_sha256": provenance.get("source_zip_sha256"),
        "source_provenance_preserved": True,
        "business_semantic_evidence_is_source_provenance": False,
        "fields": resolved_fields,
        "classification_counts": counts,
        "decision": {
            "typed_qd_kt_input_contract": "BUSINESS_INPUT_CONTRACT_MISSING",
            "reason": (
                "QDKT/NgayQDKT business semantics are now partially closed, but "
                "structured planning-phase decision reference/date ownership and other "
                "active inputs remain unresolved"
            ),
            "schema_change_authorized": False,
        },
        "invariants": {
            "source_provenance_modified": False,
            "runtime_contract_changed": False,
            "models_modified": False,
            "schema_modified": False,
            "inspection_outcome_reused_as_qdkt_owner": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Overlay confirmed business semantics onto source-derived INSPECTION_QD_KT provenance."
    )
    parser.add_argument("--provenance", type=Path, default=DEFAULT_PROVENANCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
        report = build_business_semantics(provenance)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print("STATUS=INSPECTION_QD_KT_BUSINESS_SEMANTICS_FAILED")
        print(f"ERROR={exc}")
        return 2

    print(f"STATUS={report['status']}")
    print(f"CLASSIFICATION_COUNTS={json.dumps(report['classification_counts'], sort_keys=True)}")
    print(f"OUTPUT={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
