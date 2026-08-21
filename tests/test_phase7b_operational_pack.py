from tools.build_phase7b_operational_pack import item_execution_notes, required_fields


def test_required_fields_for_freeze_window_include_approval_data():
    fields = required_fields("legacy_write_freeze_window_approved")

    assert "approver" in fields
    assert "freeze_start" in fields
    assert "freeze_end" in fields


def test_required_fields_for_rollback_contacts_include_contacts():
    fields = required_fields("rollback_contacts_confirmed")

    assert "primary_contact" in fields
    assert "backup_contact" in fields
    assert "escalation_path" in fields


def test_item_execution_notes_are_specific():
    note = item_execution_notes("final_phase2_import_rerun")

    assert "final migration import/reconciliation sequence" in note
