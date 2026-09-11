# INSPECTION_QD_KT Business-Input Audit

## Decision

`INSPECTION_QD_KT` remains `BUSINESS_INPUT_CONTRACT_MISSING`. This audit does
not authorize document creation or a typed runtime payload. The checked-out
repository has no `legacy/` VBA source modules; the available evidence is the
procedure inventory and the Phase 5 template reconciliation artifact. A
bookmark label or a physical bookmark match is not evidence of a business
source expression.

The last-correct source for each row below is therefore either the explicitly
recorded branch evidence or **not captured in available source evidence**.

## Mapping Matrix

| Bookmark/field | Exact legacy expression / variable | Upstream source table/field | Conditional logic | Formatting logic | Structured candidate owner | Mapping | Requiredness | Structured data now | Proposed atom owner |
|---|---|---|---|---|---|---|---|---|---|
| `Daychuyen` | No active write proven for `Tao_QDKT_KHKT_BBKT(i=2)` | Not captured | Not captured | Not captured | `Case` / inspection context | BLOCKED | conditional/branch-dependent | no proven QĐKT input contract | `InspectionPlan` or case production-line source, after evidence |
| `Diachicoso` | Not captured | Not captured | Not captured | Not captured | `Site.site_address` | BLOCKED | required if written | address exists, provenance for QĐKT not proven | `Site.site_address` |
| `Diadiem` | Not captured; physical variants `Diadiemx1..3` only | Not captured | Variant expansion is physical evidence only | Not captured | `InspectionPlan` | PARTIAL | conditional | plan dates exist, location meaning not proven | dedicated plan location atom only after evidence |
| `Diadiemx` | Not captured; physical variants `Diadiemx1..3` only | Not captured | Not proven | Not captured | `InspectionPlan` | PARTIAL | conditional | no deterministic mapping | same plan-location atom as `Diadiem`, after evidence |
| `Fulldate` | Not captured | Not captured | Not captured | Not captured | `CaseApplication` / inspection dates | BLOCKED | required if written | dates exist in separate owners; exact meaning unknown | explicit QĐKT rendered-date atom |
| `GhPviCN` | No active write proven for `i=2`; active limitation write documented only for `i=4` | `CaseEvaluationScope.limitation_text` is not authorized for `i=2` | branch-specific | Not captured | branch-aware document scope projection | BLOCKED | conditional | generic scope projection intentionally excludes QĐKT | branch-specific limitation instruction |
| `GhPviDG` | No active write proven for `i=2`; assessment limitation documented for `i=4` | Not captured | branch-specific | default `Không` documented for `i=4` only | `CaseAssessment` / branch projection | BLOCKED | conditional | assessment exists but QĐKT branch not proven | branch-specific assessment limitation |
| `GioiHanPvi` | No active write proven for `i=2`; `GHanDC` documented for `i=3` | Not captured | branch-specific | `GHanDC` defaults to `Không` for `i=3` | `InspectionPlan` / branch projection | BLOCKED | conditional | plan exists, QĐKT use not proven | branch-specific plan limitation |
| `HsDK` | Not captured | `CaseApplication.dossier_code` or `dossier_reference` candidate | Not captured | Not captured | `CaseApplication` | BLOCKED | likely required, not proven | structured dossier fields exist | explicit dossier display atom |
| `MoiDel` | Not captured; physical `MoiDel2` match only | Not captured | deletion/retention semantics not proven | Not captured | case inspection type | PARTIAL | conditional | `Case.inspection_type` exists | explicit delete instruction after VBA proof |
| `NgayKT` | Not captured | `InspectionOutcome.inspected_on` candidate | Must distinguish from range/end date | Not captured | `InspectionOutcome` | BLOCKED | required if written | start date exists | explicit inspection-start atom |
| `NgayKTx` | Not captured | `InspectionOutcome.inspected_to_on` candidate | conditional semantics not proven | Not captured | `InspectionOutcome` | BLOCKED | conditional | end date exists | explicit inspection-end atom |
| `NgaynopHsDK` | Not captured | `CaseApplication.submitted_on` candidate | Not captured | Not captured | `CaseApplication` | PARTIAL | required if written | structured submitted date exists | application-received-date atom |
| `NgayQDKT` | Not captured | `InspectionPlan`/`InspectionOutcome` decision reference has no proven date owner | Not captured | Not captured | decision metadata owner, currently absent | BLOCKED | required if written | reference exists; decision date does not | explicit decision-date atom |
| `PVCepha` | Not captured | `CaseEvaluationScope` taxonomy candidate | GxP/scope branch not proven for QĐKT | Not captured | taxonomy projection | BLOCKED | conditional | taxonomy exists, QĐKT scalar writes not proven | scope-derived atom only after branch proof |
| `PVDuoclieu` | Not captured | `CaseEvaluationScope` taxonomy candidate | GxP/scope branch not proven | Not captured | taxonomy projection | BLOCKED | conditional | taxonomy exists, QĐKT scalar writes not proven | scope-derived atom only after branch proof |
| `PVNangmem` | Not captured | `CaseEvaluationScope` taxonomy candidate | GxP/scope branch not proven | Not captured | taxonomy projection | BLOCKED | conditional | taxonomy exists, QĐKT scalar writes not proven | scope-derived atom only after branch proof |
| `PVNhomat` | Not captured | `CaseEvaluationScope` taxonomy candidate | GxP/scope branch not proven | Not captured | taxonomy projection | BLOCKED | conditional | taxonomy exists, QĐKT scalar writes not proven | scope-derived atom only after branch proof |
| `PVPeni` | Not captured | `CaseEvaluationScope` taxonomy candidate | GxP/scope branch not proven | Not captured | taxonomy projection | BLOCKED | conditional | taxonomy exists, QĐKT scalar writes not proven | scope-derived atom only after branch proof |
| `PVSuibot` | Not captured | `CaseEvaluationScope` taxonomy candidate | GxP/scope branch not proven | Not captured | taxonomy projection | BLOCKED | conditional | taxonomy exists, QĐKT scalar writes not proven | scope-derived atom only after branch proof |
| `PVTiem` | Not captured | `CaseEvaluationScope` taxonomy candidate | GxP/scope branch not proven | Not captured | taxonomy projection | BLOCKED | conditional | taxonomy exists, QĐKT scalar writes not proven | scope-derived atom only after branch proof |
| `QDKT` | Not captured | `InspectionPlan.decision_document_hint` candidate only | Not captured | Not captured | `InspectionPlan` plus explicit decision metadata | BLOCKED | required if written | hint exists; authoritative decision identity not proven | decision reference atom |
| `TaiDel` | Not captured; physical `TaiDel1..4` match only | Not captured | deletion/retention semantics not proven | Not captured | case inspection type | PARTIAL | conditional | `Case.inspection_type` exists | explicit delete instruction after VBA proof |
| `Tencoso` | Not captured; physical `Tencoso1..3` match only | `Site.site_name` candidate | Variant expansion is physical evidence only | Not captured | `Site.site_name` | PARTIAL | required if written | site name exists | site display-name atom |
| `ThoigianKT` | Not captured | `InspectionOutcome` date range candidate | Whether range or generated text is unknown | Not captured | `InspectionOutcome` | BLOCKED | required if written | start/end dates exist | explicit inspection-period atom |
| `TieuchuanKT` | Not captured | `Case.applicable_standard` candidate | Not captured | Not captured | `Case.applicable_standard` | PARTIAL | required if written | standard exists | applicable-standard atom |
| `TT` | Not captured | `InspectionTeam` / ordered members | Role, title and ordering not proven | Not captured | `InspectionTeamMember` | BLOCKED | required if written | identities and sort order exist | ordered team-member atom |
| `TT1` | Not captured | `InspectionTeamMember` candidate | Member role semantics not proven | Not captured | `InspectionTeamMember` | BLOCKED | conditional | structured member rows exist | first team-member atom |
| `TT2` | Not captured | `InspectionTeamMember` candidate | Member role semantics not proven | Not captured | `InspectionTeamMember` | BLOCKED | conditional | structured member rows exist | second team-member atom |
| `TT3Del` | Not captured; exact physical bookmark only | `InspectionTeamMember` candidate | Delete condition not proven | Not captured | ordered team members | PARTIAL | conditional | member count can be known | explicit third-member delete instruction |
| `TT3x` | Not captured; exact physical bookmark only | `InspectionTeamMember` candidate | Third-member semantics not proven | Not captured | ordered team members | PARTIAL | conditional | member count can be known | third team-member atom |
| `TT_SYTx` | Not captured | `InspectionTeamMember` candidate | ministry/department role not proven | Not captured | team member + role metadata | BLOCKED | conditional | generic role label exists, source meaning unknown | explicit authority-role atom |
| `TT_VKNx` | Not captured | `InspectionTeamMember` candidate | institute role not proven | Not captured | team member + role metadata | BLOCKED | conditional | generic role label exists, source meaning unknown | explicit authority-role atom |
| `VKN` | Not captured; physical exact `VKN` match only | `InspectionTeamMember` candidate | organization/role meaning not proven | Not captured | team member identity | PARTIAL | conditional | member identity exists | explicit VKN-member atom |
| `VKNx` | Not captured; physical exact `VKNx` match only | `InspectionTeamMember` candidate | conditional meaning not proven | Not captured | team member identity | PARTIAL | conditional | member identity exists | explicit VKN conditional atom |

