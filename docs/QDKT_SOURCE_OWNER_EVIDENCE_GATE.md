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
