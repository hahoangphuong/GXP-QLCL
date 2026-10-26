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