## Counts and blockers

The current reconciliation artifact reports 35 logical payload fields, 22 real
bookmarks, 26 unresolved historical payload fields and 7 unmatched real
bookmarks for this family. The matrix above classifies 35 requested fields as:

- `PROVEN`: 0
- `PARTIAL`: 9
- `BLOCKED`: 26

`PARTIAL` means only a physical bookmark family or a candidate structured owner
is known; it is not sufficient for rendering. No field is marked `PROVEN`
because exact source expression plus conditional and formatting semantics are
not available for the QĐKT branch.

The exact blockers are:

1. the checked-out source does not contain `Module1.TaoQDKT_KHKT`,
   `RecordForm.CreateFile`, `RecordForm.Get_Tpl(2)`, or the implementation of
   `RecordForm.Tao_QDKT_KHKT_BBKT(..., i=2)`;
2. the four real QĐKT templates still have a contract mismatch, so physical
   bookmark matches cannot establish logical mapping;
3. decision-date, dossier-display, inspection-period, team-role and conditional
   delete semantics have no authoritative structured contract;
4. the existing evaluation-scope integration explicitly excludes
   `INSPECTION_QD_KT` because the active scalar scope writes are not proven.

## Runtime decision

- Typed QĐKT business-input contract: **not implemented**.
- `INSPECTION_QD_KT` readiness: **unchanged**, `BUSINESS_INPUT_CONTRACT_MISSING`.
- Create endpoint/UI: **not enabled**.
- Generic `{GP}` binary fallback: **not used**; exact GxP binding/locator rules remain unchanged.
- Schema, importer, Phase 7, template binaries and database: **unchanged**.

The next evidence-required slice is to capture the exact source modules and
branch execution for `i=2`, then reconcile the four QĐKT template variants by
logical field and conditional render instruction. No implementation should be
started from this matrix alone.
