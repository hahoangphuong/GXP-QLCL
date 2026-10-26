# QĐKT i=2 source owner evidence gate

This guard reads the pinned `artifacts/legacy_audit/inspection_qd_kt_input_provenance.json` from the traced `RecordForm.CreateFile(i=2)` path. It is an **offline evidence consistency check**, not renderer readiness.

| Source bookmark group | Classification | Safety rule |
| --- | --- | --- |
| Fulldate, Diadiem, Diadiemx, Diachicoso, QDKT, NgayQDKT, VKNx, VKN | 8 OWNER_BLOCKED | Modern Date, Site, InspectionDecision and team columns must not silently substitute VBA input sources |
| Tencoso, HsDK, NgaynopHsDK, TT3x, TT3Del, TTx | 6 OWNER_PARTIAL | Source path identified, but exact owner/value/display contract remains unresolved |

`inspect_qdkt_source_provenance()` checks the 14 logical operation symbols, active source trace metadata, source ZIP pin, and status assignments. Those symbols are not all literal physical bookmark names: the VBA helper can expand a logical base name to numbered targets. Any attempt to silently reclassify an owner, drop an operation symbol, or clear source semantics fails closed. Test fixtures mutate the artifact to prove these guards.

A later source adjudication must update the verified legacy trace, document exact modern owner, transformation, template-specific and Word-visual acceptance evidence, and replace this intentionally conservative gate through review. A status change alone cannot enable creation. In particular `ready_to_render=False` and Issue #74 remain unchanged; there is no typed QĐKT POST, no storage mutation, and no approval assertion.


## Guard cho thao tác VBA thực tế ở nhánh i=2

Bộ kiểm tra còn pin vị trí lệnh, loại thao tác và khả năng tiếp cận trong nhánh `i=2` cho cả 14 bookmark. Phân biệt `WRITE` với `DELETE` (`TT3Del`), `REACHABLE_I2` với `CONDITIONAL_I2`; các thao tác của nhánh `i=3/4` không thể thay thế thao tác đang hoạt động. Chuỗi biến nguồn phải có bước truy vết cho từng biến được khai báo. Các fixture cố tình thay đổi nhánh, dòng lệnh, thao tác, biểu thức và chuỗi nguồn để chứng minh fail-closed.

**Giới hạn chứng cứ:** gate chưa so sánh từng biểu thức với binary VBA gốc, chưa kiểm tra từng bookmark trong bốn file DOCX và chưa chứng minh dữ liệu ORM hiện đại tương đương. Vì vậy chỉ là tính nhất quán của inventory đã kiểm kê; mọi trạng thái owner vẫn blocked/partial, không tạo payload hoặc mở renderer.


## VBA numbered bookmark series parity (QĐKT `i=2`)

Direct source `legacy/GXP-VBA code.zip!RecordForm.frm` proves the targeting
algorithm. `Replace_Bookmark` lines 589–603 uses series mode only when
`(i >= 0) And (j > 0)`, loops inclusively `For k = i To j`, and builds
`bm & IIf(k = 0, vbNullString, k)`. Otherwise it addresses the unnumbered
`bm`. The helper is under `On Error Resume Next`: a missing generated target
does not terminate the loop, and the same `txt` expression is assigned to
every target that exists. `UpdateBookmark` lines 604–622 uses the same naming
loop but re-adds each bookmark after assignment; QĐKT `CreateFile(i=2)` calls
`Replace_Bookmark`, not `UpdateBookmark`.

The actual route is `Module1.bas:595–651` (`CreateFile(..., 2, ...)`) →
`RecordForm.frm:1702–1778` → `Get_Tpl` case 2 at lines 666–669 →
`Tao_QDKT_KHKT_BBKT` at lines 739–817. The read-only resolver in
`inspection_qd_kt_vba_bookmark_series.py` models only the source-proven i=2
target selection and intersects it with existing physical names. It does not
create a missing bookmark or write a DOTX/DOCX.

| Logical operation | VBA target expression | Operation / condition in i=2 | GLP | GMP | GMPbb | GSP |
| --- | --- | --- | --- | --- | --- | --- |
| `Tencoso` | `Tencoso1` … `Tencoso8` | WRITE, common, source `TenCtydd` (line 744) | `1,2,3` | `1,2,3` | `1,2,3` | `1,2,3` |
| `Diadiemx` | `Diadiemx1` … `Diadiemx3` | WRITE, common (line 746) | `1,2,3` | `1,2,3` | `1,2` | `1,2` |
| `VKNx` | exact `VKNx` | WRITE only when `Sel_GPs=1 or 2` (line 751) | exact | exact | branch not run | branch not run |
| `VKN` | `VKN1`, `VKN2` | WRITE only when `Sel_GPs=1 or 2` and `i=2` (line 752) | `1,2`; physical unnumbered `VKN` is not targeted | same | branch not run, although physical `VKN`/`VKNx` exist | branch not run; their absence is expected |
| `TTx` | `"TT" & (k+1) & "x"` | WRITE while `k<=1` and within `Ds_TTV` (lines 754–758); this is a separate dynamic expression, not the series helper | `TT1x`,`TT2x` | same | same | same |
| `TT3x` | exact `TT3x` | conditional WRITE when a third member exists (lines 760–765) | exact | exact | exact | exact |
| `TT3Del` | exact `TT3Del` | conditional DELETE otherwise (line 766) | exact | exact | exact | exact |

