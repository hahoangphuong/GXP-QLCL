"""Read-only runtime evidence contract; source equality never authorizes Word."""
from hashlib import sha256
from pathlib import Path

from backend.app.document.inspection_qd_kt_provenance_gate import read_provenance_json, semantic_sha256

RUNTIME_EVIDENCE = Path(__file__).resolve().parents[3] / "tests/fixtures/inspection_qd_kt_runtime_source_evidence.json"
RUNTIME_EVIDENCE_SHA256 = "b2cdf80607d44c4543fa0b90e78e9eecfc10c4ef3ebb8ebdecd5d7c32df279ea"
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024


class QdKtRuntimeEvidenceBlocked(ValueError):
    pass


def normalized_source(text: str) -> str:
    if type(text) is not str:
        raise QdKtRuntimeEvidenceBlocked("QDKT_SOURCE_TEXT_INVALID")
    # Do not trim, case-fold, NFC/NFD-normalize or remove punctuation/attributes.
    return text.replace("\r\n", "\n").replace("\r", "\n")


def compare_source_text(left: str, right: str) -> dict:
    a, b = normalized_source(left), normalized_source(right)
    return {
        "left_utf8_lf_sha256": sha256(a.encode("utf-8")).hexdigest(),
        "right_utf8_lf_sha256": sha256(b.encode("utf-8")).hexdigest(),
        "comparison": "CONTENT_EQUIVALENT_VERSION_UNPROVEN" if a == b else "IMPLEMENTATION_DIFFERS",
        "version_binding_verified": False,
    }


def load_runtime_source_evidence(path: Path = RUNTIME_EVIDENCE) -> dict:
    evidence = read_provenance_json(path)
    if semantic_sha256(evidence) != RUNTIME_EVIDENCE_SHA256:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_CAPTURE_DRIFT")
    return evidence


def validate_runtime_artifact_snapshot(key: str, data: bytes) -> bytes:
    expected = load_runtime_source_evidence()["artifact_inputs"]
    if type(key) is not str or key not in expected:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ARTIFACT_SET_INCOMPLETE")
    if type(data) is not bytes or len(data) > MAX_ARTIFACT_BYTES or sha256(data).hexdigest() != expected[key]["sha256"]:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ARTIFACT_BYTES_MISMATCH")
    return data


def validate_runtime_artifact_bytes(artifacts: dict[str, bytes]) -> dict[str, bytes]:
    """Acquire elsewhere, verify actual immutable bytes here before extraction.

    The capture pin is a review anchor, not independent acquisition attestation.
    No caller-supplied checksum or matching metadata can replace actual bytes.
    """
    expected = load_runtime_source_evidence()["artifact_inputs"]
    if type(artifacts) is not dict or any(type(key) is not str for key in artifacts) or set(artifacts) != set(expected):
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_ARTIFACT_SET_INCOMPLETE")
    result = {}
    for key in expected:
        result[key] = validate_runtime_artifact_snapshot(key, artifacts[key])
    return result


def validate_runtime_capture(capture: dict) -> None:
    if semantic_sha256(capture) != RUNTIME_EVIDENCE_SHA256:
        raise QdKtRuntimeEvidenceBlocked("QDKT_RUNTIME_EXTRACTION_MISMATCH")
