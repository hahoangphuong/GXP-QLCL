"""Fail-closed physical-source manifest for an explicitly approved cutover."""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Any, Mapping
from backend.app.domain.legacy_snapshot_v2 import CANONICAL_WORKBOOK_FILENAME, EXPECTED_SHEET_INVENTORY, EXTRACTOR_VERSION, PROVEN_RELATIONSHIPS, SCHEMA_VERSION, _sheet_classification

MANIFEST_SCHEMA_VERSION = "gxp-cutover-legacy-source-manifest/v1"
SNAPSHOT_CONTRACT = {"raw_source_view":"AUTHORITATIVE_READER_OBSERVED_COORDINATES_ONLY","semantic_tabular_view":"NOT_CREATED_IN_BATCH_A","no_inference_rule":"AUTHORITATIVE_WORKBOOK_DATA_MUST_BE_USED;_FALLBACK_REQUIRES_SOURCE_ABSENCE,_EXPLICIT_APPROVAL,_AND_FIELD_REGISTRY_RECORD."}

def manifest_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

def _digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value): raise ValueError(f"cutover manifest {label} is invalid")

def build_manifest(*, workbook_bytes: bytes, snapshot_bytes: bytes, expected_workbook_sha256: str, expected_snapshot_sha256: str, declared_frozen: bool) -> dict[str, Any]:
    _sha(expected_workbook_sha256,"workbook SHA256"); _sha(expected_snapshot_sha256,"snapshot SHA256")
    if sha256(workbook_bytes).hexdigest()!=expected_workbook_sha256 or sha256(snapshot_bytes).hexdigest()!=expected_snapshot_sha256: raise ValueError("cutover manifest raw source SHA differs")
    snapshot=json.loads(snapshot_bytes)
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("cutover manifest snapshot provenance differs")
    workbook = snapshot.get("workbook")
    if not isinstance(workbook, Mapping) or any((workbook.get("canonical_filename")!=CANONICAL_WORKBOOK_FILENAME,workbook.get("sha256")!=expected_workbook_sha256,workbook.get("extractor_version")!=EXTRACTOR_VERSION,workbook.get("total_sheet_count")!=len(EXPECTED_SHEET_INVENTORY),workbook.get("sheet_inventory")!=list(EXPECTED_SHEET_INVENTORY),workbook.get("semantic_output_deterministic") is not True)):
        raise ValueError("cutover manifest workbook provenance differs")
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, list) or tuple(item.get("sheet_name") for item in sheets) != EXPECTED_SHEET_INVENTORY:
        raise ValueError("cutover manifest sheet inventory differs")
    entries=[]
    for ordinal, sheet in enumerate(sheets, 1):
        rows=sheet.get("raw_rows")
        width=max((cell.get("column_ordinal",0) for row in rows for cell in row.get("cells",[])),default=0) if isinstance(rows,list) else -1
        populated=sum(cell.get("raw_state")!="NULL" and cell.get("raw_value")!="" for row in rows for cell in row.get("cells",[])) if isinstance(rows,list) else -1
        inventory={"row_count":len(rows) if isinstance(rows,list) else -1,"column_count":width,"cell_coordinate_count":sum(len(row.get("cells",[])) for row in rows) if isinstance(rows,list) else -1}
        if not isinstance(rows,list) or any((sheet.get("sheet_ordinal")!=ordinal,sheet.get("classification")!=_sheet_classification(sheet.get("sheet_name")),sheet.get("used_row_count")!=len(rows),sheet.get("used_column_count")!=width,sheet.get("raw_row_count")!=len(rows),sheet.get("populated_cell_count")!=populated,sheet.get("raw_coordinate_inventory")!=inventory,sheet.get("content_sha256")!=_digest(rows))):
            raise ValueError("cutover manifest sheet content differs")
        universe=sorted(row.get("source_row_number") for row in rows)
        if any(not isinstance(value,int) for value in universe) or len(set(universe))!=len(universe): raise ValueError("cutover manifest row universe is invalid")
        entries.append({key:sheet.get(key) for key in ("sheet_name","classification","used_row_count","used_column_count","raw_row_count","populated_cell_count","content_sha256","raw_coordinate_inventory")} | {"sheet_ordinal":ordinal,"row_number_universe_sha256":_digest(universe)})
    if snapshot.get("relationships") != [{"source_sheet":a,"source_field":b,"target_sheet":c,"target_field":d,"cardinality":"UNRESOLVED","evidence":"EXACT_AUTHORITATIVE_WORKBOOK_FIELD_NAMES","status":"PROVEN_FIELD_REFERENCE"} for a,b,c,d in PROVEN_RELATIONSHIPS]:
        raise ValueError("cutover manifest relationship contract differs")
    if snapshot.get("contract") != SNAPSHOT_CONTRACT:
        raise ValueError("cutover manifest snapshot contract differs")
    value={"artifact_kind":"gxp_cutover_legacy_source_manifest","schema_version":MANIFEST_SCHEMA_VERSION,"raw_workbook":{"canonical_filename":workbook.get("canonical_filename"),"sha256":workbook["sha256"],"size_bytes":len(workbook_bytes)},"snapshot":{"schema_version":SCHEMA_VERSION,"raw_sha256":expected_snapshot_sha256,"workbook_sha256":workbook["sha256"],"extractor_version":workbook.get("extractor_version"),"total_sheet_count":len(entries),"sheet_inventory":list(EXPECTED_SHEET_INVENTORY)},"sheets":entries,"core_sheets":["db.cty","db.cso","db.ktra","db.cc","db.dkkd","db.Tdoi","db.Tdoi2"],"relationships":snapshot["relationships"],"contract":snapshot["contract"],"freeze":{"declared_frozen":declared_frozen}}
    value["content_sha256"]=_digest(value)
    return value
