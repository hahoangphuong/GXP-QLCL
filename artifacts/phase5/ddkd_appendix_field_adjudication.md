# Phase 5 DDKD Appendix/Decision Field Adjudication

## Scope
- Family: `DDKD_APPENDIX_OR_DECISION`
- Audit target: unresolved fields `All`, `GCN_GMP`, `QD_GMP`
- Evidence sources:
  - active templates `z3. Phụ lục GCN ĐĐKKDD.dotx` and `z4. QĐ cấp ĐĐKKDD.dotx`
  - VBA source `artifacts/legacy_audit/vba_sources/GPs/RecordForm.frm`

## Adjudications
- `All` -> status=`safe_prefix_variant_group`
  targets: `AllGDP, AllGLP, AllGMP, AllGSP`
  evidence: Active templates expose AllGDP/AllGLP/AllGMP/AllGSP bookmarks.
  evidence: RecordForm.Tao_PL_QD_GiayDDK deletes All{GPs_T} inside a 4-group loop.
  evidence: Get_Tplz case 3 and case 4 both feed the same Tao_PL_QD_GiayDDK loop.
- `GCN_GMP` -> status=`case_shared_write_with_missing_active_bookmark`
  evidence: Get_Tplz selects z3 explicitly for case 3 and z4 explicitly for case 4.
  evidence: CreateFilez handles case 3 and case 4 explicitly, then routes both into Tao_PL_QD_GiayDDK.
  evidence: RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung calls Replace_Bookmark wdDoc, GCN_GMP.
  evidence: Replace_Bookmark uses On Error Resume Next and silently no-ops when a bookmark is missing.
  evidence: Neither active template z3 nor z4 exposes a GCN_GMP bookmark.
- `QD_GMP` -> status=`case_shared_write_with_missing_active_bookmark`
  evidence: Get_Tplz selects z3 explicitly for case 3 and z4 explicitly for case 4.
  evidence: CreateFilez handles case 3 and case 4 explicitly, then routes both into Tao_PL_QD_GiayDDK.
  evidence: RecordForm.Tao_PL_QD_GiayDDK_Thongtinchung calls Replace_Bookmark wdDoc, QD_GMP.
  evidence: Replace_Bookmark uses On Error Resume Next and silently no-ops when a bookmark is missing.
  evidence: Neither active template z3 nor z4 exposes a QD_GMP bookmark.

## Recommended Next State
- promotable now: `All`
- still blocked: `GCN_GMP, QD_GMP`
- note: GCN_GMP and QD_GMP should not be promoted into render-safe runtime mapping until we explicitly decide how DocumentService handles case-shared writes whose active templates do not expose matching bookmarks.
- note: A future runtime policy may classify these as tolerated missing-bookmark writes for this family, but that must be an explicit contract decision rather than an accidental side effect.
