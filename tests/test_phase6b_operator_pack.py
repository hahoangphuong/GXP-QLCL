from tools.build_phase6b_operator_pack import required_evidence_fields, scenario_execution_notes


def test_required_evidence_fields_adds_word_specific_fields():
    fields = required_evidence_fields("word_direct_save_private_share")

    assert "document_path" in fields
    assert "word_behavior" in fields


def test_required_evidence_fields_adds_lock_fields():
    fields = required_evidence_fields("two_user_lock_contention_private_share")

    assert "user_a" in fields
    assert "user_b" in fields
    assert "lock_outcome" in fields


def test_scenario_execution_notes_returns_specific_hint():
    note = scenario_execution_notes("disconnect_during_save")

    assert "Interrupt network during save" in note
