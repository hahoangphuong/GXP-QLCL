from pathlib import Path
import json

from tools import build_phase7_cutover_readiness as readiness
from tools.validate_phase7_cutover_checklist import validate_rows


def test_cutover_runbook_requires_explicit_identity_provisioning_and_readiness_verification():
    text = (Path(__file__).resolve().parents[1] / "docs" / "PHASE7_CUTOVER_RUNBOOK.md").read_text(encoding="utf-8")

    assert "tools/provision_app_user.py" in text
    assert "tools/verify_rbac_readiness.py" in text
    assert '--require-user "<operator-email>:<role-code>"' in text
    assert text.index("tools/provision_app_user.py") < text.index("tools/verify_rbac_readiness.py")
    assert "@" not in text


def test_validate_rows_accepts_known_statuses():
    errors = validate_rows(
        [
            {"item_id": "desktop_phase6_complete", "status": "pass"},
            {"item_id": "projection_conflicts_resolved", "status": "blocked"},
            *[_operational_item(item_id) for item_id in readiness.FREEZE_ITEM_IDS + readiness.ROLLBACK_ITEM_IDS],
        ]
    )

    assert errors == []


def test_validate_rows_rejects_duplicate_ids_and_unknown_status():
    errors = validate_rows(
        [
            {"item_id": "desktop_phase6_complete", "status": "pass"},
            {"item_id": "desktop_phase6_complete", "status": "mystery"},
        ]
    )

    assert any("duplicate item_id: desktop_phase6_complete" in error for error in errors)
    assert any("desktop_phase6_complete: invalid status 'mystery'" in error for error in errors)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _patch_phase7_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(readiness, "PHASE3_PATH", tmp_path / "phase3r.json")
    monkeypatch.setattr(readiness, "PHASE4_PATH", tmp_path / "phase4.json")
    monkeypatch.setattr(readiness, "PHASE5_PATH", tmp_path / "phase5.json")
    monkeypatch.setattr(readiness, "PHASE6_PATH", tmp_path / "phase6.json")
    monkeypatch.setattr(readiness, "PHASE6_SUMMARY_PATH", tmp_path / "phase6_summary.json")
    monkeypatch.setattr(readiness, "PHASE3P_PATH", tmp_path / "phase3p.json")
    monkeypatch.setattr(readiness, "PHASE3S_PATH", tmp_path / "phase3s.json")
    monkeypatch.setattr(readiness, "CHECKLIST_PATH", tmp_path / "checklist.json")


def _operational_item(item_id: str, status: str = "pending") -> dict:
    return {"item_id": item_id, "status": status}


def _write_checklist(tmp_path: Path, *, status: str = "pending") -> None:
    items = [_operational_item(item_id, "pass") for item_id in (
        "desktop_phase6_complete", "projection_conflicts_resolved",
    )]
    items.extend(_operational_item(item_id, status) for item_id in (
        "legacy_write_freeze_window_approved", "legacy_write_freeze_announced", "final_phase2_import_rerun",
        "final_reconciliation_signed_off", "rollback_contacts_confirmed", "excel_read_only_archive_mode",
    ))
    _write_json(tmp_path / "checklist.json", {"items": items})


