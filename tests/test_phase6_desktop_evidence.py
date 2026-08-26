from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from tools import validate_phase6_desktop_evidence as phase6


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8", newline="\n")
    return sha256(encoded.encode("utf-8")).hexdigest()


def _base_matrix() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
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
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "required_for_phase_close": True,
                "status": "pass",
                "notes": f"Matrix contract for {scenario_id}",
                "required_evidence_fields": phase6.required_evidence_fields_for_scenario(scenario_id),
            }
        )
    scenarios.append(
        {
            "scenario_id": "local_word_open_edit_save_harness",
            "required_for_phase_close": False,
            "status": "pass",
            "notes": "Supporting harness",
        }
    )
    return {
        "generated_on": "2026-08-26",
        "phase": "phase6_desktop_private_share_validation",
        "required_scenario_count": 10,
        "scenarios": scenarios,
    }


def _evidence_row(scenario_id: str) -> dict[str, Any]:
    row = {
        "scenario_id": scenario_id,
        "operator": "business_owner/operator",
        "executed_on": "2026-08-26",
        "machine_name": "Windows operator workstation",
        "network_mode": "tailscale_private_network",
        "share_path": r"\\100.95.45.127\Hồ sơ nội bộ",
        "status": "pass",
        "required_for_phase_close": True,
        "notes": f"Evidence for {scenario_id}",
        "evidence_refs": ["operator_attestation"],
    }
    if scenario_id in {"word_open_existing_doc_private_share", "word_direct_save_private_share"}:
        row["document_path"] = r"\\100.95.45.127\Hồ sơ nội bộ\_GXP_PHASE6_TEST\phase6_word_test.docx"
        row["word_behavior"] = "Word opened and saved the document directly from the share."
    if scenario_id in {"disconnect_during_open", "disconnect_during_save", "reconnect_after_disconnect"}:
        row["disconnect_method"] = "controlled temporary network/Tailscale interruption"
        row["recovery_observed"] = "Share access recovered after reconnect."
    if scenario_id == "two_user_lock_contention_private_share":
        row["user_a"] = "desktop_session_A"
        row["user_b"] = "desktop_session_B"
        row["lock_outcome"] = "Lock contention was observed without silent overwrite."
    return row


def _base_evidence() -> dict[str, Any]:
    return {
        "generated_on": "2026-08-26",
        "evidence_status": "operator_attested_pass",
        "source": "business owner/operator attestation in ChatGPT conversation",
        "scenarios": [
            _evidence_row("private_share_mapping_active"),
            _evidence_row("explorer_navigation_private_share"),
            _evidence_row("word_open_existing_doc_private_share"),
            _evidence_row("word_direct_save_private_share"),
            _evidence_row("office_wifi_single_user"),
            _evidence_row("hotspot_single_user"),
            _evidence_row("disconnect_during_open"),
            _evidence_row("disconnect_during_save"),
            _evidence_row("reconnect_after_disconnect"),
            _evidence_row("two_user_lock_contention_private_share"),
        ],
    }


def _env_probe() -> dict[str, Any]:
    return {
        "word_com": {"available": True},
        "explorer_executable": "C:/Windows/explorer.exe",
        "active_smb_mappings": [{"remote_path": r"\\100.95.45.127\Hồ sơ nội bộ"}],
        "disconnected_smb_mappings": [],
        "tailscale_executable": "C:/Program Files/Tailscale/tailscale.exe",
    }


def _word_harness() -> dict[str, Any]:
    return {
        "document_updated_text_verified": True,
        "lock_behavior_observed": True,
        "second_open_read_only": True,
        "second_open_error": None,
    }


def test_validate_matrix_rows_accepts_known_statuses() -> None:
    errors = phase6.validate_matrix_rows(
        [
            {"scenario_id": "a", "status": "pass"},
            {"scenario_id": "b", "status": "blocked"},
            {"scenario_id": "c", "status": "pending"},
            {"scenario_id": "d", "status": "not_tested"},
        ]
    )

    assert errors == []


def test_validate_matrix_rows_rejects_duplicate_ids_and_unknown_status() -> None:
    errors = phase6.validate_matrix_rows(
        [
            {"scenario_id": "dup", "status": "pass"},
            {"scenario_id": "dup", "status": "mystery"},
        ]
    )

    assert any("duplicate scenario_id: dup" in error for error in errors)
    assert any("dup: invalid status 'mystery'" in error for error in errors)


def test_build_summary_reconciles_all_ten_required_scenarios(tmp_path: Path) -> None:
    matrix_path = tmp_path / "matrix.json"
    evidence_path = tmp_path / "evidence.json"
    env_probe_path = tmp_path / "env_probe.json"
    word_harness_path = tmp_path / "word_harness.json"
    matrix_sha = _write_json(matrix_path, _base_matrix())
    evidence_sha = _write_json(evidence_path, _base_evidence())
    _write_json(env_probe_path, _env_probe())
    _write_json(word_harness_path, _word_harness())

    summary = phase6.build_summary(
        matrix_path=matrix_path,
        evidence_path=evidence_path,
        env_probe_path=env_probe_path,
        word_harness_path=word_harness_path,
    )

    assert summary["overall_status"] == "closed"
    assert summary["required_scenario_count"] == 10
    assert summary["required_pass_count"] == 10
    assert summary["required_outstanding"] == []
    assert summary["validation_errors"] == []
    assert summary["evidence_sha256"] == evidence_sha
    assert summary["matrix_sha256"] == matrix_sha
    assert len(summary["scenario_reconciliation"]) == 10


