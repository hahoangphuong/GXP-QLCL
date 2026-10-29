"""Unsigned observations diagnose runtime identity; they never authenticate it."""
from datetime import datetime
from pathlib import Path
import re

from backend.app.document.inspection_qd_kt_provenance_gate import read_provenance_json, semantic_sha256
from backend.app.document.inspection_qd_kt_runtime_provenance import load_runtime_source_evidence

IDENTITY_EVIDENCE = Path(__file__).resolve().parents[3] / "tests/fixtures/inspection_qd_kt_runtime_identity_evidence.json"
IDENTITY_EVIDENCE_SHA256 = "44fbef547678e1359eea7fb51db037d2bb0ac73ef97ded86e2c606d778025251"
OBSERVATION_METHOD = "AUTHORIZED_OPERATOR_READ_ONLY_EXISTING_EXCEL_COM"
OBSERVATION_SCOPE = "TARGET_ROT_INSTANCE_AVAILABLE_ADDINS_NOT_EXHAUSTIVE_LOADED_CODE"


class QdKtRuntimeIdentityBlocked(ValueError):
    pass


def load_runtime_identity_evidence(path: Path = IDENTITY_EVIDENCE) -> dict:
    data = read_provenance_json(path)
    if semantic_sha256(data) != IDENTITY_EVIDENCE_SHA256:
        raise QdKtRuntimeIdentityBlocked("QDKT_IDENTITY_EVIDENCE_DRIFT")
    return data


def runtime_identity_chain() -> dict:
    evidence = load_runtime_identity_evidence()
    capture = load_runtime_source_evidence()
    return {
        "evidence_class": "PINNED_STATIC_CAPTURE_NOT_LIVE_EXCEL_ATTESTATION",
        "identity_evidence_pin": IDENTITY_EVIDENCE_SHA256,
        "stages": [
            {"stage": "PRIMARY_SUPPLIED_ADDIN", "category": "BYTE_IDENTITY_PROVEN",
             "scope": "supplied snapshot only; not current Excel-loaded or executed bytes",
             "sha256": capture["artifact_inputs"]["addin"]["sha256"],
             "source_modules": capture["addin_modules_utf8_lf_sha256"]},
            {"stage": "REVIEWED_EXPORT_SET", "category": "ENCODING_AMBIGUOUS",
             "source_equivalence_category": "SOURCE_EQUIVALENCE_PROVEN",
             "scope": "14 writer lines and 9 whole procedures after LF-only normalization; not version identity",
             "missing": "WinAPI export, export encoding attestation, source-to-build mapping"},
            {"stage": "BUILD_AND_DISTRIBUTION", "category": "VERSION_BINDING_UNVERIFIED",
             "manifest_evidence": "EVIDENCE_UNAVAILABLE", "scope": evidence["build_distribution_survey"]["limitation"]},
            {"stage": "EXCEL_LOADED_RUNTIME", "category": "RUNTIME_IDENTITY_UNVERIFIED",
             "scope": "no independently authenticated live-session identity; loader can reuse same-name workbook without a hash check"},
        ],
        "encoding": evidence["encoding"], "loader": evidence["loader"],
        "build_distribution_survey": evidence["build_distribution_survey"],
        "blocker": "UNVERIFIED_VERSION_BINDING", "runtime_identity_verified": False,
        "decision": "UNDECIDED", "word_uat": "NOT_EXECUTED", "ready_to_render": False,
    }


def _fields(value, required):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != set(required):
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_FIELDS_INVALID")


def _text(value, limit=4096):
    if type(value) is not str or not value.strip() or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_TEXT_INVALID")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_TEXT_INVALID") from exc
    return value


def _time(value):
    try:
        text = _text(value, 64)
        matched = re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.([0-9]{1,7}))?(?:Z|[+-][0-9]{2}:[0-9]{2})", text)
        if not matched:
            raise ValueError("ISO observation timestamp")
        result = datetime.fromisoformat(text)
        if result.utcoffset() is None:
            raise ValueError("offset")
        # Preserve .NET's seventh fractional digit for metadata ordering.
        # Explicit offsets apply to acquisition context, never a business date.
        return result.replace(microsecond=0), int((matched.group(1) or "0").ljust(7, "0"))
    except ValueError as exc:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_TIME_INVALID") from exc


def _integer(value, minimum=1):
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_PROCESS_INVALID")
    return value


def _windows_path(value):
    value = _text(value)
    if not re.match(r"(?:[A-Za-z]:\\|\\\\[^\\]+\\[^\\]+\\)", value) or "/" in value or ":" in value[2:] or any(p in (".", "..") for p in value.split("\\")):
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_PATH_INVALID")
    return value


