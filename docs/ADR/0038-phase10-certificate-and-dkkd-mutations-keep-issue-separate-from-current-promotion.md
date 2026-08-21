# ADR 0038: Phase 10 Certificate and DDKD Mutations Keep Issue Separate From Current Promotion

## Status
Approved

## Context
Legacy VBA proves that certificate and DDKD workflows do not treat row creation, issue metadata entry, and promotion to current/effective as the same business event.

For GPs certificates:
- successor rows can be created first
- issue metadata can be filled later
- `Replace_CC` promotes a candidate only after date validation against the current active row

For DDKD:
- successor rows can also exist before they become current
- `CapNhat_DDK` performs a separate promotion gate using issue-date ordering against the current active row

Phase 10 already established audit-first case and inspection mutations. The remaining gap was certificate issuance/update behavior.

## Decision
- Add explicit mutation routes for:
  - certificate issue/create
  - certificate latest-version update
  - certificate promote-current
  - DDKD issue/create
  - DDKD latest-version update
  - DDKD promote-current
- Keep issue/create separate from current promotion for both artifact families.
- Make newly issued certificate and DDKD records start with `latest_flag = false`.
- Require explicit promotion to make a candidate current/effective.
- For GPs certificates, promotion compares the candidate issue date against the current active certificate of the same `site_id + certificate_type` baseline.
- For DDKD, promotion compares the candidate issue date against the current active DDKD row for the same site.
- Keep all mutations role-gated to `manager` and `admin`.
- Keep all mutations audit-first.
- Only promotion writes the workflow-level `certificate_issued` inspection event for case-backed GPs certificates.

## Consequences
### Positive
- Phase 10 now covers the core business-write surface needed before frontend work.
- The target app preserves the legacy distinction between issued-successor creation and current-state promotion.
- Administrative/non-case-backed certificate issuance remains supported without forcing a fake case link.

### Negative
- Current schema baseline still uses `latest_flag` as the active/current marker and does not yet persist full lineage/status-event tables.
- GPs promotion is currently gated by `site_id + certificate_type`, which is narrower than legacy scope-aware comparison and should later tighten when scope projections are first-class.

## Follow-up
- Phase 11 should attach document workflow endpoints to these audited business artifacts rather than mutating files directly.
- A later schema pass should add first-class lineage/status-event persistence for certificates and DDKD as already described in `docs/TARGET_DATA_MODEL.md`.
