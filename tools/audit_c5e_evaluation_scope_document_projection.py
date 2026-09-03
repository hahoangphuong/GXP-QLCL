from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.domain.evaluation_scope_document_projection import DOCUMENT_SCOPE_BRANCHES
from tools.audit_c5e_evaluation_scope_document_mapping import EXPECTED

OUTPUT = ROOT / "artifacts" / "legacy_audit" / "c5e_evaluation_scope_document_projection.json"


def main() -> int:
    mismatches: list[dict[str, object]] = []
    for family_code, expected in EXPECTED.items():
        actual = DOCUMENT_SCOPE_BRANCHES.get(family_code)
        if actual is None:
            mismatches.append({"family_code": family_code, "reason": "missing_branch_contract"})
            continue
        expected_fields = set(expected.get("active", {}))
        actual_fields = set(actual.get("fields", {}))
        if expected_fields != actual_fields:
            mismatches.append({
                "family_code": family_code,
                "reason": "active_field_set_mismatch",
                "expected": sorted(expected_fields),
                "actual": sorted(actual_fields),
            })
        if str(expected["branch"]) != str(actual.get("branch")):
            mismatches.append({"family_code": family_code, "reason": "branch_mismatch", "expected": expected["branch"], "actual": actual.get("branch")})
        if set(expected.get("commented_only", {})) != set(actual.get("commented_only", {})):
            mismatches.append({"family_code": family_code, "reason": "commented_only_mismatch"})

    blockers = []
    if mismatches:
        blockers.append({
            "code": "BRANCH_CONTRACT_MISMATCH",
            "message": "The branch-aware scalar projection contract does not match the source-derived C.5e audit.",
            "evidence": mismatches,
        })

    payload = {
        "schema_version": "c5e-evaluation-scope-document-projection/v1",
        "status": "SCALAR_PROJECTION_CONTRACT_READY" if not blockers else "BLOCKED_FOR_SCALAR_PROJECTION_CONTRACT",
        "semantic_owner": "backend/app/domain/evaluation_scope_document_projection.py",
        "source_evidence": "active RecordForm.frm branches captured by c5e_evaluation_scope_document_mapping audit",
        "compact_summary_reuse_authorized": False,
        "historical_prose_oracle_authorized": False,
        "unkeyed_entries_semantic_input_authorized": False,
        "branch_contract_count": len(DOCUMENT_SCOPE_BRANCHES),
        "branch_contract_mismatches": mismatches,
        "blockers": blockers,
        "deferred_separate_path": {
            "name": "Input_DC_to_CC certificate detail",
            "status": "NOT_IMPLEMENTED_IN_SCALAR_CONTRACT",
            "compact_summary_substitution_authorized": False,
        },
        "next_safe_slice": "integrate scalar projection into document payload resolution per family while keeping Input_DC_to_CC certificate detail separate",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STATUS={payload['status']}")
    print(f"BLOCKERS={len(blockers)}")
    print(f"OUTPUT={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
