from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from tools import build_phase6b_operator_pack as phase6b


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8", newline="\n")
    return sha256(encoded.encode("utf-8")).hexdigest()


def _summary() -> dict[str, Any]:
    scenarios = []
    for scenario_id in [
        "private_share_mapping_active",
        "explorer_navigation_private_share",
        "word_open_existing_doc_private_share",
        "word_direct_save_private_share",
        "office_wifi_single_user",
        "hotspot_single_user",
        "disconnect_during_open",
        "disconnect_during_save",
        "reconnect_after_disconnect",
        "two_user_lock_contention_private_share",
    ]:
        scenarios.append({"scenario_id": scenario_id, "status": "pass"})
    return {
        "overall_status": "closed",
        "evidence_path": "evidence.json",
        "evidence_sha256": "",
        "required_outstanding": [],
        "scenario_reconciliation": scenarios,
    }


def _evidence() -> dict[str, Any]:
    return {
        "scenarios": [
            {
                "scenario_id": "private_share_mapping_active",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
            },
            {
                "scenario_id": "explorer_navigation_private_share",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
            },
            {
                "scenario_id": "word_open_existing_doc_private_share",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
                "document_path": "x.docx",
                "word_behavior": "opened",
            },
            {
                "scenario_id": "word_direct_save_private_share",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
                "document_path": "x.docx",
                "word_behavior": "saved",
            },
            {
                "scenario_id": "office_wifi_single_user",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
            },
            {
                "scenario_id": "hotspot_single_user",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
            },
            {
                "scenario_id": "disconnect_during_open",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
                "disconnect_method": "controlled interruption",
                "recovery_observed": "recovered",
            },
            {
                "scenario_id": "disconnect_during_save",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
                "disconnect_method": "controlled interruption",
                "recovery_observed": "recovered",
            },
            {
                "scenario_id": "reconnect_after_disconnect",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
                "disconnect_method": "controlled interruption",
                "recovery_observed": "recovered",
            },
            {
                "scenario_id": "two_user_lock_contention_private_share",
                "executed_on": "2026-08-26",
                "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
                "evidence_refs": ["operator_attestation"],
                "user_a": "A",
                "user_b": "B",
                "lock_outcome": "observed",
            },
        ]
    }


def test_required_evidence_fields_adds_word_specific_fields() -> None:
    fields = phase6b.required_evidence_fields("word_direct_save_private_share")

    assert "document_path" in fields
    assert "word_behavior" in fields


def test_required_evidence_fields_adds_lock_fields() -> None:
    fields = phase6b.required_evidence_fields("two_user_lock_contention_private_share")

    assert "user_a" in fields
    assert "user_b" in fields
    assert "lock_outcome" in fields


def test_scenario_execution_notes_returns_specific_hint() -> None:
    note = phase6b.scenario_execution_notes("disconnect_during_save")

    assert "disconnect-during-save" in note


def test_build_operator_pack_carries_evidence_provenance_and_ten_rows(tmp_path: Path) -> None:
    summary = _summary()
    evidence_path = tmp_path / "evidence.json"
    evidence_sha = _write_json(evidence_path, _evidence())
    summary["evidence_path"] = evidence_path.as_posix()
    summary["evidence_sha256"] = evidence_sha
    summary_path = tmp_path / "summary.json"
    _write_json(summary_path, summary)

    report = phase6b.build_operator_pack(summary_path=summary_path, evidence_path=evidence_path)

    assert report["phase6_status"] == "closed"
    assert report["summary_sha256"] == sha256(summary_path.read_bytes()).hexdigest()
    assert report["evidence_sha256"] == evidence_sha
    assert len(report["scenario_rows"]) == 10
    assert report["required_outstanding_count"] == 0
