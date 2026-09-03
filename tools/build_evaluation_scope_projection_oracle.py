"""Capture the current canonical renderer output hashes before span wiring."""
from __future__ import annotations
import json
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.domain.evaluation_scope import parse_legacy_evaluation_scope, render_evaluation_scope_summary

ROOT = Path(__file__).resolve().parents[1]
def digest(path: Path) -> str: return sha256(path.read_bytes()).hexdigest()
def main() -> None:
    snapshot_path=ROOT/'artifacts/phase3c/legacy_snapshot.json'; taxonomy_path=ROOT/'artifacts/legacy_snapshot/evaluation_scope_taxonomy.json'
    snapshot=json.loads(snapshot_path.read_text(encoding='utf-8')); taxonomy=json.loads(taxonomy_path.read_text(encoding='utf-8'))
    ranges={v['gxp_type']:v['rows'] for v in taxonomy['named_ranges'].values()}; records=[]; selected=0
    for row in snapshot['db.ktra']:
        gxp=row.get('LOẠI KT'); parsed=parse_legacy_evaluation_scope(row.get('PHẠM VI KIỂM TRA'),gxp_type=gxp,taxonomy=taxonomy)
        if parsed['classification']!='STRUCTURED_VALID': continue
        nodes=[{**node,'id':str(i)} for i,node in enumerate(ranges[gxp],1)]; by={node['key']:node for node in nodes}; blocks=[]
        for ordinal,scope in enumerate(parsed['scopes'],1):
            choices=[{'taxonomy_node_id':by[item['key']]['id'],'source_order':item['source_order'],'custom_description':item['description']} for item in scope['selected_nodes']]
            selected += len(choices); blocks.append({'id':str(ordinal),'ordinal':ordinal,'name':scope['name'],'note':scope['note'],'selections':choices,'unkeyed_entries':scope['unkeyed_entries']})
        text=render_evaluation_scope_summary(blocks=blocks,taxonomy_nodes=nodes,limitation_text=parsed['limitation_text'])
        records.append({'legacy_inspection_id':str(row.get('ID')),'gxp_type':gxp,'rendered_sha256':sha256(text.encode()).hexdigest(),'rendered_length':len(text)})
    if len(records)!=677 or selected!=9762: raise SystemExit(f'Unexpected corpus: {len(records)} records, {selected} selected nodes')
    result={'schema_version':'evaluation-scope-canonical-projection-oracle/v1','snapshot_sha256':digest(snapshot_path),'taxonomy_sha256':digest(taxonomy_path),'record_count':len(records),'selected_node_count':selected,'records':sorted(records,key=lambda x:(x['gxp_type'],x['legacy_inspection_id']))}
    out=ROOT/'artifacts/legacy_audit/evaluation_scope_canonical_projection_oracle.json'; out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__': main()
