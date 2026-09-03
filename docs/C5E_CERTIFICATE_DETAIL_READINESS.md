# C.5e Certificate Detail (`Input_DC_to_CC`) Readiness Gate

## Decision

The scalar C.5e path is already integrated. Certificate-detail generation remains a separate semantic path and is **not yet authorized for implementation** from the durable repository evidence currently available.

The gate intentionally returns:

`BLOCKED_PENDING_EXACT_VBA_AND_TEMPLATE_EVIDENCE`

This is a safety/evidence gate, not a regression in C.5d.2 or the C.5e scalar integration.

## Why it stays separate

The compact workspace summary and the branch-aware scalar document projection are text projections. The certificate-detail path is different: legacy behavior is known to operate on structured taxonomy/detail content and Word bookmark/row structure. Therefore none of these are authorized substitutes:

- workspace `summary_text`;
- historical `rendered_prose`;
- the C.5e scalar projection;
- `unkeyed_entries`;
- the commented `Input_DC_to_CC2` body.

## Current durable evidence

`docs/VBA_FUNCTION_MAP.md` records `Input_DC_to_CC2` as a **commented legacy variant**. It does not retain the exact active `Input_DC_to_CC` body.

`artifacts/phase5/template_registry.curated.json` registers `CERTIFICATE_ISSUANCE_WORD`, but its current bookmark list is the general-information surface (`TenCoso`, addresses, dates, WHO/PIC/S/OECD deletion markers, etc.). It does not durably define the taxonomy-detail destination rows/bookmarks used by `Input_DC_to_CC`.

`backend/app/document/docx_template_render.py` supports deterministic scalar bookmark replacement and generic bookmarked table-row cloning. That capability is not, by itself, proof that the legacy certificate-detail row-copy/formatting semantics are reproduced.

## Required evidence before port

The next implementation slice must first retain sanitized, reviewable evidence for:

1. the exact active `Input_DC_to_CC` procedure body and directly called helpers;
2. the exact certificate template row/bookmark structure consumed by that procedure;
3. row-level mapping from canonical selected taxonomy node/custom description to destination row/bookmark behavior;
4. formatting/copy behavior that must survive the server-side DOCX renderer.

Only after those are captured should a detailed projection owner be implemented and connected to `TableRegionRenderInput` or a more specific render primitive.

## Invariants

- No use of `unkeyed_entries`; they remain legacy skipped-by-design.
- No reverse inference from prose back into taxonomy nodes.
- No fallback to compact summary for certificate detail.
- No treating commented VBA as active semantics.
- Unsupported or ambiguous source/template mappings fail closed.
