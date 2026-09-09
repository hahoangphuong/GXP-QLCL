from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tools import init_phase7_execution as initializer
from tools import update_phase7_execution_item as updater
from tools.phase7_execution_evidence import ROOT, TEMPLATE_PATH
from tools.validate_phase7_cutover_checklist import AUTHORITATIVE_ITEM_IDS, validate_rows


def _evidence_dir(tmp_path: Path) -> Path:
    evidence_dir = (tmp_path / "evidence").resolve()
    assert initializer.main(["--output-dir", str(evidence_dir)]) == 0
    return evidence_dir


def _checklist_path(evidence_dir: Path) -> Path:
    return evidence_dir / "cutover_execution_checklist.json"


def _payload(evidence_dir: Path) -> dict:
    return json.loads(_checklist_path(evidence_dir).read_text(encoding="utf-8"))


def _update(evidence_dir: Path, *args: str) -> int:
    return updater.main(["--evidence-dir", str(evidence_dir), *args])


def _rollback_pass_args() -> list[str]:
    return [
        "--item-id", "rollback_contacts_confirmed", "--status", "pass",
        "--set", "owner=owner", "--set", "executed_on=2026-09-06T10:00:00+00:00",
        "--set", "notes=confirmed", "--set", "primary_contact=primary",
        "--set", "backup_contact=backup", "--set", "escalation_path=path",
        "--evidence-ref", "ticket-1",
    ]


def _rollback_single_operator_args() -> list[str]:
    return [
        "--item-id", "rollback_contacts_confirmed", "--status", "pass",
        "--set", "owner=owner", "--set", "executed_on=2026-09-06T10:00:00+00:00",
        "--set", "notes=confirmed", "--set", "primary_contact=primary",
        "--set", "operator_mode=single_operator_test", "--set", "backup_contact=N/A",
        "--set", "escalation_path=N/A", "--evidence-ref", "ticket-1",
    ]


def _freeze_pass_args() -> list[str]:
    return [
        "--item-id", "legacy_write_freeze_window_approved", "--status", "pass",
        "--set", "owner=owner", "--set", "executed_on=2026-09-06T10:00:00+00:00",
        "--set", "notes=approved", "--set", "approver=approver",
        "--set", "execution_scope=cutover",
        "--set", "freeze_start=2026-09-06T10:00:00+00:00",
        "--set", "freeze_end=2026-09-06T11:00:00+00:00",
        "--set", "approval_ref=approval", "--evidence-ref", "ticket-1",
    ]


def _replace_set(arguments: list[str], field: str, value: str) -> list[str]:
    replacement = list(arguments)
    for index, argument in enumerate(replacement):
        if argument.startswith(f"{field}="):
            replacement[index] = f"{field}={value}"
            return replacement
    raise AssertionError(f"Missing test field: {field}")


