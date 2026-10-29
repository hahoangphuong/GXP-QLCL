"""Unsigned runtime observations cannot authenticate the Excel-loaded code."""
from copy import deepcopy
import json

import pytest

from backend.app.document.inspection_qd_kt_provenance_gate import QdKtProvenanceGateBlocked, read_provenance_json


@pytest.mark.parametrize("payload", [b'{"collector":"\\ud800"}', b'{"\\udfff":"observer"}', b'{"nested":["\\ud800"]}'])
def test_unpaired_surrogates_cannot_enter_utf8_provenance(tmp_path, payload):
    path = tmp_path / "observation.json"
    path.write_bytes(payload)
    with pytest.raises(QdKtProvenanceGateBlocked, match="QDKT_SOURCE_PROVENANCE_INCOMPLETE"):
        read_provenance_json(path)


def test_valid_unicode_pairs_and_combining_marks_are_not_normalized(tmp_path):
    path = tmp_path / "unicode.json"
    path.write_bytes(b'{"text":"e\\u0301 \\ud83d\\ude00"}')
    assert read_provenance_json(path) == {"text": "e\u0301 \U0001f600"}


def _observation():
    from backend.app.document.inspection_qd_kt_runtime_identity import OBSERVATION_METHOD, OBSERVATION_SCOPE
    from backend.app.document.inspection_qd_kt_runtime_provenance import load_runtime_source_evidence
    return {
        "schema_version": "qdkt-excel-observation/v1", "collector_id": "SYNTHETIC-NOT-AN-OPERATOR",
        "acquisition_method": OBSERVATION_METHOD, "inventory_scope": OBSERVATION_SCOPE,
        "capture_started_at": "2026-10-29T01:00:00+00:00", "capture_completed_at": "2026-10-29T01:00:01+00:00",
        "process": {"pid": 12345, "session_id": 1, "hwnd": "0x1234", "hwnd_pid": 12345,
                    "started_at": "2026-10-29T00:00:00+00:00", "started_at_after": "2026-10-29T00:00:00+00:00"},
        "loaded_addin": {"workbook_name": "GPs.xlam", "full_path": r"Z:\unavailable\GPs.xlam", "excel_version": "16.0", "excel_build": "12345"},
        "available_addins": [{"name": "GPs.xlam", "full_path": r"Z:\unavailable\GPs.xlam", "installed": True}],
        "excel_process_ids": [12345], "runtime_module_source_status": "NOT_COLLECTED",
        "on_disk": {"path": r"Z:\unavailable\GPs.xlam", "size_bytes": 1017208,
            "sha256": load_runtime_source_evidence()["artifact_inputs"]["addin"]["sha256"],
            "captured_at": "2026-10-29T01:00:02+00:00", "acquisition_method": "BOUNDED_OFFLINE_FILE_SNAPSHOT"},
    }


def test_mutually_consistent_forged_chain_cannot_authenticate_loaded_code(monkeypatch):
    from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation
    from tools import qdkt_runtime_observation as io
    def forbidden(*args, **kwargs): raise AssertionError("payload path was opened")
    monkeypatch.setattr(io, "_snapshot", forbidden)
    evidence = _observation()
    original = deepcopy(evidence)
    result = assess_runtime_observation(evidence)
    assert evidence == original
    assert result["reported_disk_matches_reviewed"] is True
    assert result["on_disk_category"] == "VERSION_BINDING_UNVERIFIED"
    assert result["collector_authenticated"] is result["runtime_identity_verified"] is result["ready_to_render"] is False
    assert result["in_memory_executed_vba_category"] == "RUNTIME_IDENTITY_UNVERIFIED"
    assert result["blocker"] == "UNVERIFIED_VERSION_BINDING"


@pytest.mark.parametrize("change", ["pid_bool", "hwnd_pid", "pid_reused", "naive", "reverse_time", "name_path", "dotdot", "ads", "installed_string", "duplicate_process", "missing_process", "duplicate_available", "method", "extra_approval", "disk_path", "disk_size_bool", "disk_hash", "source_status", "empty_hwnd"])
def test_observation_inconsistency_is_rejected_without_rescue(change):
    from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation, QdKtRuntimeIdentityBlocked
    data = _observation()
    if change == "pid_bool": data["process"]["pid"] = True
    elif change == "hwnd_pid": data["process"]["hwnd_pid"] = 999
    elif change == "pid_reused": data["process"]["started_at_after"] = "2026-10-29T00:01:00+00:00"
    elif change == "naive": data["capture_started_at"] = "2026-10-29T01:00:00"
    elif change == "reverse_time": data["capture_completed_at"] = "2026-10-29T00:59:00+00:00"
    elif change == "name_path": data["loaded_addin"]["full_path"] = r"Z:\unavailable\foreign.xlam"
    elif change == "dotdot": data["loaded_addin"]["full_path"] = r"Z:\unavailable\..\GPs.xlam"
    elif change == "ads": data["loaded_addin"]["full_path"] = r"Z:\unavailable:stream\GPs.xlam"
    elif change == "installed_string": data["available_addins"][0]["installed"] = "true"
    elif change == "duplicate_process": data["excel_process_ids"].append(12345)
    elif change == "missing_process": data["excel_process_ids"] = [999]
    elif change == "duplicate_available": data["available_addins"] *= 2
    elif change == "method": data["acquisition_method"] = "CACHED_FIXTURE"
    elif change == "extra_approval": data["runtime_identity_verified"] = True
    elif change == "disk_path": data["on_disk"]["path"] = r"Z:\other\GPs.xlam"
    elif change == "disk_size_bool": data["on_disk"]["size_bytes"] = True
    elif change == "disk_hash": data["on_disk"]["sha256"] = "invalid"
    elif change == "source_status": data["runtime_module_source_status"] = "VERIFIED"
    else: data["process"]["hwnd"] = "0x0"
    with pytest.raises(QdKtRuntimeIdentityBlocked):
        assess_runtime_observation(data)


