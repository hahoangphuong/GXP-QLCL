"""Offline source-provenance gate for 14 logical QĐKT i=2 operations.

This module neither substitutes modern ORM columns nor enables Word rendering.
An OWNER_PARTIAL candidate is evidence to investigate, not a payload owner.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from hashlib import sha256
import json
import math

SOURCE = Path(__file__).resolve().parents[3] / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
TRACE = SOURCE.with_name("inspection_qd_kt_vba_trace.json")
SOURCE_ARCHIVE_SHA256 = "6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7"
INVENTORY_SEMANTIC_SHA256 = "17ed8cd21147a0ae4d860700444f5dc59a572acd7d32f18f78776aea600ea279"
TRACE_SEMANTIC_SHA256 = "83b652b4ece582416434700df9c987a33ed811c57d6b576dda2ad6065d731c8f"
# The legacy JSON calls these keys "physical_bookmark", but the values are
# logical VBA operation symbols. Some resolve to numbered Word bookmarks,
# others have no physical target in the four observed DOTX packages.
EXPECTED_FIELDS = frozenset({
    "Fulldate", "Tencoso", "Diadiem", "Diadiemx", "Diachicoso",
    "HsDK", "NgaynopHsDK", "QDKT", "NgayQDKT", "VKNx", "VKN",
    "TT3x", "TT3Del", "TTx",
})
EXPECTED_BLOCKED = frozenset({
    "Fulldate", "Diadiem", "Diadiemx", "Diachicoso",
    "QDKT", "NgayQDKT", "VKNx", "VKN",
})


# Pinned active i=2 operations from RecordForm.Tao_QDKT_KHKT_BBKT.
# These are provenance anchors, not an assertion that modern values are equivalent.
EXPECTED_I2_OPERATIONS = {
    "Fulldate": (743, "WRITE", "REACHABLE_I2"),
    "Tencoso": (744, "WRITE", "REACHABLE_I2"),
    "Diadiem": (745, "WRITE", "REACHABLE_I2"),
    "Diadiemx": (746, "WRITE", "REACHABLE_I2"),
    "Diachicoso": (747, "WRITE", "REACHABLE_I2"),
    "HsDK": (748, "WRITE", "REACHABLE_I2"),
    "NgaynopHsDK": (749, "WRITE", "REACHABLE_I2"),
    "QDKT": (790, "WRITE", "REACHABLE_I2"),
    "NgayQDKT": (790, "WRITE", "REACHABLE_I2"),
    "VKNx": (751, "WRITE", "CONDITIONAL_I2"),
    "VKN": (752, "WRITE", "CONDITIONAL_I2"),
    "TT3x": (765, "WRITE", "CONDITIONAL_I2"),
    "TT3Del": (766, "DELETE", "CONDITIONAL_I2"),
    "TTx": (757, "WRITE", "REACHABLE_I2"),
}


def _require_i2_trace(name: str, row: dict) -> None:
    """Reject missing or retagged active operations before source adjudication."""
    operations = row.get("vba_rendered_operations")
    if not isinstance(operations, list) or not operations:
        raise QdKtProvenanceGateBlocked("QDKT_I2_OPERATION_TRACE_CHANGED")
    active = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise QdKtProvenanceGateBlocked("QDKT_I2_OPERATION_TRACE_CHANGED")
        reachability = operation.get("reachability_i2")
        if type(reachability) is not str or reachability not in {"REACHABLE_I2", "CONDITIONAL_I2", "UNREACHABLE_I2"}:
            raise QdKtProvenanceGateBlocked("QDKT_I2_OPERATION_TRACE_CHANGED")
        if operation.get("physical_bookmark") != name:
            raise QdKtProvenanceGateBlocked("QDKT_I2_OPERATION_TRACE_CHANGED")
        if reachability != "UNREACHABLE_I2":
            active.append(operation)
    if len(active) != 1:
        raise QdKtProvenanceGateBlocked("QDKT_I2_OPERATION_TRACE_CHANGED")
    op = active[0]
    if (
        (op.get("line"), op.get("operation_type"), op.get("reachability_i2"))
        != EXPECTED_I2_OPERATIONS[name]
        or not isinstance(op.get("expression"), str)
        or (op["operation_type"] == "WRITE" and not op["expression"].strip())
        or not isinstance(op.get("branch_predicates"), str)
        or not op["branch_predicates"].strip()
    ):
        raise QdKtProvenanceGateBlocked("QDKT_I2_OPERATION_TRACE_CHANGED")
    variables = row.get("source_variables")
    chain = row.get("provenance_chain")
    if (
        not isinstance(variables, list) or not variables
        or not all(isinstance(v, str) and v.strip() for v in variables)
        or len(set(variables)) != len(variables)
        or not isinstance(chain, list) or not chain
        or not all(isinstance(entry, dict) and entry.get("variable") in variables
                   and isinstance(entry.get("steps"), list) and entry["steps"]
                   for entry in chain)
        or {entry["variable"] for entry in chain} != set(variables)
    ):
        raise QdKtProvenanceGateBlocked("QDKT_I2_SOURCE_CHAIN_INCOMPLETE")


class QdKtProvenanceGateBlocked(ValueError):
    pass


def semantic_sha256(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def parse_provenance_json_bytes(raw: bytes) -> dict:
    """Decode one bounded immutable snapshot without normalization or re-open."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise QdKtProvenanceGateBlocked("QDKT_SOURCE_JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    def invalid_constant(_):
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_PROVENANCE_INCOMPLETE")
    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise QdKtProvenanceGateBlocked("QDKT_SOURCE_PROVENANCE_INCOMPLETE")
        return value
    def require_utf8(value):
        if isinstance(value, str):
            value.encode("utf-8")
        elif isinstance(value, dict):
            for key, item in value.items():
                require_utf8(key)
                require_utf8(item)
        elif isinstance(value, list):
            for item in value:
                require_utf8(item)
    try:
        if type(raw) is not bytes or len(raw) > 2 * 1024 * 1024:
            raise ValueError("size")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant, parse_float=finite_float)
        if type(value) is not dict:
            raise ValueError("object")
        require_utf8(value)
        return value
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, QdKtProvenanceGateBlocked):
            raise
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_PROVENANCE_INCOMPLETE") from exc


