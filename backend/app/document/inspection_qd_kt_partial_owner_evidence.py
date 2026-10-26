"""Read-only evidence projection for QĐKT's six partially owned inputs.

Physical target parity must never silently become business-source ownership.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from backend.app.document.inspection_qd_kt_vba_bookmark_series import reconcile_qdkt_i2_bookmarks

_ROOT = Path(__file__).resolve().parents[3]
_PROVENANCE = _ROOT / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
_OBSERVED = _ROOT / "tests/fixtures/inspection_qd_kt_observed_template_binaries.json"
_PARTIAL = frozenset({"Tencoso", "HsDK", "NgaynopHsDK", "TT3x", "TT3Del", "TTx"})
_EXACT_SOURCE_TARGETS = {"HsDK": (748, "s_MaHsDk"), "NgaynopHsDK": (749, 'Replace(s_NgaynopHsDk, "-", "/")')}


@dataclass(frozen=True)
class QdKtPartialOwnerEvidence:
    logical_name: str
    gxp_type: str
    source_semantic_endpoint: str
    blocker: str
    target_names: tuple[str, ...]
    target_resolution_proven: bool
    candidate_target_names: tuple[str, ...] = ()
    owner_classification: str = "OWNER_PARTIAL"
    source_owner_verified: bool = False
    ready_to_render: bool = False


def inspect_qdkt_partial_owner_evidence(
    gxp_type: str, *, provenance_path: Path = _PROVENANCE,
    observation_path: Path = _OBSERVED,
) -> tuple[QdKtPartialOwnerEvidence, ...]:
    """Project verified target names beside unresolved source ownership."""
    try:
        provenance = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
        observed = json.loads(Path(observation_path).read_text(encoding="utf-8"))
        fields = provenance["fields"]
        rows = observed["templates"]
        if set(fields) != _PARTIAL | {
            "Fulldate", "Diadiem", "Diadiemx", "Diachicoso",
            "QDKT", "NgayQDKT", "VKNx", "VKN",
        }:
            raise ValueError("QDKT_PARTIAL_SOURCE_INVENTORY_DRIFT")
        if {row["gxp_type"] for row in rows} != {"GLP", "GMP", "GMPbb", "GSP"} or len(rows) != 4:
            raise ValueError("QDKT_PARTIAL_TEMPLATE_INVENTORY_DRIFT")
        row = next(row for row in rows if row["gxp_type"] == gxp_type)
        if row["ready_to_render"] is not False or row["bookmark_owner_parity_verified"] is not False:
            raise ValueError("QDKT_PARTIAL_TEMPLATE_PROMOTED")
        targets = reconcile_qdkt_i2_bookmarks(gxp_type, row["bookmark_names"])
        results = []
        for name in sorted(_PARTIAL):
            field = fields[name]
            if field["owner_classification"] != "OWNER_PARTIAL" or not field["blocker"] or not field["source_semantic_endpoint"]:
                raise ValueError("QDKT_PARTIAL_OWNER_PREMATURELY_PROMOTED")
            if not any(op["reachability_i2"] in {"REACHABLE_I2", "CONDITIONAL_I2"} for op in field["vba_rendered_operations"]):
                raise ValueError("QDKT_PARTIAL_I2_PROVENANCE_UNVERIFIED")
            resolution = targets.get(name)
            if name in _EXACT_SOURCE_TARGETS:
                # The captured i=2 VBA uses exact unnumbered names, not
                # the numbered family. A missing physical target is a
                # source-proven no-op, not an unknown target mapping.
                expected_line, expected_expression = _EXACT_SOURCE_TARGETS[name]
                active = [
                    op for op in field["vba_rendered_operations"]
                    if op["reachability_i2"] == "REACHABLE_I2"
                ]
                if len(active) != 1 or active[0]["line"] != expected_line or active[0]["expression"] != expected_expression:
                    raise ValueError("QDKT_PARTIAL_EXACT_SOURCE_DRIFT")
                candidates = (name,)
                physical = set(row["bookmark_names"])
                effective = tuple(target for target in candidates if target in physical)
                proven = True
            else:
                candidates = resolution.candidate_targets if resolution else ()
                effective = resolution.effective_targets if resolution else ()
                proven = resolution is not None
            results.append(QdKtPartialOwnerEvidence(
                logical_name=name, gxp_type=gxp_type,
                source_semantic_endpoint=field["source_semantic_endpoint"],
                blocker=field["blocker"],
                target_names=effective,
                target_resolution_proven=proven,
                candidate_target_names=candidates,
            ))
        return tuple(results)
    except (OSError, KeyError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        raise ValueError("QDKT_PARTIAL_OWNER_EVIDENCE_UNAVAILABLE") from exc