@pytest.mark.parametrize("field", ["schema_version", "acquisition_method", "inventory_scope"])
def test_foreign_equality_object_cannot_claim_an_acquisition_method(field):
    from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation, QdKtRuntimeIdentityBlocked
    class Forged:
        def __eq__(self, other): return True
        def __ne__(self, other): return False
    data = _observation()
    data[field] = Forged()
    with pytest.raises(QdKtRuntimeIdentityBlocked):
        assess_runtime_observation(data)


def test_mismatched_disk_bytes_are_a_contradiction_not_runtime_execution_proof():
    from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation
    data = _observation()
    data["on_disk"]["sha256"] = "0" * 64
    result = assess_runtime_observation(data)
    assert result["reported_disk_matches_reviewed"] is False and result["on_disk_category"] == "CONTRADICTED"
    assert result["runtime_identity_verified"] is False and result["blocker"] == "UNVERIFIED_VERSION_BINDING"


def test_multiple_instances_available_flags_and_source_claims_do_not_authenticate():
    from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation
    data = _observation()
    data["excel_process_ids"].append(23456)
    data["available_addins"].append({"name": "GPs.xlam", "full_path": r"Z:\other\GPs.xlam", "installed": True})
    data["runtime_module_source_status"] = "OPERATOR_REPORTED_SOURCE_CAPTURE"
    data["on_disk"] = None
    result = assess_runtime_observation(data)
    assert result["multiple_excel_processes_reported"] and result["same_name_available_entries"] == 2
    assert result["on_disk_category"] == "EVIDENCE_UNAVAILABLE"
    assert result["runtime_identity_verified"] is result["all_loaded_instances_accounted_for"] is False


def test_process_creation_identity_does_not_lose_dotnet_100ns_precision():
    from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation, QdKtRuntimeIdentityBlocked
    data = _observation()
    data["process"]["started_at"] = "2026-10-29T00:00:00.0000001Z"
    data["process"]["started_at_after"] = "2026-10-29T00:00:00.0000002Z"
    with pytest.raises(QdKtRuntimeIdentityBlocked, match="SESSION_MISMATCH"):
        assess_runtime_observation(data)


def test_capture_order_does_not_lose_dotnet_100ns_precision():
    from backend.app.document.inspection_qd_kt_runtime_identity import assess_runtime_observation, QdKtRuntimeIdentityBlocked
    data = _observation()
    data["capture_started_at"] = "2026-10-29T01:00:00.0000002Z"
    data["capture_completed_at"] = "2026-10-29T01:00:00.0000001Z"
    with pytest.raises(QdKtRuntimeIdentityBlocked, match="TIME_INVALID"):
        assess_runtime_observation(data)


