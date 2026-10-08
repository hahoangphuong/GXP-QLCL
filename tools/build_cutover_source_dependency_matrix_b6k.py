from __future__ import annotations
import json
from pathlib import Path
MATRIX = {
  "legacy_snapshot_v2": {
    "owner_files": [
      "backend/app/domain/legacy_snapshot_v2.py",
      "tools/export_legacy_snapshot_v2.py"
    ],
    "binding_fields": [
      "workbook.sha256"
    ],
    "hardcoded_constants": [
      "AUTHORITATIVE_WORKBOOK_SHA256"
    ],
    "current_known_sha_values": [
      "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d"
    ],
    "classification": "HARD_BOUND_CURRENT_SNAPSHOT",
    "cutover_action": "explicit expected SHA",
    "reason": "default historical guard"
  },
  "B6A": {
    "owner_files": [
      "tools/discover_legacy_coverage_b6a.py"
    ],
    "binding_fields": [
      "snapshot_sha256"
    ],
    "hardcoded_constants": [
      "SNAPSHOT_SHA256"
    ],
    "current_known_sha_values": [],
    "classification": "HARD_BOUND_CURRENT_SNAPSHOT",
    "cutover_action": "review and rebind",
    "reason": "source constant guards historical snapshot"
  },
  "B6B": {
    "owner_files": [
      "backend/app/domain/legacy_db_ktra_repeatable_v2.py"
    ],
    "binding_fields": [
      "CANONICAL_SNAPSHOT_SHA256"
    ],
    "hardcoded_constants": [
      "CANONICAL_SNAPSHOT_SHA256"
    ],
    "current_known_sha_values": [],
    "classification": "HARD_BOUND_CURRENT_SNAPSHOT",
    "cutover_action": "review and rebind",
    "reason": "canonical snapshot provenance guard"
  },
  "B6C": {
    "owner_files": [
      "backend/app/domain/legacy_certificate_linkage.py"
    ],
    "binding_fields": [
      "snapshot_sha256"
    ],
    "hardcoded_constants": [],
    "current_known_sha_values": [],
    "classification": "REVIEWED_SOURCE_BOUND",
    "cutover_action": "review",
    "reason": "reviewed linkage evidence"
  },
  "B6H": {
    "owner_files": [
      "backend/app/domain/production_line_population.py"
    ],
    "binding_fields": [
      "snapshot_sha256"
    ],
    "hardcoded_constants": [],
    "current_known_sha_values": [],
    "classification": "DATABASE_STATE_BOUND",
    "cutover_action": "replan",
    "reason": "canonical state dependent"
  },
  "B6I": {
    "owner_files": [
      "backend/app/domain/production_line_review_workspace.py"
    ],
    "binding_fields": [
      "candidate_set_sha256"
    ],
    "hardcoded_constants": [],
    "current_known_sha_values": [],
    "classification": "REVIEWED_SOURCE_BOUND",
    "cutover_action": "rebuild roster and obtain explicit review decisions where required; roster identity alone is not physical identity approval",
    "reason": "review roster"
  },
  "B6J": {
    "owner_files": [
      "backend/app/domain/production_line_population_b6j.py",
      "backend/app/domain/production_line_population_writer_b6j.py",
      "tools/plan_production_line_population_b6j.py",
      "tools/apply_production_line_population_b6j.py"
    ],
    "binding_fields": [
      "legacy_snapshot_sha256",
      "canonical_state_sha256",
      "candidate_set_sha256",
      "candidate_set_roster_sha256",
      "candidate_set_roster_content_sha256",
      "candidate_set_roster_item_count",
      "source_alembic_revision",
      "source_database_identity",
      "plan_sha256"
    ],
    "hardcoded_constants": [],
    "current_known_sha_values": [],
    "classification": "DATABASE_STATE_BOUND",
    "cutover_action": "re-export canonical state; rebuild review roster; replan and independently record approved plan and file SHA before any explicitly authorized use",
    "reason": "plan bound to exact legacy source, canonical database state, roster, schema revision and independent external approval digests",
    "external_approval_fields": [
      "expected_plan_sha256",
      "expected_plan_file_sha256"
    ]
  },
  "canonical_state_exporter": {
    "owner_files": [
      "backend/app/domain/production_line_canonical_state.py"
    ],
    "binding_fields": [
      "semantic_sha256"
    ],
    "hardcoded_constants": [],
    "current_known_sha_values": [],
    "classification": "DATABASE_STATE_BOUND",
    "cutover_action": "re-export",
    "reason": "database snapshot"
  },
  "phase3_reviewed_artifacts": {
    "owner_files": [
      "artifacts/phase3c/legacy_snapshot.json"
    ],
    "binding_fields": [
      "snapshot_sha256"
    ],
    "hardcoded_constants": [],
    "current_known_sha_values": [],
    "classification": "REVIEWED_SOURCE_BOUND",
    "cutover_action": "reproduce",
    "reason": "reviewed source artifact"
  },
  "B6K_review_alignment": {
    "owner_files": [
      "backend/app/domain/production_line_cutover_readiness_b6k.py",
      "tools/audit_production_line_cutover_readiness_b6k.py"
    ],
    "binding_fields": [
      "legacy_snapshot_sha256",
      "canonical_state_sha256",
      "candidate_set_sha256",
      "candidate_key",
      "source_case_ids",
      "source_certificate_ids",
      "review_decision",
      "review_status",
      "reviewer",
      "reviewed_at",
      "review_reason",
      "plan_sha256"
    ],
    "external_approval_fields": [
      "expected_plan_file_sha256",
      "expected_reviewed_roster_file_sha256"
    ],
    "hardcoded_constants": [],
    "current_known_sha_values": [],
    "classification": "REVIEWED_SOURCE_BOUND",
    "cutover_action": "Run read-only alignment audit against independently pinned plan and reviewed roster; resolve all blockers and obtain separate write authorization",
    "reason": "B6J binds review candidate universe but does not enforce B6I human decisions while writing"
  }
}
if __name__=="__main__": print(json.dumps(MATRIX,ensure_ascii=False,sort_keys=True,indent=2))
