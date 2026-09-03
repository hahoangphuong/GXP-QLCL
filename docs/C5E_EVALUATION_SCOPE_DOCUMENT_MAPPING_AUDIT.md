# C.5e Evaluation Scope → Document Mapping Audit

## Decision

C.5d.2 is accepted and production compact-summary ownership is now the VBA-derived renderer. That does **not** authorize reusing `summary_text` for Word/document fields.

C.5e production document-scope mapping is currently **BLOCKED** pending a branch-aware projection contract.

## Source-derived findings

Active `RecordForm.frm` uses different scope projections by document path:

- `Tao_BBTD`: `Daychuyen <- DaychuyenDD`.
- `Tao_QDKT_KHKT_BBKT(i=2)` / inspection decision: none of `Daychuyen`, `GhPviDG`, `GhPviCN`, `GioiHanPvi` is actively written.
- `Tao_QDKT_KHKT_BBKT(i=3)` / inspection plan: `Daychuyen <- DC_cu`; `GioiHanPvi <- GHanDC`, defaulting to `Không`.
- `Tao_QDKT_KHKT_BBKT(i=4)` / inspection minutes: `Daychuyen <- DaychuyenLF`; `GhPviDG` is the assessment-labeled limitation with default `Không`; `GhPviCN` is the certificate limitation with default `Không`.
- `Tao_PT_PCT_CT`: `Daychuyen <- RipDot(DaychuyenX)`, `Daychuyen2 <- DaychuyenLF`, `GioihanPvi <- GHanDC`; for CT with `CopyPT=True`, this branch is bypassed.
- `Tao_BB_QLRR`: `Daychuyen <- DaychuyenDD`.
- `Tao_BB_Danhgia`: direct bookmark writes include `DayChuyen <- DaychuyenDD` and `GioiHanPvi <- assessment-labeled limitation`.
- `Tao_QD_CapCC`: the apparent `Daychuyen <- DaychuyenX` write is commented out and is not active semantics.

`Input_DC_to_CC` is a separate detailed certificate path. It parses each `§` block, loads canonical taxonomy nodes, copies taxonomy bookmark rows, appends custom descriptions with row-specific rules, and optionally writes translated content. This path cannot be replaced by the compact summary renderer.

## Why the current generic Phase 5 registry is not sufficient

The existing registry is procedure-level. It therefore cannot distinguish `i=2`, `i=3`, and `i=4` inside `Tao_QDKT_KHKT_BBKT`. It also contains evidence of commented-out writes and misses at least one direct active bookmark assignment. Consequently it is useful as an inventory, but not yet as the semantic owner for evaluation-scope document payload values.

## Next safe slice

Implement a **branch-aware document-scope projection contract** that takes canonical `CaseEvaluationScope` + persisted taxonomy version and emits only the fields authorized for the requested document family/variant. It must:

- never use historical prose as an oracle;
- never pass `unkeyed_entries` into projection;
- never reuse compact `summary_text` where VBA used a different projection;
- preserve exact defaulting and label-rewrite behavior per family;
- keep certificate detailed rendering separate from scalar bookmark payloads;
- fail closed for unsupported GxP/document paths.
