"""Offline source-provenance gate for the 14 physical QĐKT i=2 bookmarks.

This module neither substitutes modern ORM columns nor enables Word rendering.
An OWNER_PARTIAL candidate is evidence to investigate, not a payload owner.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import json

SOURCE = Path(__file__).resolve().parents[3] / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
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
        if reachability not in {"REACHABLE_I2", "CONDITIONAL_I2", "UNREACHABLE_I2"}:
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
        or not op["expression"].strip()
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


@dataclass(frozen=True)
class QdKtProvenanceGate:
    source_sha256: str
    blocked_fields: tuple[str, ...]
    partial_fields: tuple[str, ...]
    proven_fields: tuple[str, ...]
    ready_for_typed_payload: bool = False


def inspect_qdkt_source_provenance(path: Path = SOURCE) -> QdKtProvenanceGate:
    """Check a pinned source-trace inventory, never infer owner equivalence.

    Source changes require a separately reviewed source/Word contract,
    never a silent status promotion from a new modern column.
    """
    evidence = json.loads(Path(path).read_text(encoding="utf-8"))
    fields = evidence.get("fields")
    if evidence.get("schema_version") != "inspection-qd-kt-input-provenance/v1":
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_SCHEMA_UNEXPECTED")
    if not isinstance(fields, dict) or set(fields) != EXPECTED_FIELDS:
        raise QdKtProvenanceGateBlocked("QDKT_PHYSICAL_BOOKMARK_SET_CHANGED")
    digest = evidence.get("source_zip_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_ZIP_PIN_MISSING")
    if any(not isinstance(row, dict) for row in fields.values()):
        raise QdKtProvenanceGateBlocked("QDKT_SOURCE_PROVENANCE_INCOMPLETE")
    for name, row in fields.items():
        _require_i2_trace(name, row)
    status = {name: row.get("owner_classification") for name, row in fields.items()}
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
    # This gate intentionally cannot return ready=True: even changing all 14
    # statuses requires an independently specified typed/render acceptance path.
    return QdKtProvenanceGate(
        source_sha256=digest,
        blocked_fields=tuple(sorted(EXPECTED_BLOCKED)),
        partial_fields=tuple(sorted(EXPECTED_FIELDS - EXPECTED_BLOCKED)),
        proven_fields=(),
    )
