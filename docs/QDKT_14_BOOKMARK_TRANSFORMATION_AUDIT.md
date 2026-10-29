# QĐKT — 14-operation source and transformation audit

Generated read-only from pinned repository evidence. Not a payload, approval or renderer contract.

14 logical VBA symbols are not 14 exact Word names; numbered targets and dynamic TTx are listed below.

Status counts: {"BLOCKED": 4, "CONTRADICTED": 4, "PARTIAL": 6, "VERIFIED": 0}. Legacy ownership stays 8 BLOCKED / 6 PARTIAL.

| Logical operation | Status | Effective physical targets (GLP / GMP / GMPbb / GSP) |
|---|---|---|
| Diachicoso | CONTRADICTED | absent / absent / absent / absent |
| Diadiem | BLOCKED | absent / absent / absent / absent |
| Diadiemx | BLOCKED | Diadiemx1, Diadiemx2, Diadiemx3 / Diadiemx1, Diadiemx2, Diadiemx3 / Diadiemx1, Diadiemx2 / Diadiemx1, Diadiemx2 |
| Fulldate | CONTRADICTED | absent / absent / absent / absent |
| HsDK | PARTIAL | absent / absent / absent / absent |
| NgayQDKT | CONTRADICTED | absent / absent / absent / absent |
| NgaynopHsDK | PARTIAL | absent / absent / absent / absent |
| QDKT | CONTRADICTED | absent / absent / absent / absent |
| TT3Del | PARTIAL | TT3Del / TT3Del / TT3Del / TT3Del |
| TT3x | PARTIAL | TT3x / TT3x / TT3x / TT3x |
| TTx | PARTIAL | TT1x, TT2x / TT1x, TT2x / TT1x, TT2x / TT1x, TT2x |
| Tencoso | PARTIAL | Tencoso1, Tencoso2, Tencoso3 / Tencoso1, Tencoso2, Tencoso3 / Tencoso1, Tencoso2, Tencoso3 / Tencoso1, Tencoso2, Tencoso3 |
| VKN | BLOCKED | VKN1, VKN2 / VKN1, VKN2 / N/A (branch) / N/A (branch) |
| VKNx | BLOCKED | VKNx / VKNx / N/A (branch) / N/A (branch) |

## Runtime identity chain and operator protocol

This extends the captured facts without changing any original semantic pin. UNVERIFIED_VERSION_BINDING remains a blocker; no live Excel observation has been supplied or performed by the agent.

| Stage | Category | Scope |
|---|---|---|
| PRIMARY_SUPPLIED_ADDIN | BYTE_IDENTITY_PROVEN | supplied snapshot only; not current Excel-loaded or executed bytes |
| REVIEWED_EXPORT_SET | ENCODING_AMBIGUOUS | 14 writer lines and 9 whole procedures after LF-only normalization; not version identity |
| BUILD_AND_DISTRIBUTION | VERSION_BINDING_UNVERIFIED | Bounded workspace search; no assertion about unavailable original build/distribution systems. |
| EXCEL_LOADED_RUNTIME | RUNTIME_IDENTITY_UNVERIFIED | no independently authenticated live-session identity; loader can reuse same-name workbook without a hash check |

Acceptance dimensions (not approvals):

| Dimension | Category |
|---|---|
| build_distribution | VERSION_BINDING_UNVERIFIED |
| business_owner_acceptance | EVIDENCE_UNAVAILABLE |
| executable_vba | RUNTIME_IDENTITY_UNVERIFIED |
| export_encoding | ENCODING_AMBIGUOUS |
| independent_custody | EVIDENCE_UNAVAILABLE |
| loaded_runtime | RUNTIME_IDENTITY_UNVERIFIED |
| reported_disk | EVIDENCE_UNAVAILABLE |
| reviewed_source | SOURCE_EQUIVALENCE_PROVEN |
| supplied_snapshot | BYTE_IDENTITY_PROVEN |

Detailed operator-only protocol: `docs/QDKT_RUNTIME_OBSERVATION_PROTOCOL.md`. It separates observed COM path, on-disk snapshot, in-memory executed code and reviewed source. Unsigned, even internally consistent, PID/path/hash metadata never authenticates a collector or closes runtime identity.

Encoding evidence: `tests/fixtures/inspection_qd_kt_runtime_identity_evidence.json` records original line hex/SHA, cp1258 and cp1252 codepoints, and exact ZIP/add-in lines. Get_Tpl has nine differing lines in Cases 7/8/11/12/13, outside Case 2. Get_TTV2 has one differing error-message line in its Fail handler: this CAN be reached on the i=2 call's failure path, not proven executed, and is not a direct Word text write. Neither ambiguity is silently normalized or treated as an approved export encoding.

The add-in docProps/app.xml records producer Application=Microsoft Excel and AppVersion=16.0300, with no custom properties or manifest/build/release/version-named member observed. This is Office producer metadata, not a VBA build/distribution mapping or the version of an observed Excel session. The byte-anchored companion records the metadata XML SHA without collecting author/private core properties.

Verifier boundary review: changed bytes and changed expected metadata cannot pass the independent capture pin; symlink/alternate-root acquisition is delegated to the existing bounded evidence reader. Known binary pins are checked before ZIP/VBA parsing. Malformed foreign projects or case-colliding module attacks are not reachable past unchanged byte pins; parser defense tests do not claim such a bypass was found. Static capture never substitutes for requested fresh extraction. Repository-code/dependency compromise is outside this input-only trust claim.

New demonstrated gap: escaped lone UTF-16 surrogates were accepted by the JSON reader and failed only during later UTF-8 canonicalization. They now fail at the shared parser owner, including nested values/keys; valid Unicode and all old pins remain unchanged. The observation assessor is a diagnostic contract, not an approval or memory-attestation API.

## Runtime/source evidence hardening

Evidence classes remain separate: approved business policy; reviewed ZIP source; captured add-in source; exact original binary bytes; Word output/legal acceptance. The new capture is pinned static evidence, not a claim that local files were freshly verified by the normal audit.

### Artifact and acquisition inventory