def test_build_summary_fails_closed_when_required_scenario_missing(tmp_path: Path) -> None:
    evidence = _base_evidence()
    evidence["scenarios"] = evidence["scenarios"][:-1]
    _write_json(tmp_path / "matrix.json", _base_matrix())
    _write_json(tmp_path / "evidence.json", evidence)
    _write_json(tmp_path / "env_probe.json", _env_probe())
    _write_json(tmp_path / "word_harness.json", _word_harness())

    summary = phase6.build_summary(
        matrix_path=tmp_path / "matrix.json",
        evidence_path=tmp_path / "evidence.json",
        env_probe_path=tmp_path / "env_probe.json",
        word_harness_path=tmp_path / "word_harness.json",
    )

    assert summary["overall_status"] == "invalid"
    assert "two_user_lock_contention_private_share" in summary["missing_required_scenarios"]


def test_build_summary_fails_closed_when_unknown_scenario_present(tmp_path: Path) -> None:
    evidence = _base_evidence()
    evidence["scenarios"].append(_evidence_row("unknown_extra_scenario"))
    _write_json(tmp_path / "matrix.json", _base_matrix())
    _write_json(tmp_path / "evidence.json", evidence)
    _write_json(tmp_path / "env_probe.json", _env_probe())
    _write_json(tmp_path / "word_harness.json", _word_harness())

    summary = phase6.build_summary(
        matrix_path=tmp_path / "matrix.json",
        evidence_path=tmp_path / "evidence.json",
        env_probe_path=tmp_path / "env_probe.json",
        word_harness_path=tmp_path / "word_harness.json",
    )

    assert summary["overall_status"] == "invalid"
    assert summary["extra_unknown_scenarios"] == ["unknown_extra_scenario"]


def test_build_summary_fails_closed_when_required_scenario_is_not_pass(tmp_path: Path) -> None:
    evidence = _base_evidence()
    evidence["scenarios"][0]["status"] = "blocked"
    _write_json(tmp_path / "matrix.json", _base_matrix())
    _write_json(tmp_path / "evidence.json", evidence)
    _write_json(tmp_path / "env_probe.json", _env_probe())
    _write_json(tmp_path / "word_harness.json", _word_harness())

    summary = phase6.build_summary(
        matrix_path=tmp_path / "matrix.json",
        evidence_path=tmp_path / "evidence.json",
        env_probe_path=tmp_path / "env_probe.json",
        word_harness_path=tmp_path / "word_harness.json",
    )

    assert summary["overall_status"] == "invalid"
    assert any("must have status 'pass'" in error for error in summary["validation_errors"])


def test_build_summary_fails_closed_when_required_evidence_field_missing(tmp_path: Path) -> None:
    evidence = _base_evidence()
    del evidence["scenarios"][2]["document_path"]
    _write_json(tmp_path / "matrix.json", _base_matrix())
    _write_json(tmp_path / "evidence.json", evidence)
    _write_json(tmp_path / "env_probe.json", _env_probe())
    _write_json(tmp_path / "word_harness.json", _word_harness())

    summary = phase6.build_summary(
        matrix_path=tmp_path / "matrix.json",
        evidence_path=tmp_path / "evidence.json",
        env_probe_path=tmp_path / "env_probe.json",
        word_harness_path=tmp_path / "word_harness.json",
    )

    assert summary["overall_status"] == "invalid"
    assert any("document_path" in error for error in summary["validation_errors"])


def test_repo_phase6_evidence_chain_closes_cleanly() -> None:
    summary = phase6.build_summary()

    expected_evidence_sha = sha256(phase6.EVIDENCE_PATH.read_bytes()).hexdigest()
    expected_matrix_sha = sha256(phase6.DEFAULT_MATRIX.read_bytes()).hexdigest()

    assert summary["overall_status"] == "closed"
    assert summary["required_scenario_count"] == 10
    assert summary["required_pass_count"] == 10
    assert summary["required_fail_count"] == 0
    assert summary["required_blocked_count"] == 0
    assert summary["required_pending_count"] == 0
    assert summary["required_outstanding"] == []
    assert summary["validation_errors"] == []
    assert summary["evidence_path"] == "artifacts/phase6/phase6_desktop_validation_evidence_20260826.json"
    assert summary["evidence_sha256"] == expected_evidence_sha
    assert summary["matrix_path"] == "artifacts/phase6/desktop_validation_matrix.template.json"
    assert summary["matrix_sha256"] == expected_matrix_sha
