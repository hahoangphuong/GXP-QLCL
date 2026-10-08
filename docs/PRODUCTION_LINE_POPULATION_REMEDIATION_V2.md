# B6H V2 ProductionLine Remediation Readiness

## Boundary

B6H V2 is read-only. It exports canonical state through an explicit PostgreSQL
READ ONLY transaction, groups legacy compatibility text for review, validates a
reviewed physical-identity roster, and re-plans. It has no apply command and
creates no `ProductionLine`, link, transformation, scope lifecycle, or
certificate relationship row.

## Authoritative Inputs

Every plan binds the exact Snapshot V2 SHA256, canonical-state semantic JSON SHA256 (or
`null` when the export has not run), roster SHA256 (or `null`), and planner
version. The canonical-state format is `production-line-canonical-state/v1` and
requires database identity, exact Alembic `20260929_0017`, source-state
fingerprint, UUID-form canonical IDs for Sites, lines, Cases, Certificates and
transformations, and explicit
physical evidence. The roster format is
`production-line-physical-identity-roster/v1`.

`canonical_state_sha256` and `physical_identity_roster_sha256` mean SHA256 of
canonical semantic JSON, not source-file bytes. `content_sha256` remains each
artifact's deterministic local integrity digest. The exporter also reports
`CANONICAL_STATE_FILE_SHA256` solely for exact serialized-file transport
integrity; it must never be copied into planner or roster provenance.

`MÃ DC`, `Case.scope_code`, and `Certificate.line_code` remain compatibility
text. Link records preserve their exact raw source values separately from the
NFKC/trim/collapse/uppercase grouping value. GxP context is normalized by the
shared Phase 2 `normalize_inspection_gxp_type` owner and is never line identity.
The raw value is used by a future
stale-plan fence; canonical text is never substituted for it.

## Review Workflow

1. Run the canonical-state exporter on the rehearsal VM with an explicit local
   PostgreSQL URL and its enforced READ ONLY transaction.
2. Generate the template roster from the discovery artifact; it contains every
   candidate and only `DEFER_INSUFFICIENT_EVIDENCE` decisions initially.
3. A reviewer chooses an explicit action and reason. `APPROVE_NEW_PHYSICAL_LINE`
   has no preallocated line ID; `MAP_TO_EXISTING_PRODUCTION_LINE` must reference
   an exported same-Site line.
4. Re-plan using the exact canonical-state and roster files. Unknown/stale or
   altered candidates, duplicate decisions, cross-Site mappings, unapproved
   items, and unsupported actions fail closed.

`SPLIT_REQUIRED`, `CONFLICT`, and `DEFER_INSUFFICIENT_EVIDENCE` are never
writable. Review priority tags are triage hints only and never prove a physical
identity.

## Closed-Contract Audit

B6H V2 does not modify B6D, B6E, or B6F decisions. Their B6G wording in the
working tree is an inventory clarification: migration `0017` created only
empty expand-only structures and did not authorize a runtime or migration
writer. This B6H V2 source bundle excludes those pre-existing documents.

## Next Gate

Until a read-only rehearsal canonical-state export and human-reviewed roster
exist, B6H remains `B6H_REMEDIATION_REQUIRED`; it is not an apply authorization.