All six inputs were supplied in the local workspace. Original acquisition/build/distribution chain is not attested. No timestamp, filename, excerpt or matching JSON hash field proves version identity.

| Artifact | Exact byte SHA-256 |
|---|---|
| `legacy/GPs.xlam` | `52725cba1fd87107814d07da1dbae8d79c77127765018b0daf4b6fe6f44b1b58` |
| `legacy/GXP-VBA code.zip` | `6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7` |
| `legacy/Templates/2. QD KT - GLP.dotx` | `c55695dbdaafa48f0b2a4211a8adda7b97443a44439d9a81de306ce98729ec19` |
| `legacy/Templates/2. QD KT - GMP.dotx` | `490d534580ce00844b6175e64ca4e2fdc345d7957be8813f0f62d03a9b82c1a5` |
| `legacy/Templates/2. QD KT - GMPbb.dotx` | `fec4dc35ac5fbb2f2ef6b56750fe6dcf5316dafc0898395279d9ff281b2ca771` |
| `legacy/Templates/2. QD KT - GSP.dotx` | `890df5e2345e2927b286f4a3adb107a984825eff21e998ae253020ecac46eea1` |

Extraction: oletools==0.60.2 VBA_Parser + VBA_Project PROJECTCODEPAGE; static only; in-memory immutable bytes. Normalization is LF only; no trim, case-fold, NFC/NFD or punctuation changes.

The add-in physically contains `xl/vbaProject.bin`, SHA `84afc3e2d431b550e7f7f6b392f1a363d6d476efe444ba7aab3b4932dba4bcfe`. BYTE_IDENTICAL_BINDING_PROVEN applies only to that embedded binary member and its containing add-in bytes. It does not prove the ZIP exports came from that binary, that Excel loaded it, or that compiled p-code matches extracted source.

The reviewed ZIP has 51 exports/FRX entries and no WinAPI module or runtime add-in. The add-in contains QĐKT source procedures and all three uniquely declared WinAPI helpers in the same captured project. Static call references resolve in that source snapshot, not in a proven live execution.

PROJECTCODEPAGE in the add-in is 1252. The historic ZIP trace uses `_decode` with cp1258 fallback; the ZIP does not attest its export codepage. Full Get_Tpl and Get_TTV2 text differs under the reviewed decoder in non-i2/error-message literals; cp1252 comparison matches. This is an encoding ambiguity, not proof of an actual changed business implementation. Existing reviewed source and semantic pins are preserved.

| Procedure | ZIP lines | Add-in source lines | Reviewed-decoder comparison |
|---|---|---|---|
| `Module1.bas!TaoQDKT_KHKT` | [595, 651] | [595, 651] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `Module1.bas!FormatDateS` | [2042, 2052] | [2042, 2052] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `RecordForm.frm!CreateFile` | [1702, 1789] | [1695, 1782] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `RecordForm.frm!Get_Tpl` | [657, 729] | [650, 722] | IMPLEMENTATION_DIFFERS |
| `RecordForm.frm!Tao_QDKT_KHKT_BBKT` | [739, 818] | [732, 811] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `RecordForm.frm!GetTT_Ktra` | [326, 412] | [319, 405] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `RecordForm.frm!Get_VKN` | [1854, 1871] | [1847, 1864] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `RecordForm.frm!Replace_Bookmark` | [589, 603] | [582, 596] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `RecordForm.frm!Delete_Bookmark` | [576, 587] | [569, 580] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `TTVForm.frm!Get_TTV2` | [399, 428] | [392, 421] | IMPLEMENTATION_DIFFERS |
| `TTVForm.frm!Get_TTV_List3` | [380, 397] | [373, 390] | CONTENT_EQUIVALENT_VERSION_UNPROVEN |
| `WinAPI.bas!DelLastIf_Ins` | absent | [504, 510] | ARTIFACT_UNAVAILABLE_OR_EVIDENCE_INSUFFICIENT |
| `WinAPI.bas!LCase_FirstChar` | absent | [552, 555] | ARTIFACT_UNAVAILABLE_OR_EVIDENCE_INSUFFICIENT |
| `WinAPI.bas!Del_LastPeriod` | absent | [559, 561] | ARTIFACT_UNAVAILABLE_OR_EVIDENCE_INSUFFICIENT |

All 14 operation source lines match in the captured writer (ZIP 739–818 versus add-in 732–811). Each field's `runtime_source_reference` records exact paired line numbers and LF source hashes. Business ownership, variable initialization and actual values remain unproven by this source match.

Supplementary workbook observed separately: `legacy/Danh sách Kiểm tra GPs.xlsb`, exact SHA `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`. Static oletools extraction of `Module1.Load_Lib`, lines 20–40, shows reuse of an already-open workbook named GPs.xlam, then local Addins and configured fallback opening at 32–33. Module1:73 invokes `Application.Run` by add-in name. No checksum/build identity is checked on this path. An already-loaded or different path copy is a competing explanation; this supplementary workbook is not one of the six fresh-verifier inputs. No workbook/add-in was opened in Excel.

### Unresolved evidence matrix

| Relationship | Result | Still needed |
|---|---|---|
| Add-in to embedded project bytes | BYTE_IDENTICAL_BINDING_PROVEN (container-member scope only) | Loaded-runtime and p-code/source attestation |
| Reviewed ZIP to captured QĐKT source lines | CONTENT_EQUIVALENT_VERSION_UNPROVEN | Attested export/build/distribution manifest, including codepage |
| WinAPI helper to ZIP | ARTIFACT_UNAVAILABLE_OR_EVIDENCE_INSUFFICIENT | Original helper export/runtime-package provenance; no invented ZIP body |
| Full Get_Tpl/Get_TTV2 reviewed-decoder text | IMPLEMENTATION_DIFFERS as text, encoding cause unresolved | Export codepage evidence; do not infer active i=2 change |
| Template filename formula to original bytes selected at runtime | UNVERIFIED_VERSION_BINDING | Resolved Template_Path/version capture and actual Word UAT |
| All source evidence to legal/business equivalence | Not established | Existing owner decisions/date/timezone/Word acceptance |

