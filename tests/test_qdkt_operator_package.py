"""Operator package replay does not authenticate a runtime or custodian."""
from copy import deepcopy
from pathlib import Path
import json

import pytest

from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation
from tests.test_qdkt_runtime_identity import _observation


def test_acceptance_distinguishes_static_bytes_from_unsigned_session_claims():
    result = assess_runtime_observation(_observation())
    matrix = result["acceptance_matrix"]
    assert matrix["supplied_snapshot"] == "BYTE_IDENTITY_PROVEN"
    assert matrix["reviewed_source"] == "SOURCE_EQUIVALENCE_PROVEN"
    assert matrix["export_encoding"] == "ENCODING_AMBIGUOUS"
    assert matrix["build_distribution"] == "VERSION_BINDING_UNVERIFIED"
    assert matrix["independent_custody"] == "EVIDENCE_UNAVAILABLE"
    assert matrix["executable_vba"] == "RUNTIME_IDENTITY_UNVERIFIED"
    assert matrix["business_owner_acceptance"] == "EVIDENCE_UNAVAILABLE"
    assert result["acquisition_clock_authenticated"] is False


def test_disk_capture_before_session_is_not_hidden_by_matching_hash():
    observation = _observation()
    observation["on_disk"]["captured_at"] = "2026-10-28T01:00:00+00:00"
    result = assess_runtime_observation(observation)
    assert result["disk_capture_relation"] == "PREDATES_REPORTED_SESSION"
    assert result["runtime_identity_verified"] is False


def test_multiple_sessions_and_same_name_paths_are_explicit_not_selected_by_heuristic():
    observation = _observation()
    observation["excel_process_ids"].append(999)
    other = deepcopy(observation["available_addins"][0])
    other["full_path"] = r"Y:\another\GPs.xlam"
    observation["available_addins"].append(other)
    result = assess_runtime_observation(observation)
    assert result["same_name_path_ambiguity_reported"] is True
    assert result["multiple_excel_processes_reported"] is True
    assert result["all_loaded_instances_accounted_for"] is False
    assert result["runtime_identity_verified"] is False


def test_correct_disk_claim_at_a_different_physical_path_is_not_rebound():
    from backend.app.document.inspection_qd_kt_runtime_identity import QdKtRuntimeIdentityBlocked
    observation = _observation()
    observation["on_disk"]["path"] = r"D:\reviewed-copy\GPs.xlam"
    with pytest.raises(QdKtRuntimeIdentityBlocked, match="DISK_PATH_MISMATCH"):
        assess_runtime_observation(observation)


def test_replaced_file_after_observation_does_not_attest_earlier_loaded_code():
    observation = _observation()
    observation["on_disk"]["sha256"] = "0" * 64
    result = assess_runtime_observation(observation)
    assert result["acceptance_matrix"]["reported_disk"] == "CONTRADICTED"
    assert result["disk_capture_relation"] == "POST_SESSION_OBSERVATION_NOT_MEMORY_BINDING"
    assert result["runtime_identity_verified"] is False


def test_consistent_changed_clock_offset_does_not_authenticate_clock_or_custody():
    observation = _observation()
    for key in ("capture_started_at", "capture_completed_at"):
        observation[key] = observation[key].replace("+00:00", "+07:00")
    for key in ("started_at", "started_at_after"):
        observation["process"][key] = observation["process"][key].replace("+00:00", "+07:00")
    result = assess_runtime_observation(observation)
    assert result["acquisition_clock_authenticated"] is False
    assert result["acceptance_matrix"]["independent_custody"] == "EVIDENCE_UNAVAILABLE"
    assert result["runtime_identity_verified"] is False


def test_package_is_deterministic_replayable_without_private_binaries_and_detects_tamper(tmp_path):
    from tools.qdkt_operator_evidence_package import build_operator_package, verify_operator_package, PACKAGE_FILES
    root = Path(__file__).resolve().parents[1]
    for relative in PACKAGE_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / relative).read_bytes())
    package = build_operator_package(tmp_path)
    assert build_operator_package(tmp_path) == package
    assert verify_operator_package(tmp_path, package)["package_files_match"] is True
    assert package["collector_authenticated"] is package["ready_to_render"] is False
    lossy = deepcopy(package)
    lossy["ready_to_render"] = 0
    with pytest.raises(ValueError, match="QDKT_OPERATOR_PACKAGE_DRIFT"):
        verify_operator_package(tmp_path, lossy)
    target = tmp_path / "tools/Observe-QdktExcelRuntime.ps1"
    target.write_bytes(target.read_bytes() + b"\n# changed")
    with pytest.raises(ValueError, match="QDKT_OPERATOR_PACKAGE_DRIFT"):
        verify_operator_package(tmp_path, package)


@pytest.mark.parametrize("exists,status", [(False, "EVIDENCE_UNAVAILABLE"), (True, "INVALID_EVIDENCE")])
def test_cli_distinguishes_unavailable_from_invalid_without_static_rescue(tmp_path, capsys, exists, status):
    from tools.audit_qdkt_source_transformations import main
    if exists:
        (tmp_path / "observation.json").write_bytes(b'{"collector":"\\ud800"}')
    assert main(["--assess-runtime-observation", str(tmp_path), "observation.json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["input_evidence_status"] == status
    assert report["ready_to_render"] is False
    assert "local_artifact_verification" not in report
