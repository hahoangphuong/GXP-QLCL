# ADR 0031: Fail-Closed Current Projection Conflict Handling

## Status
Proposed

## Date
2026-08-14

## Context
Legacy current-state behavior is not a strict one-row invariant.

Audited workbook evidence now proves:
- `db.cc` contains duplicate current keys caused by multiple current rows sharing the same current projection key when `MÃ DC` is blank.
- `db.ktra` contains duplicate current keys where:
  - a completed row and a pending row can both remain current; or
  - two completed rows can both remain current.

Therefore, a target projection such as `current_certificate_projection` or `current_case_projection` cannot safely assume that every business key yields exactly one current source row during migration or reconciliation.

## Decision
- Current-state projections in the target system must fail closed on non-unique current candidates.
- Projection refresh logic must not silently pick a winner from multiple eligible rows.
- The target design must expose an explicit conflict surface, for example:
  - `current_projection_conflict`
  - or an equivalent anomaly/reconciliation table
- Conflict records must preserve at least:
  - projection type
  - evaluated business key
  - candidate source row identifiers
  - detection timestamp
  - adjudication status

## Alternatives considered
### Silently pick the newest row
- Rejected because legacy evidence does not prove newest-row-wins is always the real business rule.

### Silently pick the row with the richest downstream linkage
- Rejected because this would hide real legacy ambiguity and would conflate reconciliation heuristics with authoritative business policy.

### Import only one row and discard the rest
- Rejected because migration must preserve source truth and produce reconciliation evidence.

## Consequences
Positive:
- Target read models stay honest about unresolved legacy ambiguity.
- Operators can review and adjudicate conflicts explicitly.
- Migration cutover rules can evolve without destroying source evidence.

Negative:
- Projection refresh and downstream read paths must handle a third state beyond success or missing:
  - conflict
- Additional reconciliation workflow is required before some records can be treated as authoritative current state.

## Migration/backward compatibility
- All legacy source rows can still be imported unchanged.
- The conflict surface is additive and does not require changing stable legacy IDs.
- Current-state consumers must be prepared for unresolved-conflict outcomes during migration phases.

## Security/data implications
- Avoids hidden destructive data collapse during migration.
- Preserves auditability for operator adjudication.

## Validation
- Proven by:
  - [CURRENT_LOOKUP_RECONCILIATION.md](/D:/GXP-QLCL/docs/CURRENT_LOOKUP_RECONCILIATION.md)
  - [DUPLICATE_CURRENT_ANALYSIS.md](/D:/GXP-QLCL/docs/DUPLICATE_CURRENT_ANALYSIS.md)