def _write_valid_phase7_artifacts(tmp_path: Path, *, conflict_count: int = 0) -> None:
    _write_checklist(tmp_path)
    _write_json(tmp_path / "phase3r.json", {"phase3_status": "closed"})
    _write_json(tmp_path / "phase4.json", {"phase4_status": "closed"})
    _write_json(tmp_path / "phase5_audit.json", {"registry_family_count": 26, "matched_family_count": 26, "active_file_count": 91})
    _write_json(tmp_path / "phase5_recon.json", {"families": []})
    _write_json(tmp_path / "phase5_ddkd_variants.json", {"family_code": "DDKD_CERTIFICATE", "variants": [{"variant_key": "ddkd_certificate_new"}]})
    _write_json(tmp_path / "phase5_bbtd_variants.json", {"family_code": "INSPECTION_BBTD_HOSO_DK", "variants": [{"variant_key": "bbtd_hoso_dk_all_lines"}]})
    _write_json(tmp_path / "phase5_ddkd_appendix.json", {"family_code": "DDKD_APPENDIX_OR_DECISION", "recommended_next_state": {"promotable_now": ["All"], "still_blocked": ["GCN_GMP", "QD_GMP"]}})
    _write_json(
        tmp_path / "phase5.json",
        {
            "phase5_status": "closed",
            "validation_errors": [],
            "artifact_sources": {
                "template_compatibility_audit": {
                    "path": (tmp_path / "phase5_audit.json").as_posix(),
                    "sha256": readiness.safe_load_json(tmp_path / "phase5_audit.json", "phase5_audit").payload_sha256,
                },
                "template_contract_reconciled": {
                    "path": (tmp_path / "phase5_recon.json").as_posix(),
                    "sha256": readiness.safe_load_json(tmp_path / "phase5_recon.json", "phase5_recon").payload_sha256,
                },
                "ddkd_template_variants": {
                    "path": (tmp_path / "phase5_ddkd_variants.json").as_posix(),
                    "sha256": readiness.safe_load_json(tmp_path / "phase5_ddkd_variants.json", "phase5_ddkd_variants").payload_sha256,
                },
                "bbtd_template_variants": {
                    "path": (tmp_path / "phase5_bbtd_variants.json").as_posix(),
                    "sha256": readiness.safe_load_json(tmp_path / "phase5_bbtd_variants.json", "phase5_bbtd_variants").payload_sha256,
                },
                "ddkd_appendix_field_adjudication": {
                    "path": (tmp_path / "phase5_ddkd_appendix.json").as_posix(),
                    "sha256": readiness.safe_load_json(tmp_path / "phase5_ddkd_appendix.json", "phase5_ddkd_appendix").payload_sha256,
                },
            },
        },
    )
    _write_json(
        tmp_path / "phase6_summary.json",
        {
            "overall_status": "closed",
            "required_outstanding": [],
            "validation_errors": [],
        },
    )
    phase6_summary_sha256 = readiness.safe_load_json(
        tmp_path / "phase6_summary.json",
        "phase6_summary",
    ).payload_sha256
    _write_json(
        tmp_path / "phase6.json",
        {
            "phase6_status": "closed",
            "required_outstanding": [],
            "summary_sha256": phase6_summary_sha256,
        },
    )
    _write_json(tmp_path / "phase3p.json", {"conflict_count": conflict_count, "manual_review_count": conflict_count})


def _write_valid_phase3s_summary(tmp_path: Path, *, phase3p_sha256: str, conflict_count: int) -> None:
    _write_json(
        tmp_path / "phase3s.json",
        {
            "overall_status": "ready",
            "resolved_count": conflict_count,
            "unresolved_count": 0,
            "source_conflict_count": conflict_count,
            "source_phase3p_sha256": phase3p_sha256,
            "action_counts": {"winner": 4, "no_winner": max(conflict_count - 4, 0)},
            "missing_conflict_keys": [],
            "extra_decision_keys": [],
            "validation_errors": [],
        },
    )


def test_build_readiness_blocks_when_phase3_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase3r.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["structured_data_baseline"]
    assert report["phase7_status"] == "blocked"
    assert gate["status"] == "blocked"
    assert "Phase 3 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase4_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase4.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["storage_contract_baseline"]
    assert gate["status"] == "blocked"
    assert "Phase 4 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase5_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase5.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["document_contract_baseline"]
    assert gate["status"] == "blocked"
    assert "Phase 5 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase6_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase6.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["desktop_private_share_validation"]
    assert gate["status"] == "blocked"
    assert "Phase 6 closeout artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase6_summary_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase6_summary.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["desktop_private_share_validation"]
    assert gate["status"] == "blocked"
    assert "Phase 6 desktop validation summary artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_phase3p_artifact_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase3p.json").unlink()

    report = readiness.build_readiness()

    gate = report["gates"]["current_projection_conflicts"]
    assert gate["status"] == "blocked"
    assert "current projection conflict artifact is missing" in gate["reason"]


