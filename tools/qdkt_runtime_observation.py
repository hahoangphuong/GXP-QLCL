"""Bounded analyst IO; payload paths are never used to reopen a file."""
from hashlib import sha256
from pathlib import Path
from datetime import datetime, timezone

from backend.app.document.inspection_qd_kt_provenance_gate import parse_provenance_json_bytes
from backend.app.document.inspection_qd_kt_runtime_identity import (
    assess_runtime_observation, load_runtime_identity_evidence, QdKtRuntimeIdentityBlocked,
)
from backend.app.document.inspection_qd_kt_runtime_provenance import load_runtime_source_evidence
from tools._qdkt_evidence_io import read_evidence, EvidenceBlocked, JSON_LIMIT, FILE_LIMIT


def _snapshot(parent: str, relative: str, limit: int) -> tuple[Path, bytes]:
    root = Path(parent)
    if not root.is_absolute():
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_ROOT_INVALID")
    try:
        data = read_evidence(root, relative, limit)
    except EvidenceBlocked as exc:
        raise QdKtRuntimeIdentityBlocked("QDKT_OBSERVATION_FILE_UNAVAILABLE") from exc
    return root / relative, data


def assess_observation_file(parent: str, relative: str) -> dict:
    _, raw = _snapshot(parent, relative, JSON_LIMIT)
    return assess_runtime_observation(parse_provenance_json_bytes(raw))


def observe_runtime_file(parent: str, name: str) -> dict:
    if type(name) is not str or name.lower() != "gps.xlam":
        raise QdKtRuntimeIdentityBlocked("QDKT_RUNTIME_FILE_NAME_INVALID")
    path, data = _snapshot(parent, name, FILE_LIMIT)
    captured_at = datetime.now(timezone.utc).isoformat()  # acquisition metadata, never a business/issuance date
    digest = sha256(data).hexdigest()
    match = digest == load_runtime_source_evidence()["artifact_inputs"]["addin"]["sha256"] and len(data) == load_runtime_identity_evidence()["primary_addin_size_bytes"]
    return {"path": str(path), "size_bytes": len(data), "sha256": digest, "captured_at": captured_at,
        "acquisition_method": "BOUNDED_OFFLINE_FILE_SNAPSHOT",
        "evidence_scope": "ON_DISK_IMMUTABLE_SNAPSHOT_ONLY_NOT_EXCEL_MEMORY",
        "on_disk_category": "BYTE_IDENTITY_PROVEN" if match else "CONTRADICTED",
        "matches_reviewed_addin_bytes": match, "runtime_identity_verified": False,
        "blocker": "UNVERIFIED_VERSION_BINDING", "ready_to_render": False}