def test_observation_cli_does_not_invoke_fresh_vba_extraction(tmp_path, monkeypatch, capsys):
    from tools.audit_qdkt_source_transformations import main
    from tools import qdkt_runtime_source_verification as verifier
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(_observation()), encoding="utf-8")
    def forbidden(*args): raise AssertionError("observation is not fresh VBA extraction")
    monkeypatch.setattr(verifier, "verify_local_runtime_sources", forbidden)
    assert main(["--assess-runtime-observation", str(tmp_path), "capture.json"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert "local_artifact_verification" not in output
    assert output["runtime_observation_assessment"]["runtime_identity_verified"] is False


def test_payload_duplicate_keys_and_untrusted_paths_cannot_trigger_reacquisition(tmp_path):
    from tools.qdkt_runtime_observation import assess_observation_file
    path = tmp_path / "capture.json"
    path.write_text('{"collector_id":"first","collector_id":"second"}', encoding="utf-8")
    with pytest.raises(QdKtProvenanceGateBlocked, match="DUPLICATE_KEY"):
        assess_observation_file(str(tmp_path), "capture.json")


def test_same_filename_with_other_bytes_is_not_a_reviewed_runtime(tmp_path):
    from tools.qdkt_runtime_observation import observe_runtime_file
    (tmp_path / "GPs.xlam").write_bytes(b"synthetic foreign add-in bytes")
    result = observe_runtime_file(str(tmp_path), "GPs.xlam")
    assert result["size_bytes"] == len(b"synthetic foreign add-in bytes")
    assert result["on_disk_category"] == "CONTRADICTED" and result["matches_reviewed_addin_bytes"] is False
    assert result["runtime_identity_verified"] is False


def test_identity_evidence_preserves_original_pins_and_error_path_reachability(tmp_path):
    from backend.app.document.inspection_qd_kt_runtime_identity import load_runtime_identity_evidence, QdKtRuntimeIdentityBlocked
    from backend.app.document.inspection_qd_kt_runtime_provenance import RUNTIME_EVIDENCE_SHA256
    evidence = load_runtime_identity_evidence()
    assert evidence["encoding"]["source_capture_pin"] == RUNTIME_EVIDENCE_SHA256 == "b2cdf80607d44c4543fa0b90e78e9eecfc10c4ef3ebb8ebdecd5d7c32df279ea"
    tpl, team = evidence["encoding"]["procedures"]
    assert len(tpl["differences"]) == 9 and {r["case"] for r in tpl["differences"]} == {7, 8, 11, 12, 13}
    assert len(team["differences"]) == 1 and team["differences"][0]["reachability"] == "I2_REACHABLE_FAILURE_HANDLER_NOT_PROVEN_EXECUTED"
    assert all(bytes.fromhex(r["raw_hex"]).decode("cp1258") == r["cp1258_text"] and bytes.fromhex(r["raw_hex"]).decode("cp1252") == r["cp1252_text"] for p in (tpl, team) for r in p["differences"])
    evidence["global_blocker"] = "CLOSED"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(QdKtRuntimeIdentityBlocked, match="QDKT_IDENTITY_EVIDENCE_DRIFT"):
        load_runtime_identity_evidence(path)


def test_replacing_artifact_and_its_expected_metadata_does_not_replace_review_pin(monkeypatch):
    from hashlib import sha256
    from backend.app.document import inspection_qd_kt_runtime_provenance as runtime
    evidence = runtime.load_runtime_source_evidence()
    foreign = b"same-name foreign runtime project"
    evidence["artifact_inputs"]["addin"]["sha256"] = sha256(foreign).hexdigest()
    monkeypatch.setattr(runtime, "read_provenance_json", lambda _: evidence)
    with pytest.raises(runtime.QdKtRuntimeEvidenceBlocked, match="QDKT_RUNTIME_CAPTURE_DRIFT"):
        runtime.validate_runtime_artifact_snapshot("addin", foreign)


@pytest.mark.parametrize("kind,code", [("duplicate_modules", "QDKT_RUNTIME_MODULE_AMBIGUOUS"), ("two_projects", "QDKT_RUNTIME_PROJECT_AMBIGUOUS"), ("no_project", "QDKT_RUNTIME_PROJECT_AMBIGUOUS"), ("version", "QDKT_RUNTIME_EXTRACTOR_VERSION_UNREVIEWED")])
def test_extractor_defense_in_depth_does_not_choose_a_first_ambiguous_result(monkeypatch, kind, code):
    # Component-only fault injection. Foreign binary inputs cannot reach this
    # stage through the public verifier's unchanged byte pins.
    import sys
    import types
    import importlib.metadata
    from tools.qdkt_runtime_source_verification import _extract_addin
    from backend.app.document.inspection_qd_kt_runtime_provenance import QdKtRuntimeEvidenceBlocked
    state = {"created": False, "closed": False}
    class Parser:
        def __init__(self, *args, **kwargs):
            state["created"] = True
            projects = [] if kind == "no_project" else [("", "PROJECT", "VBA/dir")] * (2 if kind == "two_projects" else 1)
            self.ole_subfiles = [types.SimpleNamespace(ole_file=None, find_vba_projects=lambda: projects)]
        def extract_macros(self):
            return [(None, "VBA/WinAPI", "WinAPI.bas", "first"), (None, "VBA/WINAPI", "WINAPI.bas", "second")]
        def close(self): state["closed"] = True
    fake = types.ModuleType("oletools.olevba")
    fake.VBA_Parser = Parser
    fake.VBA_Project = lambda *a, **kw: types.SimpleNamespace(codepage=1252)
    monkeypatch.setitem(sys.modules, "oletools", types.ModuleType("oletools"))
    monkeypatch.setitem(sys.modules, "oletools.olevba", fake)
    monkeypatch.setattr(importlib.metadata, "version", lambda _: "unknown" if kind == "version" else "0.60.2")
    with pytest.raises(QdKtRuntimeEvidenceBlocked, match=code):
        _extract_addin(b"component fault injection; not primary evidence")
    if kind == "version": assert state["created"] is False
    else: assert state["created"] and state["closed"]