Fresh local reproduction: with the reviewed optional analyst tool `oletools==0.60.2`, run `python -m tools.audit_qdkt_source_transformations --verify-local-artifacts --format json`. The flag reads the six fixed local inputs through the existing bounded offline evidence reader, checks actual immutable bytes before extraction, re-extracts source and scans every word/*.xml (including notes), then compares the entire capture with the independent pin. Missing/substituted bytes, extractor absence/version change or metadata drift blocks; there is no fallback to captured evidence labelled as fresh. Stdout only and exit 2 remain intentional because render readiness is blocked.

New RED→GREEN cases reject foreign GxP objects, duplicate/malformed physical names, bool/float numbered bounds and JSON exponent overflow. Valid target ordering/missing-target no-op behavior is preserved; Unicode, casing and punctuation are not normalized away. No renderer or business source owner was added.

## New findings and validation boundary

Last-correct: operation line/reachability and the 8/6 ownership set were already checked. First-incorrect: assignment, formatting, candidate-owner and invariant metadata could change without rejection; matching edits to both archive hashes could substitute the reviewed source. Full semantic pins now reject those changes while allowing JSON whitespace/key ordering differences.

Separate RED cases showed duplicate JSON keys taking the last value, malformed reachability escaping as TypeError, an unknown geography enum ignored by the vaccine branch, and a foreign equality object masquerading as vaccine in both selector and wrapper. Minimal fixes reject these at their source owners. They do not establish manufacture-source provenance.

The planning entry assigns Daychuyen, but authority logic reads DaychuyenDD; CreateFile(i=2) does not reload GetTT_Ktra. No fresh assignment of dossier/decision public variables is proven on that entry. This is unproven variable lifetime, not a claim that a particular runtime document used stale data.

Backend module hashes use UTF-8 with LF-normalized source to survive Windows Git checkout conversion. Original template/source-binary hashes remain exact byte hashes. The report is deterministic but pins are review anchors, not signatures or independent owner attestations.

## Diachicoso — CONTRADICTED

Legacy expression: `Del_LastPeriod(Replace(DiachiDD, vbCrLf, ";"))`.

Legacy transform: Replace CRLF with semicolon, then Del_LastPeriod. Supplementary add-in helper removes exactly one trailing period, without Trim or lone-LF cleanup. This is not approved current address normalization.

Candidate canonical source: Persisted Site.site_address via Case.site_id and read_qdkt_registered_site.

Ownership: Current owner explicitly selected registered Site address; legacy primary entry reads planning-row cell 11.

Null/missing: Current reader blocks missing/untrimmed registered address or absent Case/Site join; never falls back to plan cells.

Multiple records: One Case-linked Site; no address concatenation or selection from another Case.

Date/time: Not a date field.

Difference: The legacy and approved current source owners differ by design. Exact target is absent in all four originals; no current punctuation/layout acceptance exists.

Blockers: `LOCATION_BOOKMARK_FORMAT_UNPROVEN`, `QDKT_ADDRESS_SOURCE_POLICY_CONFLICT`.

Owner evidence: Owner-approved registered-address presentation without importing planning-row assumptions; Word layout acceptance or intentional no-op decision.

Evidence refs: `MainForm.frm:4154`; `Module1.bas:612`; `RecordForm.frm:747`; `backend/app/document/inspection_qd_kt_registered_site.py:read_qdkt_registered_site`; `docs/INSPECTION_QD_KT_CONFIRMED_BUSINESS_RULES_20261022.md:Địa chỉ và địa danh`; `legacy/GPs.xlam!WinAPI.bas:559-561 (supplementary version)`.

## Diadiem — BLOCKED

Legacy expression: `Tinhthanh`.

Legacy transform: Only when a comma exists: take suffix, trim, remove province/city prefixes and periods case-insensitively; then HCM alias rewrite; Dia_danh Match index.

Candidate canonical source: Case-linked Site.province_name is a candidate province, not automatically a legal locality string.

Ownership: Legacy selected planning-row cell 10; modern registered province is Case -> Site. Their live-value equivalence is not proven.

Null/missing: Legacy missing Match becomes 0; modern unknown/absent province blocks, never defaults to a northern province.

Multiple records: Require exactly one legacy-reference match; no first match or alphabetic comparison.

Date/time: Not a date field.

Difference: Attested-legacy locality projection exists but does not establish current Case equivalence; legal locality and registered address are different concepts. Exact Diadiem is absent in all originals.

Blockers: `LEGACY_PROVINCE_MAPPING_UNPROVEN`, `LOCATION_BOOKMARK_FORMAT_UNPROVEN`.

Owner evidence: Owner-approved Case locality source and prefix/alias/character rules; Evidence for current versus historical province mapping.

Evidence refs: `MainForm.frm:4156`; `Module1.bas:614`; `Module1.bas:614-632`; `Module1.bas:617`; `Module1.bas:618`; `Module1.bas:619`; `Module1.bas:620`; `Module1.bas:621`; `Module1.bas:622`; `Module1.bas:623`; `Module1.bas:625`; `RecordForm.frm:745`; `backend/app/document/inspection_qd_kt_locality_projection.py:project_qdkt_locality_from_attested_legacy`.

## Diadiemx — BLOCKED

Legacy expression: `LCase_FirstChar(Tinhthanhx), 1, 3`.

Legacy transform: If Match > 0, Index(Dia_danh_x,index,2) + province, else raw province; replace TP prefix; LCase_FirstChar call; numbered targets 1..3. Supplementary add-in helper lowercases only the first character and preserves the rest.

Candidate canonical source: Attested legacy Dia_danh_x prefix plus province; no approved Site-to-legal-place display contract.

Ownership: Planning province lookup via Dia_danh/Dia_danh_x, not address parsing or a free-text plan fallback.

Null/missing: Legacy falls back to province on missing lookup; backend does not certify that fallback for a modern Case.

Multiple records: One unique source reference entry; missing numbered target is a legacy no-op, not a reason to choose another province.

Date/time: Not a date field.

Difference: GLP/GMP have three effective targets; GMPbb/GSP have two. Existing attested projection leaves case_source_equivalence_verified=false.

Blockers: `LOCATION_BOOKMARK_FORMAT_UNPROVEN`, `QDKT_PLANNING_ROW_PROVINCE_UNATTESTED`.

Owner evidence: Owner-approved current locality display and Case binding; Word acceptance of numbered target formatting.

Evidence refs: `MainForm.frm:4158`; `Module1.bas:626-632`; `Module1.bas:628`; `Module1.bas:630`; `Module1.bas:632`; `RecordForm.frm:746`; `backend/app/document/inspection_qd_kt_locality_projection.py:project_qdkt_locality_from_attested_legacy`; `legacy/GPs.xlam!WinAPI.bas:552-555 (supplementary version)`.

## Fulldate — CONTRADICTED

Legacy expression: `FormatDateS(Date, 1)`.

Legacy transform: Module1.FormatDateS(Date, 1): IsDate then dd tháng MM năm yyyy; invalid date returns NulStr. RecordForm calls the exact unnumbered target.

Candidate canonical source: No Process A issuance date source is authorized.

Ownership: VBA workstation intrinsic Date has no Case/Site/Plan owner; do not substitute Case dates or server clock.

Null/missing: Process A preserves the template's blank issuance date; absence of Fulldate does not prove a visually blank date line.

Multiple records: No latest record or file creation timestamp may supply an issuance date.

Date/time: Workstation calendar Date is distinct from backend clock, generated_at, Case dates and legal issuance. Business timezone is unproven.

Difference: Legacy attempts a workstation-date write; confirmed current Process A policy requires blank issuance date. All four observed templates lack this target.

Blockers: `BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED`, `QDKT_BUSINESS_TIMEZONE_UNPROVEN`, `QDKT_DRAFT_DATE_POLICY_CONFLICT`.

Owner evidence: Owner-approved blank-date layout and handling of literal template year; Actual Word visual evidence for four variants.

Evidence refs: `Module1.bas:2042-2052`; `RecordForm.frm:736`; `RecordForm.frm:743`; `docs/INSPECTION_QD_KT_CONFIRMED_BUSINESS_RULES_20261022.md:Ngày trên bản dự thảo`.

## HsDK — PARTIAL

Legacy expression: `s_MaHsDk`.

Legacy transform: Exact unnumbered HsDK write of s_MaHsDk; GetTT_Ktra reads the selected db_ktra row column ColDB_HSDK_Ktra+1 (I). No coercion from a similar field name.

Candidate canonical source: Current persisted CaseApplication.dossier_code, through read_dossier_snapshot.

Ownership: Case/Application/Site canonical UUID/version join is separate from historical selected Rg3 row identity. Module1 entry does not reload this public variable.

Null/missing: Legacy empty text is silently skipped; current dossier gate blocks absent/blank code and identity/version conflicts.

Multiple records: Current CaseApplication snapshot only; no legacy row, prior Case or latest unrelated application fallback.

Date/time: Dossier code is not a date or issuance number.

Difference: Dossier semantics are source-proven; public-state freshness at the planning entry is not. Target absent in all originals; A/B owner choice still required.

Blockers: `QDKT_DOSSIER_TARGET_ABSENT`, `QDKT_LEGACY_PUBLIC_STATE_LIFETIME_UNPROVEN`.

Owner evidence: Legal A/B wording/placement or intentional omission approval; Candidate version/checksum and Word UAT.

Evidence refs: `RecordForm.frm:334-343`; `RecordForm.frm:343`; `RecordForm.frm:748`; `artifacts/legacy_audit/inspection_qd_kt_dossier_bookmark_source_evidence.json`; `backend/app/document/inspection_qd_kt_renderer_contract.py:read_dossier_snapshot`.

## NgayQDKT — CONTRADICTED

Legacy expression: `NgayQDKT`.

Legacy transform: Trailing token of legacy combined cell, or empty string when no delimiter; exact NgayQDKT write. No timestamp/date-only conversion is justified by this split.

Candidate canonical source: Process B only: date-only InspectionDecision.decision_on from the same selected source as reference.

Ownership: Same Case/Plan/decision atoms and lineage; never Case creation date, file date, backend clock or prior Case.

Null/missing: Process A has no issuance-date atom; Process B missing date blocks. Empty legacy text skips replacement without proving a blank Word date.

Multiple records: Reference and date stay paired to one source ID; replacement date cannot precede predecessor; same-day requires explicit lineage.

Date/time: Source decision_on is date-only and distinct from aware CaseApplication submission time. Legal issuance is still unverified.

Difference: Legacy attempted write conflicts with blank draft-date policy; exact target absent in originals. No automatic legal-issued status follows from persistence.

Blockers: `QDKT_DRAFT_DATE_POLICY_CONFLICT`, `QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN`.

Owner evidence: External issuance evidence for Process B; Owner/Word proof of Process A blank administrative date.

Evidence refs: `MainForm.frm:4176`; `MainForm.frm:4179`; `RecordForm.frm:374-384`; `RecordForm.frm:381`; `RecordForm.frm:383`; `RecordForm.frm:790`; `backend/app/document/inspection_qd_kt_decision_source.py:require_latest_qdkt_reference`.

## NgaynopHsDK — PARTIAL

Legacy expression: `Replace(s_NgaynopHsDk, "-", "/")`.

Legacy transform: GetTT_Ktra reads H; writer only replaces '-' with '/'. It does not define business timezone or normalize a backend timestamp.

Candidate canonical source: Current persisted CaseApplication.submitted_on: timestamp with timezone, not date-only.

Ownership: Same Case/Application/Site/version snapshot as dossier code; db_ktra H is submission date, not automatically receipt date.

Null/missing: Missing/naive/ambiguous timestamp or UNDECIDED rule blocks. Never use today, file time, received_at or created_at.

Multiple records: Require the matching application snapshot/version; no mixed code/date from different records.

Date/time: Date-only and aware timestamp are separate representations; recorded-offset date is only an explicit proposal. PostgreSQL session offset can change calendar day; timezone remains unproven.

Difference: Semantic submission-date evidence exists, but DB representation/display policy and absent target prevent full equivalence.

Blockers: `QDKT_BUSINESS_TIMEZONE_UNPROVEN`, `QDKT_DATE_NORMALIZATION_UNAPPROVED`, `QDKT_DOSSIER_TARGET_ABSENT`.

Owner evidence: Business owner date normalization/display decision; Legal A/B decision and actual Word UAT.

Evidence refs: `RecordForm.frm:343`; `RecordForm.frm:749`; `backend/app/document/inspection_qd_kt_renderer_contract.py:normalize_submission_date`; `docs/QDKT_RENDERER_DECISION_WORD_UAT.md:Confirmed lineage and date contract`.

## QDKT — CONTRADICTED

Legacy expression: `QDKT:`.

Legacy transform: GetTT_Ktra splits combined db_ktra decision cell into first token and trailing date; malformed/no separator leaves reference string. Writer attempts exact QDKT.

Candidate canonical source: Process B only: Case/Plan-bound InspectionDecision.reference selected by proven REPLACES lineage.

Ownership: Persisted Case -> InspectionPlan -> source decision, never scalar projection fallback or identity-map state. No such atom belongs in Process A.

Null/missing: No source rows or incomplete/ambiguous chain blocks. Process A must not inherit an existing reference; planning entry does not reload this public variable.

Multiple records: Use #191 complete single-root/REPLACES chain, no MAX(id), MAX(date), insertion order, unknown amendments or scalar projection.

Date/time: Reference text is not evidence of legal issuance.

Difference: Legacy i=2 attempts a reference write while current draft policy excludes issued reference/date. Exact target absent; persisted source is not external issuance proof.

Blockers: `QDKT_DRAFT_ISSUED_REFERENCE_POLICY_CONFLICT`, `QDKT_LEGAL_ISSUANCE_EVIDENCE_UNPROVEN`.

Owner evidence: Approved external issuance evidence contract for Process B; Keep Process A reference absent; resolve unsupported lifecycle policy.

Evidence refs: `MainForm.frm:4176`; `MainForm.frm:4179`; `RecordForm.frm:1453`; `RecordForm.frm:374-384`; `RecordForm.frm:381`; `RecordForm.frm:383`; `RecordForm.frm:790`; `backend/app/document/inspection_qd_kt_case_readiness.py:inspect_qdkt_case_readiness`; `backend/app/document/inspection_qd_kt_decision_source.py:read_latest_qdkt_reference_for_case`.

## TT3Del — PARTIAL

Legacy expression: `(DELETE: no value)`.

Legacy transform: When UBound(Split(TTVdd,'|'))<=1, Delete_Bookmark.Range.Delete of TT3Del; DELETE has no value expression.

Candidate canonical source: Same ordered Case team and draft roster evidence; no write payload is a deletion instruction.

Ownership: Deletion predicate must bind to the same reviewed roster/version and template span, never another decision's team.

Null/missing: Missing target is silently ignored in VBA; current deletion span/format must remain fail-closed until verified.

Multiple records: Member count/order and third-member span evidence are required; a current count does not approve a prior draft.

Date/time: Not an issuance-date source.

Difference: Physical presence and count predicate are proven facts; deleting a Word range with legal surrounding text still requires span/visual acceptance.

Blockers: `INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED`, `QDKT_THIRD_MEMBER_DELETION_ACCEPTANCE_UNPROVEN`.

Owner evidence: Approved deletion span and roster binding; Word proof for short and extended rosters.

Evidence refs: `ExtRecordForm.frm:102`; `ExtRecordForm.frm:138`; `ExtRecordForm.frm:171`; `ExtRecordForm.frm:185`; `ExtRecordForm.frm:227`; `ExtRecordForm.frm:229`; `ExtRecordForm.frm:236`; `ExtRecordForm.frm:242`; `ExtRecordForm.frm:41`; `ExtRecordForm.frm:43`; `ExtRecordForm.frm:44`; `ExtRecordForm.frm:46`; `ExtRecordForm.frm:47`; `ExtRecordForm.frm:53`; `ExtRecordForm.frm:54`; `ExtRecordForm.frm:56`; `ExtRecordForm.frm:57`; `Module1.bas:645`; `RecordForm.frm:1394`; `RecordForm.frm:1488`; `RecordForm.frm:1526`; `RecordForm.frm:1541`; `RecordForm.frm:1986`; `RecordForm.frm:1997`; `RecordForm.frm:2000`; `RecordForm.frm:2003`; `RecordForm.frm:2004`; `RecordForm.frm:576-587`; `RecordForm.frm:754`; `RecordForm.frm:754-766`; `RecordForm.frm:776`; `RecordForm.frm:783`; `RecordForm.frm:800`; `RecordForm.frm:877`; `RecordForm.frm:898`; `TTVForm.frm:351`; `TTVForm.frm:413`; `TTVForm.frm:504`; `TTVForm.frm:508`; `backend/app/document/inspection_qd_kt_third_member_span.py`.

## TT3x — PARTIAL

Legacy expression: `TVss`.

Legacy transform: TTVForm.Get_TTV_List3 composes degree/prefix + cleaned name (remove '*' and 'PCT. ') + ' - ' + title + ', ' + unit. Writer splits TTVdd by '|', trims third entry, adds TT_ext + CRLF for later entries and writes TT3x only when UBound >1.

Candidate canonical source: Case-owned ordered InspectionTeamMember rows plus separately reviewed draft roster/version/title evidence.

Ownership: Case team is not an approved decision-specific roster. Member identity/order does not prove titles, positions or Word text.

Null/missing: Legacy On Error Resume Next/empty text can leave placeholders. Modern missing/empty/unstable team or absent required extension blocks.

Multiple records: Exactly one Case team and unique ordered members; preserve source order, do not reorder by name/title/ID.

Date/time: Roster-at-draft/version evidence is separate from current team and issue date.

Difference: Legacy formatted TTVdd comes through TTVForm; modern display_name/role_code alone cannot reproduce degree/title/position and template fragment formatting.

Blockers: `INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED`, `QDKT_TEAM_WORD_FORMAT_UNPROVEN`.

Owner evidence: Source-attested TTVForm formatting/title provenance; Exact TT_ext fragment and real Word roster/layout acceptance.

Evidence refs: `ExtRecordForm.frm:102`; `ExtRecordForm.frm:138`; `ExtRecordForm.frm:171`; `ExtRecordForm.frm:185`; `ExtRecordForm.frm:227`; `ExtRecordForm.frm:229`; `ExtRecordForm.frm:236`; `ExtRecordForm.frm:242`; `ExtRecordForm.frm:41`; `ExtRecordForm.frm:43`; `ExtRecordForm.frm:44`; `ExtRecordForm.frm:46`; `ExtRecordForm.frm:47`; `ExtRecordForm.frm:53`; `ExtRecordForm.frm:54`; `ExtRecordForm.frm:56`; `ExtRecordForm.frm:57`; `Module1.bas:639-645`; `Module1.bas:645`; `RecordForm.frm:1394`; `RecordForm.frm:1488`; `RecordForm.frm:1526`; `RecordForm.frm:1541`; `RecordForm.frm:1986`; `RecordForm.frm:1997`; `RecordForm.frm:2000`; `RecordForm.frm:2003`; `RecordForm.frm:2004`; `RecordForm.frm:754`; `RecordForm.frm:754-765`; `RecordForm.frm:759`; `RecordForm.frm:761`; `RecordForm.frm:763`; `RecordForm.frm:776`; `RecordForm.frm:778`; `RecordForm.frm:783`; `RecordForm.frm:785`; `RecordForm.frm:800`; `RecordForm.frm:877`; `RecordForm.frm:898`; `TTVForm.frm:148-155,329-340,380-428,494-527`; `TTVForm.frm:351`; `TTVForm.frm:413`; `TTVForm.frm:504`; `TTVForm.frm:508`; `backend/app/document/inspection_qd_kt_team_layout_instructions.py:plan_qdkt_team_layout`.

## TTx — PARTIAL

Legacy expression: `Trim(Ds_TTV(k)):        k = k + 1`.

Legacy transform: k=0..1 while within UBound: exact dynamic names TT1x/TT2x and Trim(Ds_TTV(k)). TTx itself is not a physical target.

Candidate canonical source: Ordered Case team members with separately attested legacy formatted display/title provenance.

Ownership: Process A uses proposed Case team; Process B needs approved decision-specific evidence. No automatic conversion between them.

Null/missing: Legacy may leave later placeholders when tokens are missing; modern pure layout gate conservatively requires a complete attested display, not guessed blank members.

Multiple records: Backend requires explicit stable sort_order/unique identities. Legacy Get_TTV_Index follows comma-token order and picks the first normalized name match; unmatched names are omitted by Get_TTV_List3. Do not import that name lookup as canonical identity.

Date/time: Draft snapshot/version is distinct from legal issuance and current member metadata.

Difference: Physical target mapping is proven; formatted legacy role/title strings and Word paragraph layout remain unresolved despite correct DB membership.

Blockers: `INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED`, `QDKT_TEAM_TITLE_PROVENANCE_UNPROVEN`.

Owner evidence: Owner-approved identity/title/position composition; Version-bound roster and four-variant Word acceptance.

Evidence refs: `ExtRecordForm.frm:102`; `ExtRecordForm.frm:138`; `ExtRecordForm.frm:171`; `ExtRecordForm.frm:185`; `ExtRecordForm.frm:227`; `ExtRecordForm.frm:229`; `ExtRecordForm.frm:236`; `ExtRecordForm.frm:242`; `ExtRecordForm.frm:41`; `ExtRecordForm.frm:43`; `ExtRecordForm.frm:44`; `ExtRecordForm.frm:46`; `ExtRecordForm.frm:47`; `ExtRecordForm.frm:53`; `ExtRecordForm.frm:54`; `ExtRecordForm.frm:56`; `ExtRecordForm.frm:57`; `Module1.bas:639-645`; `Module1.bas:645`; `RecordForm.frm:1394`; `RecordForm.frm:1488`; `RecordForm.frm:1526`; `RecordForm.frm:1541`; `RecordForm.frm:1986`; `RecordForm.frm:1997`; `RecordForm.frm:2000`; `RecordForm.frm:2003`; `RecordForm.frm:2004`; `RecordForm.frm:754`; `RecordForm.frm:754-759`; `RecordForm.frm:759`; `RecordForm.frm:776`; `RecordForm.frm:783`; `RecordForm.frm:800`; `RecordForm.frm:877`; `RecordForm.frm:898`; `TTVForm.frm:148-155,329-340,380-397`; `TTVForm.frm:351`; `TTVForm.frm:413`; `TTVForm.frm:504`; `TTVForm.frm:508`; `backend/app/document/inspection_qd_kt_team_snapshot_review.py`; `backend/app/document/inspection_qd_kt_team_source.py:read_qdkt_team_source`.

## Tencoso — PARTIAL

Legacy expression: `TenCtydd, 1, 8`.

Legacy transform: DelLastIf_Ins(cell 4, vbCrLf); supplementary add-in helper removes trailing characters in the CR/LF set, not embedded lines/general whitespace. Replace_Bookmark bounds 1..8 repeats the same TenCtydd value.

Candidate canonical source: Site.site_name via persisted Case.site_id; candidate only, not a complete QĐKT name atom.

Ownership: Primary Module1 entry uses merged planning-row cell 4; MainForm alternate uses db_cso. Modern Case-to-Site is canonical, but name/format selection is not closed.

Null/missing: Legacy empty text exits without replacement. No backend default to company name, parent company or another Site is approved.

Multiple records: Read one Case-linked Site; series target count is not a multi-Site selection rule.

Date/time: Not a date field.

Difference: Three observed numbered targets receive identical text; source-row/name/title equivalence and Word line wrapping remain partial.

Blockers: `QDKT_NAME_FORMATTING_UNPROVEN`, `QDKT_SITE_NAME_SOURCE_EQUIVALENCE_PARTIAL`.

Owner evidence: Owner-approved current Site-name snapshot/normalization rule; Four-variant Word name/line-wrap acceptance.

Evidence refs: `MainForm.frm:4151`; `Module1.bas:607`; `RecordForm.frm:589-603`; `RecordForm.frm:744`; `legacy/GPs.xlam!WinAPI.bas:504-510 (supplementary version)`.

## VKN — BLOCKED

Legacy expression: `s2, 1, 2`.

Legacy transform: Get_VKN second output s2; Sel_GPs 1/2 and i=2; helper bounds 1..2 writes VKN1/VKN2, not the unnumbered VKN bookmark.

Candidate canonical source: Same dedicated authority atoms as VKNx; abbreviated institution text, not an inspector name.

Ownership: No manufacture enum may be inferred from company names or accepted from a counterfeit Python equality callback.

Null/missing: Missing manufacturing classification or medicine province mapping blocks; vaccine may use declared UNPROVEN geography, never an unknown enum.

Multiple records: Same exact classification/zone selection as VKNx; no independent institution guess for the abbreviation.

Date/time: Not a date field.

Difference: GLP/GMP numbered targets are effective; base VKN is not used by this helper invocation. GMPbb/GSP branch is not applicable even if a similarly named bookmark exists.

Blockers: `MANUFACTURING_CLASSIFICATION_SOURCE_UNPROVEN`, `QDKT_AUTHORITY_PROSE_ACCEPTANCE_UNPROVEN`.

Owner evidence: Canonical classification owner; Owner acceptance of exact abbreviation/full-name pair and variant policy.

Evidence refs: `MainForm.frm:1632`; `MainForm.frm:4157`; `MainForm.frm:4161`; `Module1.bas:626`; `RecordForm.frm:1854-1871`; `RecordForm.frm:1861`; `RecordForm.frm:1865`; `RecordForm.frm:1868`; `RecordForm.frm:280`; `RecordForm.frm:365`; `RecordForm.frm:752`; `backend/app/document/inspection_qd_kt_vba_bookmark_series.py:reconcile_qdkt_i2_bookmarks`.

## VKNx — BLOCKED

Legacy expression: `s1`.

Legacy transform: For Sel_GPs 1/2: Get_VKN detects four vaccine strings in DaychuyenDD, else legacy province index <=32 versus >32; generates full institute prose.

Candidate canonical source: Dedicated manufacture-kind + source-proven province-zone atoms; no canonical classification extraction owner is established.

Ownership: Case/Site manufacturing classification remains unresolved; never infer from facility name, team or free-text scope. Legacy primary entry sets Daychuyen, while Get_VKN reads public DaychuyenDD.

Null/missing: Legacy missing Match index 0 falls into north branch; current unknown classification/mapping blocks. No northern default.

Multiple records: One uniquely mapped province and explicit classification; no first mapping, lexical ordering or current administrative-code substitution.

Date/time: Historical 63-province reference is not a current administrative-date policy.

Difference: Pure authority text and legacy geography helpers exist, but their source atoms are not thereby owner-approved. GMPbb target exists yet branch is not reached; GSP has no target.

Blockers: `LEGACY_PROVINCE_MAPPING_UNPROVEN`, `MANUFACTURING_CLASSIFICATION_SOURCE_UNPROVEN`, `QDKT_LEGACY_PUBLIC_STATE_LIFETIME_UNPROVEN`.

Owner evidence: Approved canonical vaccine/biological classification source and variant applicability; Accepted historical/current geography and exact institute prose.

Evidence refs: `MainForm.frm:1632`; `MainForm.frm:4157`; `MainForm.frm:4161`; `Module1.bas:626`; `Module1.bas:626,637`; `RecordForm.frm:1854-1871`; `RecordForm.frm:1860`; `RecordForm.frm:1864`; `RecordForm.frm:1867`; `RecordForm.frm:280`; `RecordForm.frm:365`; `RecordForm.frm:750-752`; `backend/app/document/inspection_qd_kt_legacy_province_band.py:classify_qdkt_legacy_province_zone`; `backend/app/document/inspection_qd_kt_vkn_authority.py:select_qdkt_vkn_authority`.

## Adversarial evidence matrix

- CROSS_CASE (HIGH): Decision from another Case. Test: `tests/test_inspection_qd_kt_lifecycle_integrity.py::test_cross_case_decision_cannot_be_composed_with_local_site_and_team`. Expected: Reject mismatched source scope. Required evidence: Persisted Case/Plan ownership.

- WRONG_SITE (HIGH): Registered Site association differs. Test: `tests/test_inspection_qd_kt_registered_site.py::test_qdkt_case_uses_only_its_registered_site_address`. Expected: Read only the Case-linked Site; no fallback. Required evidence: Canonical registered Site relation.

- STALE_PROJECTION (HIGH): Scalar projection disagrees or source row is absent. Test: `tests/test_inspection_qd_kt_decision_source.py::test_missing_or_stale_scalar_projection_never_silently_falls_back`. Expected: DECISION_PROJECTION_MISMATCH or missing-source blocker. Required evidence: Matching persisted source row and projection.

- MULTIPLE_DECISIONS (HIGH): Ambiguous decision lineage. Test: `tests/test_inspection_qd_kt_latest_reference.py::test_missing_or_ambiguous_replacement_history_blocks`. Expected: Reject incomplete/branched/circular histories. Required evidence: Owner-approved explicit lifecycle; no MAX/date heuristic.

- MISSING_ATOM (HIGH): Canonical application atom absent. Test: `tests/test_inspection_qd_kt_renderer_contract.py::test_canonical_provenance_negative_paths`. Expected: Block before dispatch; never manufacture values. Required evidence: Matching Case/Application/Site/version source.

- NULL_DEFAULT (HIGH): Missing registered address. Test: `tests/test_inspection_qd_kt_registered_site.py::test_missing_or_unapproved_address_cannot_be_guessed`. Expected: REGISTERED_SITE_ADDRESS_MISSING. Required evidence: Approved registered address; no plan default.

- UNKNOWN_ENUM (HIGH): Unknown geography or counterfeit classification. Test: `tests/test_inspection_qd_kt_transformation_audit.py::test_foreign_classification_cannot_masquerade_as_vaccine`. Expected: Reject invalid enum/type before comparisons. Required evidence: Explicit canonical manufacturing classification.

- DATE_ONLY_TIMESTAMP (HIGH): Date-only/timestamp representation conflict. Test: `tests/test_inspection_qd_kt_renderer_contract.py::test_ambiguous_or_unsupported_date_transform_is_rejected`. Expected: No implicit date-to-timestamp conversion. Required evidence: Owner-approved source date/display policy.

- TIMEZONE (HIGH): Equal instants have different recorded calendar days. Test: `tests/test_inspection_qd_kt_renderer_contract.py::test_equal_instants_with_different_recorded_calendar_days_conflict`. Expected: No server timezone or guessed conversion. Required evidence: Business timezone decision and boundary-case UAT.

- UNKNOWN_PROVINCE (HIGH): No unique legacy province mapping. Test: `tests/test_inspection_qd_kt_legacy_province_band.py::test_unsupported_classification_or_legacy_location_fails_closed`. Expected: LEGACY_PROVINCE_MAPPING_UNPROVEN. Required evidence: Source-proven applicable geography; no alphabetic rule.

- MISSING_MANUFACTURE (HIGH): Manufacturing classification UNPROVEN. Test: `tests/test_inspection_qd_kt_vkn_authority.py::test_unproven_source_classification_never_guesses_institution`. Expected: MANUFACTURE_CLASSIFICATION_UNPROVEN. Required evidence: Canonical classification owner; not company-name guessing.

- TEAM_ORDER (HIGH): Ambiguous or unsorted member order. Test: `tests/test_inspection_qd_kt_team_source.py::test_unproven_source_fails_closed`. Expected: Reject unstable order/identity/role. Required evidence: Explicit ordered roster and draft/version link.

- UNPROVEN_FORMAT (HIGH): Correct DB members do not prove formatted Word strings. Test: `tests/test_inspection_qd_kt_transformation_audit.py::test_all_14_fields_remain_unverified_and_have_complete_audit_dimensions`. Expected: No VERIFIED or legal-equivalence promotion. Required evidence: Title/position/unit/paragraph evidence plus Word UAT.

- MISSING_TARGET (HIGH): VBA attempts target absent from original DOTX. Test: `tests/test_inspection_qd_kt_transformation_audit.py::test_exact_absence_and_numbered_target_facts_are_not_conflated`. Expected: Report source no-op, keep owner blocker. Required evidence: A/B wording/placement or omission acceptance.

- DUPLICATE_TARGET (HIGH): Duplicate physical bookmark name. Test: `tests/test_inspection_qd_kt_dotx_binary_audit.py::test_duplicate_bookmark_names_across_ids_fail_closed`. Expected: Reject ambiguous physical structure. Required evidence: Independent valid primary byte audit.

- FALSE_VERIFIED (HIGH): Audit status/ready flag edited without evidence. Test: `tests/test_inspection_qd_kt_transformation_audit.py::test_committed_report_cannot_self_promote`. Expected: QDKT_TRANSFORMATION_AUDIT_REPORT_DRIFT. Required evidence: Reviewed source changes, owner approval and actual Word UAT.


## Reproduce and limitations

Run `python -m tools.audit_qdkt_source_transformations --format json` or `--format markdown` from repo root. Stdout only; exit 2 always because readiness is blocked. The existing legacy inventory is preserved; this companion projection adds current contract analysis without replacing its source classifications.

Inventory semantic SHA: `17ed8cd21147a0ae4d860700444f5dc59a572acd7d32f18f78776aea600ea279`. Trace semantic SHA: `83b652b4ece582416434700df9c987a33ed811c57d6b576dda2ad6065d731c8f`. Source archive SHA: `6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7`.

Machine report: `artifacts/legacy_audit/inspection_qd_kt_transformation_audit.json` includes all attempted/effective physical names, module hashes, group summaries and deterministic blocker inventory. Effective targets are committed primary binary observations, not a fresh read or proof of Word rendering.

Supplementary helper evidence: `tests/fixtures/inspection_qd_kt_transform_helper_evidence.json`, source binary SHA `52725cba1fd87107814d07da1dbae8d79c77127765018b0daf4b6fe6f44b1b58`. Supplementary add-in source; no invented ZIP helper body or automatic cross-version runtime-binding proof.

A CONTRADICTED status identifies a source/attempt-policy conflict, not proof that a missing bookmark actually changed a Word document. No field is VERIFIED. Source facts and helper regression success do not establish live Case provenance, legal acceptance or Word equivalence.

Process A: No issued reference/date; preserve blank administrative date; no latest decision inheritance.

Process B: Case/Plan-bound lineage is diagnostic; external legal issuance remains unverified.

Required adversarial coverage reuses #191 lifecycle tests (Case/Plan ownership, stale projection, multiple references, no issued reads), #186 renderer/date tests (missing atoms, date-only/timestamp separation, no timezone inference), and existing Site/team/locality/physical gates. New audit tests cover metadata pin drift, duplicate/missing physical targets, unknown/counterfeit classification and self-promoted reports. No production data or Word execution is involved.

Runtime gate hardening pins full reviewed inventory/trace semantic contents and rejects duplicate JSON keys. Updates to assignment/format/owner metadata require explicit source review and new pins. VKN input validation rejects unknown enum/object values while preserving the valid vaccine + UNPROVEN-geography rule; it does not supply a missing canonical manufacture owner.

Remaining owner decisions: legal A/B, wording/placement or intentional omission, current address/locality/name formatting, canonical manufacture classification and geography applicability, roster/title/position/layout evidence, date/timezone policy and external legal issuance. Actual four-variant Word UAT and trusted owner acceptance remain required.

`decision=UNDECIDED`; Word UAT `NOT_EXECUTED`; business timezone `PARTIAL_UNPROVEN_BUSINESS_TIMEZONE`; `ready_to_render=False`. Keep #74 and #144 OPEN.