def assess_runtime_observation(observation: dict) -> dict:
    """Validate internal consistency only, never author identity/role/signature.

    PID/time/path/hash claims may all be mutually consistent yet fabricated.
    No input field can promote executed-code or build identity. No path in the
    payload is opened, normalized, resolved or used to reacquire another file.
    """
    _fields(observation, ("schema_version", "collector_id", "acquisition_method", "capture_started_at", "capture_completed_at",
                          "process", "loaded_addin", "available_addins", "excel_process_ids", "inventory_scope", "on_disk", "runtime_module_source_status"))
    if any(type(observation[key]) is not str for key in ("schema_version", "acquisition_method", "inventory_scope")) or observation["schema_version"] != "qdkt-excel-observation/v1" or observation["acquisition_method"] != OBSERVATION_METHOD or observation["inventory_scope"] != OBSERVATION_SCOPE:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_METHOD_UNSUPPORTED")
    _text(observation["collector_id"], 128)
    if type(observation["runtime_module_source_status"]) is not str or observation["runtime_module_source_status"] not in ("NOT_COLLECTED", "ACCESS_DENIED", "OPERATOR_REPORTED_SOURCE_CAPTURE"):
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_METHOD_UNSUPPORTED")
    start, end = _time(observation["capture_started_at"]), _time(observation["capture_completed_at"])
    process = observation["process"]
    _fields(process, ("pid", "started_at", "started_at_after", "session_id", "hwnd", "hwnd_pid"))
    pid = _integer(process["pid"])
    _integer(process["session_id"], 0)
    _time(process["started_at"])
    _time(process["started_at_after"])
    # .NET 'o' creation stamps carry 100ns digits; datetime comparison would
    # truncate them to microseconds and hide a changed session observation.
    if _integer(process["hwnd_pid"]) != pid or process["started_at"] != process["started_at_after"]:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_SESSION_MISMATCH")
    if end < start or _time(process["started_at"]) > start:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_TIME_INVALID")
    if type(process["hwnd"]) is not str or not re.fullmatch(r"0x[0-9a-fA-F]{1,16}", process["hwnd"]) or int(process["hwnd"], 16) == 0:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_PROCESS_INVALID")
    ids = observation["excel_process_ids"]
    if type(ids) is not list or not 1 <= len(ids) <= 1024:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_INVENTORY_INVALID")
    for value in ids:
        _integer(value)
    if len(set(ids)) != len(ids) or pid not in ids:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_INVENTORY_INVALID")
    loaded = observation["loaded_addin"]
    _fields(loaded, ("workbook_name", "full_path", "excel_version", "excel_build"))
    name = _text(loaded["workbook_name"], 255)
    path = _windows_path(loaded["full_path"])
    if name.lower() != "gps.xlam" or path.rsplit("\\", 1)[-1] != name:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_NAME_PATH_MISMATCH")
    _text(loaded["excel_version"], 128)
    _text(loaded["excel_build"], 128)
    available = observation["available_addins"]
    if type(available) is not list or len(available) > 1024:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_INVENTORY_INVALID")
    for row in available:
        _fields(row, ("name", "full_path", "installed"))
        if _text(row["name"], 255).lower() != "gps.xlam" or type(row["installed"]) is not bool:
            raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_INVENTORY_INVALID")
        if _windows_path(row["full_path"]).rsplit("\\", 1)[-1] != row["name"]:
            raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_NAME_PATH_MISMATCH")
    if len({row["full_path"] for row in available}) != len(available):
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_INVENTORY_INVALID")
    disk = observation["on_disk"]
    match, disk_category = None, "EVIDENCE_UNAVAILABLE"
    if disk is not None:
        _fields(disk, ("path", "size_bytes", "sha256", "captured_at", "acquisition_method"))
        if _windows_path(disk["path"]) != path:
            raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_DISK_PATH_MISMATCH")
        _integer(disk["size_bytes"], 0)
        _time(disk["captured_at"])
        if type(disk["acquisition_method"]) is not str or disk["acquisition_method"] != "BOUNDED_OFFLINE_FILE_SNAPSHOT" or type(disk["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", disk["sha256"]):
            raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_DISK_INVALID")
        capture = load_runtime_source_evidence()
        identity = load_runtime_identity_evidence()
        match = disk["sha256"] == capture["artifact_inputs"]["addin"]["sha256"] and disk["size_bytes"] == identity["primary_addin_size_bytes"]
        disk_category = "VERSION_BINDING_UNVERIFIED" if match else "CONTRADICTED"
    return {
        "observation_trust": "UNAUTHENTICATED_OPERATOR_CLAIMS_INTERNAL_CONSISTENCY_ONLY",
        "collector_authenticated": False, "reported_loaded_path": path,
        "on_disk_category": disk_category, "reported_disk_matches_reviewed": match,
        "in_memory_executed_vba_category": "RUNTIME_IDENTITY_UNVERIFIED",
        "same_name_available_entries": len(available), "all_loaded_instances_accounted_for": False,
        "multiple_excel_processes_reported": len(ids) > 1,
        "source_identity_scope": "PINNED_REVIEWED_SOURCE_CAPTURE_NOT_OBSERVED_MEMORY",
        "reported_runtime_module_source_status": observation["runtime_module_source_status"],
        "blocker": "UNVERIFIED_VERSION_BINDING", "runtime_identity_verified": False,
        "ready_to_render": False, "legal_equivalence_verified": False,
    }
