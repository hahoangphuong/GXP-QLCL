"""Fail-closed, offline QĐKT legacy-to-canonical identity evidence assessment.

Candidate ORM field names are not evidence of identity, field equivalence, or
permission to render. No database, service, or storage access.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

_ROOT = Path(__file__).resolve().parents[3]
_SOURCE = _ROOT / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
_EXPECTED = {
    "HsDK": ("CaseApplication.dossier_code", "db.ktra row, ColDB_HSDK_Ktra + 1"),
    "NgaynopHsDK": ("CaseApplication.submitted_on", "db.ktra row, ColDB_HSDK_Ktra"),
    "Tencoso": ("Site.site_name", "planning row cell 4; fallback/alternate db_cso site row"),
}


@dataclass(frozen=True)
class QdKtIdentityEvidenceResult:
    logical_name: str
    modern_candidate: str
    legacy_source: str
    legacy_row_identity_verified: bool = False
    canonical_case_identity_verified: bool = False
    record_selection_rule_verified: bool = False
    value_semantics_verified: bool = False
    modern_owner_verified: bool = False
    ready_to_render: bool = False


def inspect_qdkt_cross_system_identity(
    *, provenance_path: Path = _SOURCE,
    proposed_mapping: Mapping[str, str] | None = None,
) -> tuple[QdKtIdentityEvidenceResult, ...]:
    """Validate pinned candidate labels, but NEVER authorize an ORM mapping.

    proposed_mapping can be supplied for offline diagnostic comparison only.
    Its presence or equality does not establish row identity or value parity.
    """
    try:
        data = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
        fields = data["fields"]
        results = []
        for name, (candidate, source) in _EXPECTED.items():
            row = fields[name]
            if (
                row["owner_classification"] != "OWNER_PARTIAL"
                or row["modern_owner_candidate"] != candidate
                or row["source_semantic_endpoint"] != source
                or not row["blocker"]
            ):
                raise ValueError("QDKT_CROSS_SYSTEM_SOURCE_OR_OWNER_DRIFT")
            results.append(QdKtIdentityEvidenceResult(
                logical_name=name, modern_candidate=candidate, legacy_source=source,
            ))
        if proposed_mapping is not None:
            if not isinstance(proposed_mapping, Mapping) or set(proposed_mapping) != set(_EXPECTED):
                raise ValueError("QDKT_CROSS_SYSTEM_MAPPING_INCOMPLETE")
            if any(
                not isinstance(value, str) or not value.strip()
                for value in proposed_mapping.values()
            ):
                raise ValueError("QDKT_CROSS_SYSTEM_MAPPING_INVALID")
        return tuple(results)
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("QDKT_CROSS_SYSTEM_PROVENANCE_UNAVAILABLE") from exc
