import json

from tools import build_phase7b_operational_pack as pack


def test_required_fields_for_freeze_window_include_approval_data():
    fields = pack.required_fields("legacy_write_freeze_window_approved")

    assert "approver" in fields
    assert "freeze_start" in fields
    assert "freeze_end" in fields


def test_required_fields_for_rollback_contacts_include_contacts():
    fields = pack.required_fields("rollback_contacts_confirmed")

    assert "primary_contact" in fields
    assert "backup_contact" in fields
    assert "escalation_path" in fields


def test_item_execution_notes_are_specific():
    note = pack.item_execution_notes("final_phase2_import_rerun")

    assert "final migration import/reconciliation sequence" in note


def test_operational_pack_can_keep_post_go_live_excel_archive_pending(tmp_path):
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "cutover_execution_checklist.json").write_text(
        json.dumps({"items": [{"item_id": "excel_read_only_archive_mode", "status": "pending", "required_for_cutover": True, "notes": "after go-live"}]}),
        encoding="utf-8",
    )
    (evidence_dir / "cutover_readiness.json").write_text(json.dumps({"phase7_status": "ready", "gates": {}}), encoding="utf-8")
    (evidence_dir / "cutover_checklist_summary.json").write_text(
        json.dumps({"overall_status": "pending", "required_outstanding": ["excel_read_only_archive_mode"]}), encoding="utf-8"
    )

    report = pack.build_operational_pack(evidence_dir=evidence_dir)

    assert report["phase7_status"] == "ready"
    assert report["checklist_status"] == "pending"
    assert report["pending_items"][0]["item_id"] == "excel_read_only_archive_mode"
