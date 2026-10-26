# QĐKT i=2 source owner evidence gate

This guard reads the pinned `artifacts/legacy_audit/inspection_qd_kt_input_provenance.json` from the traced `RecordForm.CreateFile(i=2)` path. It is an **offline evidence consistency check**, not renderer readiness.

| Source bookmark group | Classification | Safety rule |
| --- | --- | --- |
| Fulldate, Diadiem, Diadiemx, Diachicoso, QDKT, NgayQDKT, VKNx, VKN | 8 OWNER_BLOCKED | Modern Date, Site, InspectionDecision and team columns must not silently substitute VBA input sources |
| Tencoso, HsDK, NgaynopHsDK, TT3x, TT3Del, TTx | 6 OWNER_PARTIAL | Source path identified, but exact owner/value/display contract remains unresolved |

`inspect_qdkt_source_provenance()` checks the exact 14 physical names, active source trace metadata, source ZIP pin, and status assignments. Any attempt to silently reclassify an owner, drop a bookmark, or clear source semantics fails closed. Test fixtures mutate the artifact to prove these guards.

A later source adjudication must update the verified legacy trace, document exact modern owner, transformation, template-specific and Word-visual acceptance evidence, and replace this intentionally conservative gate through review. A status change alone cannot enable creation. In particular `ready_to_render=False` and Issue #74 remain unchanged; there is no typed QĐKT POST, no storage mutation, and no approval assertion.


## Guard cho thao tác VBA thực tế ở nhánh i=2

Bộ kiểm tra còn pin vị trí lệnh, loại thao tác và khả năng tiếp cận trong nhánh `i=2` cho cả 14 bookmark. Phân biệt `WRITE` với `DELETE` (`TT3Del`), `REACHABLE_I2` với `CONDITIONAL_I2`; các thao tác của nhánh `i=3/4` không thể thay thế thao tác đang hoạt động. Chuỗi biến nguồn phải có bước truy vết cho từng biến được khai báo. Các fixture cố tình thay đổi nhánh, dòng lệnh, thao tác, biểu thức và chuỗi nguồn để chứng minh fail-closed.

**Giới hạn chứng cứ:** gate chưa so sánh từng biểu thức với binary VBA gốc, chưa kiểm tra từng bookmark trong bốn file DOCX và chưa chứng minh dữ liệu ORM hiện đại tương đương. Vì vậy chỉ là tính nhất quán của inventory đã kiểm kê; mọi trạng thái owner vẫn blocked/partial, không tạo payload hoặc mở renderer.


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
