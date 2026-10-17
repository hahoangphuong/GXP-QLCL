from __future__ import annotations
from hashlib import sha256
import json
import pytest
from backend.app.domain.cutover_source_manifest_b6k import build_manifest, manifest_bytes
from backend.app.domain.legacy_snapshot_v2 import CANONICAL_WORKBOOK_FILENAME, EXPECTED_SHEET_INVENTORY, EXTRACTOR_VERSION, PROVEN_RELATIONSHIPS, SCHEMA_VERSION, _sheet_classification

CONTRACT={"raw_source_view":"AUTHORITATIVE_READER_OBSERVED_COORDINATES_ONLY","semantic_tabular_view":"NOT_CREATED_IN_BATCH_A","no_inference_rule":"AUTHORITATIVE_WORKBOOK_DATA_MUST_BE_USED;_FALLBACK_REQUIRES_SOURCE_ABSENCE,_EXPLICIT_APPROVAL,_AND_FIELD_REGISTRY_RECORD."}
def digest(v): return sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def fixture():
    wb=b"future-workbook"; sheets=[]
    for n,name in enumerate(EXPECTED_SHEET_INVENTORY,1):
        rows=[{"source_row_number":n+4,"cells":[{"column_ordinal":1,"raw_value":"x","raw_state":"TEXT","observed_type":"str"}]}]
        sheets.append({"sheet_name":name,"sheet_ordinal":n,"classification":_sheet_classification(name),"used_row_count":1,"used_column_count":1,"raw_row_count":1,"populated_cell_count":1,"content_sha256":digest(rows),"raw_coordinate_inventory":{"row_count":1,"column_count":1,"cell_coordinate_count":1},"raw_rows":rows})
    rel=[{"source_sheet":a,"source_field":b,"target_sheet":c,"target_field":d,"cardinality":"UNRESOLVED","evidence":"EXACT_AUTHORITATIVE_WORKBOOK_FIELD_NAMES","status":"PROVEN_FIELD_REFERENCE"} for a,b,c,d in PROVEN_RELATIONSHIPS]
    s={"schema_version":SCHEMA_VERSION,"workbook":{"canonical_filename":CANONICAL_WORKBOOK_FILENAME,"sha256":sha256(wb).hexdigest(),"extractor_version":EXTRACTOR_VERSION,"total_sheet_count":32,"sheet_inventory":list(EXPECTED_SHEET_INVENTORY),"semantic_output_deterministic":True},"sheets":sheets,"relationships":rel,"contract":CONTRACT}
    raw=json.dumps(s,ensure_ascii=False,sort_keys=True).encode(); return wb,s,raw
def build(wb,s,raw): return build_manifest(workbook_bytes=wb,snapshot_bytes=raw,expected_workbook_sha256=sha256(wb).hexdigest(),expected_snapshot_sha256=sha256(raw).hexdigest(),declared_frozen=True)
def test_manifest_valid_deterministic_and_rows_bound():
    wb,s,raw=fixture(); a=build(wb,s,raw); b=build(wb,s,raw); assert manifest_bytes(a)==manifest_bytes(b); assert a["content_sha256"]==b["content_sha256"]
@pytest.mark.parametrize("path",[("workbook","canonical_filename"),("workbook","extractor_version"),("workbook","total_sheet_count"),("sheets",0,"sheet_ordinal"),("sheets",0,"classification"),("sheets",0,"used_row_count"),("sheets",0,"content_sha256")])
def test_manifest_metadata_tamper_fails(path):
    wb,s,_=fixture(); target=s
    for key in path[:-1]: target=target[key]
    target[path[-1]]="bad"; raw=json.dumps(s,ensure_ascii=False,sort_keys=True).encode()
    with pytest.raises(ValueError): build(wb,s,raw)
def test_manifest_contract_relationship_and_duplicate_row_fail():
    wb,s,_=fixture(); s["contract"]["raw_source_view"]="bad";raw=json.dumps(s).encode()
    with pytest.raises(ValueError): build(wb,s,raw)
    wb,s,_=fixture();s["relationships"]=[];raw=json.dumps(s).encode()
    with pytest.raises(ValueError): build(wb,s,raw)
    wb,s,_=fixture();s["sheets"][0]["raw_rows"].append(s["sheets"][0]["raw_rows"][0]);raw=json.dumps(s).encode()
    with pytest.raises(ValueError): build(wb,s,raw)