def test_exact_known_item_update_creates_backup_and_preserves_other_rows(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    before = _checklist_path(evidence_dir).read_bytes()
    before_rows = _payload(evidence_dir)["items"]

    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "blocked", "--set", "notes=blocked") == 0

    after = _payload(evidence_dir)["items"]
    assert next(row for row in after if row["item_id"] == "desktop_phase6_complete")["status"] == "blocked"
    assert [row for row in after if row["item_id"] != "desktop_phase6_complete"] == [row for row in before_rows if row["item_id"] != "desktop_phase6_complete"]
    backups = list(evidence_dir.glob("cutover_execution_checklist.before-*.json"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before
    assert json.loads(_checklist_path(evidence_dir).read_text(encoding="utf-8"))["items"]


def test_unknown_duplicate_missing_and_external_path_fail_closed(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    original = _checklist_path(evidence_dir).read_bytes()
    assert _update(evidence_dir, "--item-id", "unknown", "--status", "pending") == 1
    assert updater.main(["--evidence-dir", "relative", "--item-id", "desktop_phase6_complete", "--status", "pending"]) == 1
    assert updater.main(["--evidence-dir", str(ROOT), "--item-id", "desktop_phase6_complete", "--status", "pending"]) == 1
    payload = _payload(evidence_dir)
    payload["items"].append(dict(payload["items"][0]))
    _checklist_path(evidence_dir).write_text(json.dumps(payload), encoding="utf-8")
    duplicate_bytes = _checklist_path(evidence_dir).read_bytes()
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending") == 1
    assert _checklist_path(evidence_dir).read_bytes() == duplicate_bytes
    _checklist_path(evidence_dir).unlink()
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending") == 1
    assert original


def test_rejects_structural_unknown_and_invalid_pass_updates_without_writing(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    original = _checklist_path(evidence_dir).read_bytes()
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending", "--set", "item_id=x") == 1
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending", "--set", "unexpected=x") == 1
    assert _update(evidence_dir, "--item-id", "rollback_contacts_confirmed", "--status", "pass") == 1
    assert _checklist_path(evidence_dir).read_bytes() == original


def test_rejects_list_fields_and_duplicate_scalars_through_set(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    original = _checklist_path(evidence_dir).read_bytes()
    assert _update(evidence_dir, "--item-id", "rollback_contacts_confirmed", "--status", "pending", "--set", "evidence_refs=x") == 1
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending", "--set", "notes=first", "--set", "notes=second") == 1
    assert _checklist_path(evidence_dir).read_bytes() == original


def test_operator_mode_is_mutable_only_for_rollback_contacts(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending", "--set", "operator_mode=single_operator_test") == 1
    assert _update(evidence_dir, "--item-id", "rollback_contacts_confirmed", "--status", "pending", "--set", "operator_mode=standard") == 0


def test_execution_scope_is_mutable_only_for_freeze_items_and_uses_closed_values(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending", "--set", "execution_scope=cutover") == 1
    assert _update(evidence_dir, "--item-id", "legacy_write_freeze_window_approved", "--status", "pending", "--set", "execution_scope=unknown") == 1
    assert _update(evidence_dir, "--item-id", "legacy_write_freeze_window_approved", "--status", "pending", "--set", "execution_scope=rehearsal") == 0
    assert _update(evidence_dir, *_replace_set(_freeze_pass_args(), "execution_scope", "unknown")) == 1
    assert _update(evidence_dir, *_replace_set(_freeze_pass_args(), "execution_scope", "rehearsal")) == 0
    row = next(row for row in _payload(evidence_dir)["items"] if row["item_id"] == "legacy_write_freeze_window_approved")
    assert row["execution_scope"] == "rehearsal"


def test_pass_validation_for_rollback_and_freeze_timestamps(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    assert _update(evidence_dir, *_rollback_pass_args()) == 0
    assert next(row for row in _payload(evidence_dir)["items"] if row["item_id"] == "rollback_contacts_confirmed")["status"] == "pass"
    assert _update(evidence_dir, "--item-id", "legacy_write_freeze_window_approved", "--status", "pass") == 1
    assert _update(evidence_dir, *_replace_set(_freeze_pass_args(), "freeze_end", "2026-09-06T09:00:00+00:00")) == 1
    assert _update(evidence_dir, *_replace_set(_freeze_pass_args(), "executed_on", "invalid")) == 1
    assert _update(evidence_dir, *_replace_set(_freeze_pass_args(), "freeze_start", "invalid")) == 1
    assert _update(evidence_dir, *_freeze_pass_args()) == 0


def test_rollback_operator_modes_fail_closed_without_weakening_standard_mode(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    assert _update(evidence_dir, *_rollback_pass_args()) == 0
    assert _update(evidence_dir, *_replace_set(_rollback_pass_args(), "backup_contact", "N/A")) == 1
    assert _update(evidence_dir, *_replace_set(_rollback_pass_args(), "escalation_path", "N/A")) == 1

    single = _rollback_single_operator_args()
    assert _update(evidence_dir, *_replace_set(single, "backup_contact", "backup")) == 1
    assert _update(evidence_dir, *_replace_set(single, "escalation_path", "path")) == 1
    assert _update(evidence_dir, *_replace_set(single, "owner", "")) == 1
    assert _update(evidence_dir, *_replace_set(single, "primary_contact", "")) == 1
    assert _update(evidence_dir, *_replace_set(single, "operator_mode", "unknown")) == 1

    isolated = _evidence_dir(tmp_path / "single")
    assert _update(isolated, *_rollback_single_operator_args()) == 0
    row = next(row for row in _payload(isolated)["items"] if row["item_id"] == "rollback_contacts_confirmed")
    assert row["operator_mode"] == "single_operator_test"


def test_single_operator_mode_requires_evidence_and_preserves_authoritative_ids(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    without_evidence = [argument for argument in _rollback_single_operator_args() if argument not in {"--evidence-ref", "ticket-1"}]
    assert _update(evidence_dir, *without_evidence) == 1
    payload = _payload(evidence_dir)
    rollback = next(row for row in payload["items"] if row["item_id"] == "rollback_contacts_confirmed")
    rollback.update({
        "status": "pass", "owner": "owner", "executed_on": "2026-09-06T10:00:00+00:00",
        "notes": "done", "primary_contact": "primary", "operator_mode": "single_operator_test",
        "backup_contact": "N/A", "escalation_path": "N/A", "evidence_refs": ["evidence"],
    })
    assert validate_rows(payload["items"]) == []
    assert {row["item_id"] for row in payload["items"]} == AUTHORITATIVE_ITEM_IDS


def test_list_fields_are_typed_deterministic_and_dry_run_has_no_filesystem_effects(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    original = _checklist_path(evidence_dir).read_bytes()
    assert _update(evidence_dir, *_rollback_pass_args(), "--evidence-ref", "ticket-2", "--dry-run") == 0
    assert _checklist_path(evidence_dir).read_bytes() == original
    assert not list(evidence_dir.glob("*.before-*.json"))
    assert _update(evidence_dir, *_rollback_pass_args(), "--evidence-ref", "ticket-1") == 1
    assert _update(evidence_dir, *_rollback_pass_args(), "--evidence-ref", "ticket-2") == 0
    row = next(row for row in _payload(evidence_dir)["items"] if row["item_id"] == "rollback_contacts_confirmed")
    assert row["evidence_refs"] == ["ticket-1", "ticket-2"]


def test_final_import_pass_requires_typed_command_refs(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    args = [
        "--item-id", "final_phase2_import_rerun", "--status", "pass",
        "--set", "owner=owner", "--set", "executed_on=2026-09-06T10:00:00+00:00",
        "--set", "notes=completed", "--set", "reconciliation_ref=reconciliation",
        "--set", "operator=operator", "--evidence-ref", "evidence",
    ]
    assert _update(evidence_dir, *args) == 1
    assert _update(evidence_dir, *args, "--command-ref", "command") == 0
    row = next(row for row in _payload(evidence_dir)["items"] if row["item_id"] == "final_phase2_import_rerun")
    assert row["command_refs"] == ["command"]


def test_template_and_generated_outputs_are_unchanged_and_all_ids_remain(tmp_path: Path) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    template = TEMPLATE_PATH.read_bytes()
    generated = {
        "cutover_readiness.json": b"readiness",
        "cutover_checklist_summary.json": b"summary",
    }
    for name, content in generated.items():
        (evidence_dir / name).write_bytes(content)
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending") == 0
    assert TEMPLATE_PATH.read_bytes() == template
    assert {row["item_id"] for row in _payload(evidence_dir)["items"]} == AUTHORITATIVE_ITEM_IDS
    assert {name: (evidence_dir / name).read_bytes() for name in generated} == generated


def test_backup_name_collision_preserves_existing_backup(tmp_path: Path, monkeypatch) -> None:
    evidence_dir = _evidence_dir(tmp_path)

    class FixedDatetime:
        @staticmethod
        def now(tz):
            assert tz is UTC
            return datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(updater, "datetime", FixedDatetime)
    existing = evidence_dir / "cutover_execution_checklist.before-20260906T120000000000Z.json"
    existing.write_bytes(b"prior-backup")

    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending") == 0

    assert existing.read_bytes() == b"prior-backup"
    collision_backup = evidence_dir / "cutover_execution_checklist.before-20260906T120000000000Z-1.json"
    assert collision_backup.is_file()


def test_replace_failure_preserves_original_and_removes_temp_file(tmp_path: Path, monkeypatch) -> None:
    evidence_dir = _evidence_dir(tmp_path)
    checklist = _checklist_path(evidence_dir)
    original = checklist.read_bytes()

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(updater.os, "replace", fail_replace)
    assert _update(evidence_dir, "--item-id", "desktop_phase6_complete", "--status", "pending") == 1

    assert checklist.read_bytes() == original
    assert not list(evidence_dir.glob(".cutover_execution_checklist.json.*.tmp"))
