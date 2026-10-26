"""Pin the two QĐKT dossier legacy inputs to the SAME db.ktra row.

This diagnostic certifies only observed VBA expressions/column adjacency.
No CaseApplication ownership, dossier identity or render permission follows.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

_PROVENANCE = Path(__file__).resolve().parents[3] / "artifacts/legacy_audit/inspection_qd_kt_input_provenance.json"
_ZIP_SHA = "6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7"
_ASSIGNMENT = (
    "s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value:"
    "    s_NgaynopHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra).Value"
)
_EXPECTED = {
    "HsDK": ("s_MaHsDk", "db.ktra row, ColDB_HSDK_Ktra + 1", 748, "s_MaHsDk"),
    "NgaynopHsDK": ("s_NgaynopHsDk", "db.ktra row, ColDB_HSDK_Ktra", 749, 'Replace(s_NgaynopHsDk, "-", "/")'),
}


@dataclass(frozen=True)
class QdKtDossierLegacyPair:
    same_legacy_row_proven: bool
    code_column_offset: int
    date_column_offset: int
    code_expression: str
    date_expression: str
    source_zip_sha256: str
    modern_owner_verified: bool = False
    ready_to_render: bool = False


def inspect_qdkt_dossier_legacy_pair(
    *, provenance_path: Path = _PROVENANCE,
) -> QdKtDossierLegacyPair:
    try:
        source = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
        if source["source_zip_sha256"] != _ZIP_SHA:
            raise ValueError("QDKT_DOSSIER_SOURCE_ZIP_DRIFT")
        fields = source["fields"]
        assignments = []
        for name, (variable, endpoint, line, expression) in _EXPECTED.items():
            row = fields[name]
            if row["owner_classification"] != "OWNER_PARTIAL" or row["source_semantic_endpoint"] != endpoint:
                raise ValueError("QDKT_DOSSIER_OWNER_OR_COLUMN_DRIFT")
            if row["source_variables"] != [variable]:
                raise ValueError("QDKT_DOSSIER_VARIABLE_DRIFT")
            chain = row["provenance_chain"]
            if len(chain) != 1 or chain[0]["variable"] != variable:
                raise ValueError("QDKT_DOSSIER_CHAIN_DRIFT")
            steps = chain[0]["steps"]
            if len(steps) != 1 or steps[0]["file"] != "RecordForm.frm" or steps[0]["line"] != 343:
                raise ValueError("QDKT_DOSSIER_ASSIGNMENT_LOCATION_DRIFT")
            assignments.append(steps[0]["code"])
            operations = [op for op in row["vba_rendered_operations"] if op["reachability_i2"] == "REACHABLE_I2"]
            if len(operations) != 1 or operations[0]["line"] != line or operations[0]["expression"] != expression or operations[0]["operation_type"] != "WRITE":
                raise ValueError("QDKT_DOSSIER_RENDER_EXPRESSION_DRIFT")
        if assignments != [_ASSIGNMENT, _ASSIGNMENT]:
            raise ValueError("QDKT_DOSSIER_SOURCE_PAIR_DRIFT")
        return QdKtDossierLegacyPair(
            same_legacy_row_proven=True,
            code_column_offset=1, date_column_offset=0,
            code_expression=_EXPECTED["HsDK"][3],
            date_expression=_EXPECTED["NgaynopHsDK"][3],
            source_zip_sha256=_ZIP_SHA,
        )
    except (OSError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("QDKT_DOSSIER_PROVENANCE_UNAVAILABLE") from exc