def read_provenance_json(path: Path) -> dict:
    """Bounded single acquisition; reject duplicates, nonfinite and invalid UTF-8."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
    except OSError as exc:
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_PROVENANCE_INCOMPLETE") from exc
    return parse_provenance_json_bytes(raw)


@dataclass(frozen=True)
class QdKtProvenanceGate:
    source_sha256: str
    blocked_fields: tuple[str, ...]
    partial_fields: tuple[str, ...]
    proven_fields: tuple[str, ...]
    ready_for_typed_payload: bool = False


_TRACE_OPERATION_KEYS = (
    "physical_bookmark", "physical_bookmark_expression", "operation_type",
    "line", "expression", "branch_predicates", "reachability_i2",
)


def _require_independent_trace_match(evidence: dict, fields: dict, trace_path: Path) -> None:
    """Reconcile the owner inventory with the separately captured VBA operation trace."""
    try:
        trace = read_provenance_json(trace_path)
    except (OSError, ValueError, TypeError) as exc:
        raise QdKtProvenanceGateBlocked("QDKT_VBA_TRACE_UNVERIFIED") from exc
    if (
        not isinstance(trace, dict)
        or trace.get("schema_version") != "inspection-qd-kt-vba-trace/v2"
        or trace.get("source_zip_sha256") != evidence.get("source_zip_sha256")
        or trace.get("call_chain") != evidence.get("call_chain")
        or evidence.get("trace_artifact") != "artifacts/legacy_audit/inspection_qd_kt_vba_trace.json"
    ):
        raise QdKtProvenanceGateBlocked("QDKT_VBA_TRACE_MISMATCH")
    ops = trace.get("physical_bookmark_operations")
    if not isinstance(ops, list) or any(not isinstance(item, dict) for item in ops):
        raise QdKtProvenanceGateBlocked("QDKT_VBA_TRACE_MISMATCH")
    for name, row in fields.items():
        expected = [
            tuple(operation.get(key) for key in _TRACE_OPERATION_KEYS)
            for operation in ops if operation.get("physical_bookmark") == name
        ]
        actual = [
            tuple(operation.get(key) for key in _TRACE_OPERATION_KEYS)
            for operation in row["vba_rendered_operations"]
        ]
        if not expected or actual != expected:
            raise QdKtProvenanceGateBlocked("QDKT_VBA_TRACE_MISMATCH")
    if semantic_sha256(trace) != TRACE_SEMANTIC_SHA256:
        raise QdKtProvenanceGateBlocked("QDKT_VBA_TRACE_MISMATCH")


def load_qdkt_source_provenance(path: Path = SOURCE) -> dict:
    """Check a pinned source-trace inventory, never infer owner equivalence.

    Source changes require a separately reviewed source/Word contract,
    never a silent status promotion from a new modern column.
    """
    evidence = read_provenance_json(path)
    fields = evidence.get("fields")
    if evidence.get("schema_version") != "inspection-qd-kt-input-provenance/v1":
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_SCHEMA_UNEXPECTED")
    if not isinstance(fields, dict) or set(fields) != EXPECTED_FIELDS:
        # Preserve the historical machine-readable blocker code for clients,
        # despite the legacy operation-symbol naming convention.
        raise QdKtProvenanceGateBlocked("QDKT_PHYSICAL_BOOKMARK_SET_CHANGED")
    digest = evidence.get("source_zip_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_ZIP_PIN_MISSING")
    if digest != SOURCE_ARCHIVE_SHA256:
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_ZIP_PIN_MISMATCH")
    if any(not isinstance(row, dict) for row in fields.values()):
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_PROVENANCE_INCOMPLETE")
    for name, row in fields.items():
        _require_i2_trace(name, row)
    _require_independent_trace_match(evidence, fields, TRACE)
    status = {name: row.get("owner_classification") for name, row in fields.items()}
    if any(type(value) is not str for value in status.values()):
        raise QdKtProvenanceGateBlocked("QDKT_OWNER_STATUS_REQUIRES_REVIEW")
    if any(
        not isinstance(fields[name], dict)
        or fields[name].get("physical_bookmark") != name
        or not fields[name].get("source_semantic_endpoint")
        or not fields[name].get("blocker")
        for name in EXPECTED_FIELDS
    ):
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_PROVENANCE_INCOMPLETE")
    if {name for name, value in status.items() if value == "OWNER_BLOCKED"} != EXPECTED_BLOCKED:
        raise QdKtProvenanceGateBlocked("QDKT_OWNER_STATUS_REQUIRES_REVIEW")
    counts = Counter(status.values())
    if counts != {"OWNER_BLOCKED": 8, "OWNER_PARTIAL": 6}:
        raise QdKtProvenanceGateBlocked("QDKT_OWNER_STATUS_REQUIRES_REVIEW")
    # Operations alone cannot authenticate assignment/format/owner metadata.
    # Pin the entire reviewed semantic inventory, independent of JSON spacing.
    if semantic_sha256(evidence) != INVENTORY_SEMANTIC_SHA256:
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_METADATA_DRIFT")
    return evidence


def inspect_qdkt_source_provenance(path: Path = SOURCE) -> QdKtProvenanceGate:
    evidence = load_qdkt_source_provenance(path)
    # This gate intentionally cannot return ready=True: even changing all 14
    # statuses requires an independently specified typed/render acceptance path.
    return QdKtProvenanceGate(
        source_sha256=evidence["source_zip_sha256"],
        blocked_fields=tuple(sorted(EXPECTED_BLOCKED)),
        partial_fields=tuple(sorted(EXPECTED_FIELDS - EXPECTED_BLOCKED)),
        proven_fields=(),
    )
