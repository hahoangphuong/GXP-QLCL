# C.5e Branch-Aware Evaluation Scope Document Projection Contract

## Decision

The generic Phase 5 payload registry remains an inventory, not the semantic owner for evaluation-scope document fields. Active VBA document paths are branch-specific, so C.5e introduces a dedicated scalar projection owner:

`backend/app/domain/evaluation_scope_document_projection.py`

The projection is derived only from canonical structured scope + persisted taxonomy + `limitation_text`. It does not use historical prose, workspace `summary_text`, or `unkeyed_entries` as semantic input.

## VBA variable reconstruction

The contract reconstructs the `RecordForm.GetTT_Ktra` scalar chain deterministically:

- `DC_cu` / `DaychuyenDD`: VBA-readable canonical structured scope with the limitation excluded;
- `GHanDC`: canonical `limitation_text`, with the final `GetData` beta/Lactam normalization;
- `DaychuyenX`: exact `GetTT_Ktra` star removal and `vbCrLf` → `; ` cleanup over `DaychuyenDD`;
- `DaychuyenLF`: exact star removal over `DaychuyenDD`;
- `RipDot`: removes only one final period after VBA-style trim.

## Branch-specific scalar writes

The owner emits only fields actively written by the requested VBA document branch:

- `INSPECTION_BBTD_HOSO_DK`: `Daychuyen = DaychuyenDD`.
- `INSPECTION_QD_KT`: no scalar scope bookmark write.
- `INSPECTION_KE_HOACH_KT`: `Daychuyen = DC_cu`; `GioiHanPvi = GHanDC`, default `Không`.
- `INSPECTION_BB_KT`: `Daychuyen = DaychuyenLF`; `GhPviDG` uses assessment-label rewrite and default `Không`; `GhPviCN` uses `GHanDC` and default `Không`.
- `INSPECTION_PT_PCT`: `Daychuyen = RipDot(DaychuyenX)`; `Daychuyen2 = DaychuyenLF`; `GioihanPvi = GHanDC`.
- `INSPECTION_PT_CT`: same fields only when `CopyPT=False`; no scalar write when `CopyPT=True`.
- `RISK_MANAGEMENT_WORKSHEET`: `Daychuyen = DaychuyenDD`.
- `ASSESSMENT_MINUTES`: exact bookmark casing `DayChuyen = DaychuyenDD`; `GioiHanPvi` uses assessment-label rewrite and default `Không`.
- `CERTIFICATE_DECISION`: no active scalar scope write; the legacy `Daychuyen` assignment is commented out and remains inactive.

Unsupported document families fail closed.

## Explicitly separate certificate-detail path

`Input_DC_to_CC` is not a scalar bookmark projection. It iterates structured taxonomy rows and copies formatted taxonomy bookmark content into certificate detail regions, including row-specific custom-description behavior. It remains a separate C.5e sub-slice and may not be replaced by compact `summary_text` or this scalar projection.

## Integration boundary

This slice proves the scalar semantic contract only. Production document payload integration is intentionally separate so the adapter can be tested family-by-family against existing Phase 5 payload and template contracts without rewriting the generic inventory registry by inference.