def test_build_readiness_blocks_when_artifact_json_is_invalid(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    (tmp_path / "phase3r.json").write_text("{invalid", encoding="utf-8")

    report = readiness.build_readiness()

    gate = report["gates"]["structured_data_baseline"]
    assert gate["status"] == "blocked"
    assert "invalid JSON" in gate["reason"]


def test_build_readiness_preserves_valid_existing_behavior(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    phase3p_sha256 = readiness.safe_load_json(tmp_path / "phase3p.json", "phase3p").payload_sha256 or ""
    _write_valid_phase3s_summary(tmp_path, phase3p_sha256=phase3p_sha256, conflict_count=0)

    report = readiness.build_readiness()

    assert report["phase7_status"] == "pending"
    assert report["gates"]["structured_data_baseline"]["status"] == "pass"
    assert report["gates"]["storage_contract_baseline"]["status"] == "pass"
    assert report["gates"]["document_contract_baseline"]["status"] == "pass"
    assert report["gates"]["desktop_private_share_validation"]["status"] == "pass"
    assert report["gates"]["current_projection_conflicts"]["status"] == "pass"


def test_operational_evidence_can_make_ready(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    phase3p_sha256 = readiness.safe_load_json(tmp_path / "phase3p.json", "phase3p").payload_sha256 or ""
    _write_valid_phase3s_summary(tmp_path, phase3p_sha256=phase3p_sha256, conflict_count=0)
    payload = json.loads((tmp_path / "checklist.json").read_text(encoding="utf-8"))
    for row in payload["items"]:
        if row["item_id"] not in readiness.FREEZE_ITEM_IDS + readiness.ROLLBACK_ITEM_IDS:
            continue
        row.update({"status": "pass", "owner": "owner", "executed_on": "2026-09-05T10:00:00+00:00", "notes": "done", "evidence_refs": ["evidence"]})
        item_id = row["item_id"]
        row.update({
            "legacy_write_freeze_window_approved": {"approver": "approver", "freeze_start": "2026-09-05T10:00:00+00:00", "freeze_end": "2026-09-05T11:00:00+00:00", "approval_ref": "approval"},
            "legacy_write_freeze_announced": {"audience": "audience", "announcement_channel": "channel", "announcement_ref": "announcement"},
            "final_phase2_import_rerun": {"command_refs": ["command"], "reconciliation_ref": "reconciliation", "operator": "operator"},
            "final_reconciliation_signed_off": {"signoff_by": "signer", "signoff_ref": "signoff"},
            "rollback_contacts_confirmed": {"primary_contact": "primary", "backup_contact": "backup", "escalation_path": "path"},
            "excel_read_only_archive_mode": {"archive_owner": "archive", "archive_step_ref": "step"},
        }[item_id])
    _write_json(tmp_path / "checklist.json", payload)
    report = readiness.build_readiness()
    assert report["phase7_status"] == "ready"
    assert report["gates"]["legacy_write_freeze_execution"]["status"] == "pass"
    assert report["gates"]["rollback_window_execution"]["status"] == "pass"


def test_pass_operational_evidence_missing_field_blocks(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    payload = json.loads((tmp_path / "checklist.json").read_text(encoding="utf-8"))
    row = next(row for row in payload["items"] if row["item_id"] == "legacy_write_freeze_window_approved")
    row["status"] = "pass"
    _write_json(tmp_path / "checklist.json", payload)
    report = readiness.build_readiness()
    assert report["gates"]["legacy_write_freeze_execution"]["status"] == "blocked"


def test_operational_gate_blocks_empty_evidence_duplicate_missing_and_failed_rows(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    payload = json.loads((tmp_path / "checklist.json").read_text(encoding="utf-8"))
    row = next(row for row in payload["items"] if row["item_id"] == "legacy_write_freeze_window_approved")
    row["status"] = "pass"
    row.update({"owner": "x", "executed_on": "2026-09-05T10:00:00+00:00", "notes": "x", "evidence_refs": [], "approver": "x", "freeze_start": "2026-09-05T11:00:00+00:00", "freeze_end": "2026-09-05T10:00:00+00:00", "approval_ref": "x"})
    payload["items"].append(dict(row))
    next(row for row in payload["items"] if row["item_id"] == "final_phase2_import_rerun")["status"] = "fail"
    _write_json(tmp_path / "checklist.json", payload)
    report = readiness.build_readiness()
    assert report["phase7_status"] == "blocked"
    assert report["gates"]["legacy_write_freeze_execution"]["status"] == "blocked"


def test_rollback_pending_and_malformed_checklist_block(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    report = readiness.build_readiness()
    assert report["gates"]["rollback_window_execution"]["status"] == "pending"
    (tmp_path / "checklist.json").write_text("{invalid", encoding="utf-8")
    report = readiness.build_readiness()
    assert report["gates"]["rollback_window_execution"]["status"] == "blocked"


def test_build_readiness_blocks_when_phase6_closeout_is_stale_relative_to_summary(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    _write_json(
        tmp_path / "phase6.json",
        {
            "phase6_status": "closed",
            "required_outstanding": [],
            "summary_sha256": "deadbeef",
        },
    )

    report = readiness.build_readiness()

    gate = report["gates"]["desktop_private_share_validation"]
    assert gate["status"] == "blocked"
    assert "stale relative to the current desktop validation summary" in gate["reason"]


def test_build_readiness_blocks_when_phase5_closeout_is_stale_relative_to_upstream_artifact(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path)
    _write_json(tmp_path / "phase5.json", {"phase5_status": "closed", "validation_errors": [], "artifact_sources": {"template_compatibility_audit": {"path": (tmp_path / "phase5_audit.json").as_posix(), "sha256": "deadbeef"}, "template_contract_reconciled": {"path": (tmp_path / "phase5_recon.json").as_posix(), "sha256": readiness.safe_load_json(tmp_path / "phase5_recon.json", "phase5_recon").payload_sha256}, "ddkd_template_variants": {"path": (tmp_path / "phase5_ddkd_variants.json").as_posix(), "sha256": readiness.safe_load_json(tmp_path / "phase5_ddkd_variants.json", "phase5_ddkd_variants").payload_sha256}, "bbtd_template_variants": {"path": (tmp_path / "phase5_bbtd_variants.json").as_posix(), "sha256": readiness.safe_load_json(tmp_path / "phase5_bbtd_variants.json", "phase5_bbtd_variants").payload_sha256}, "ddkd_appendix_field_adjudication": {"path": (tmp_path / "phase5_ddkd_appendix.json").as_posix(), "sha256": readiness.safe_load_json(tmp_path / "phase5_ddkd_appendix.json", "phase5_ddkd_appendix").payload_sha256}}})

    report = readiness.build_readiness()

    gate = report["gates"]["document_contract_baseline"]
    assert gate["status"] == "blocked"
    assert "stale relative to template_compatibility_audit" in gate["reason"]


def test_build_readiness_blocks_when_phase3s_summary_is_stale_relative_to_phase3p(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path, conflict_count=14)
    _write_valid_phase3s_summary(tmp_path, phase3p_sha256="deadbeef", conflict_count=14)

    report = readiness.build_readiness()

    gate = report["gates"]["current_projection_conflicts"]
    assert gate["status"] == "blocked"
    assert "stale relative to the current Phase 3p artifact" in gate["reason"]


def test_build_readiness_passes_when_phase3s_summary_validates_all_conflicts(tmp_path: Path, monkeypatch) -> None:
    _patch_phase7_paths(monkeypatch, tmp_path)
    _write_valid_phase7_artifacts(tmp_path, conflict_count=14)
    phase3p_sha256 = readiness.safe_load_json(tmp_path / "phase3p.json", "phase3p").payload_sha256 or ""
    _write_valid_phase3s_summary(tmp_path, phase3p_sha256=phase3p_sha256, conflict_count=14)

    report = readiness.build_readiness()

    gate = report["gates"]["current_projection_conflicts"]
    assert gate["status"] == "pass"
    assert gate["detail"]["resolved_count"] == 14