The values in the four GxP columns are the effective targets present in the
four checksum-pinned DOTX files; missing attempted targets are legacy no-ops.
In particular, absence of exact `Tencoso` is **not** a missing-bookmark defect.
The common i=2 call attempts only `Tencoso1..8`; the additional
`Tencoso4..10` call at line 792 belongs to `i=4` and is not merged into this
contract. The observation fixture continues to report literal exact-name
absence, but that fact is no longer interpreted as failed VBA target parity.

This closes only physical target-selection evidence. It does not prove the
modern owner or value of `TenCtydd`, location, authority, team prose, or any
other business input. All OWNER_BLOCKED/OWNER_PARTIAL classifications and
`ready_to_render=False` therefore remain unchanged.


## Case workspace readiness diagnostics (read-only)

`inspect_qdkt_case_readiness` emits stable machine-readable blocker codes
`QDKT_BOOKMARK_OWNER_BLOCKED_<UPPER_BOOKMARK>` for all eight blocked and
`QDKT_BOOKMARK_OWNER_PARTIAL_<UPPER_BOOKMARK>` for all six partial
provenance owners, in addition to existing Case/site/team blockers.
The UI may display these identifiers as unresolved provenance evidence;
it must not treat them as user-editable fields or approval confirmations.

If the pinned evidence inventory cannot be verified, readiness reports
`QDKT_BOOKMARK_PROVENANCE_UNVERIFIED` rather than the presumed individual
owner classifications. This does **not** populate any bookmark and cannot
enable the renderer or issued-decision API. The gap requires source/Word
adjudication and four-template parity tests before changing owner status.


## Independent captured VBA trace reconciliation

The owner inventory is now reconciled against the separately captured
`inspection_qd_kt_vba_trace.json`: the pinned source ZIP checksum, exact
`i=2` call chain, and every recorded operation of all 14 physical bookmarks
(including unreachable i=3/i=4 operations) must agree in order and in
expression, branch predicate, operation kind, line number, and reachability.
A mismatched or missing trace blocks Case readiness with
`QDKT_BOOKMARK_PROVENANCE_UNVERIFIED` through the existing gate.

This detects an inventory edit that retained an OWNER_BLOCKED classification
while silently changing the claimed VBA mapping. Both JSON artifacts remain
derived audit evidence of the same ZIP, not independent physical-source
verification; no DOTX binaries are validated here and no owner is promoted.


## Case GxP-to-template manifest preflight

The read-only Case QĐKT readiness now checks the Case's persisted
`gxp_type` against the four declared QĐKT template asset records
(`GMP`, `GLP`, `GMPbb`, `GSP`) through the existing locator and
checksum-format contract. Unsupported GxP or an invalid manifest yields
`QDKT_CASE_GXP_TEMPLATE_CONTRACT_UNVERIFIED`; no guessed template fallback
is allowed. Missing Case identity retains its existing Case blocker.

This verifies **manifest metadata only**. It does not read, hash or prove
the underlying four DOTX binaries. It does not establish a typed bookmark
mapping, permit document generation, or modify persisted business data.


## Offline DOTX binary evidence collector

`backend.app.document.inspection_qd_kt_dotx_binary_audit` inspects **supplied
local bytes**, not a template manifest alone. It streams SHA-256, checks the
declared per-GxP digest, opens `word/document.xml`, inventories Word bookmark
start/end pairs and rejects malformed or missing ZIP/XML. The four-GxP entry
point requires all four declared files and fails if any is missing or altered.

No legacy binary was provided or read in this code change; tests use explicitly
synthetic DOTX-shaped ZIP fixtures. A passing fixture does not establish actual
template parity. `binary_checksum_verified` can only be true for an individual
supplied file with an exact declared digest; `bookmark_owner_parity_verified`
and `ready_to_render` remain **false**. The observed bookmark names are
evidence for manual/source-backed adjudication, not assumed mappings to typed
payload or an authorization to issue a decision. No backend route, write, NAS,
migration or production action invokes this collector.


## DOTX package-integrity refinement

The offline binary collector now also validates the Open Packaging Conventions
`[Content_Types].xml` declaration for `/word/document.xml`: it must be the
Word **template** content type (not an ordinary DOCX document). Duplicate
bookmark names with different identifiers are rejected, not collapsed into a
misleading inventory. These checks run only after the exact binary checksum
matches; tests use synthetic packages. They do not establish that a source
legacy template or bookmark payload matches Case-owned business data.
