# ProductionLine Population And Linkage Contract

## Boundary

B6H is discovery and planning only. It creates no `ProductionLine`, changes no
`Case.production_line_id` or `Certificate.production_line_id`, creates no scope
or certificate relationship rows, and has no `--apply` mode.

## Dependency Map

`db.ktra.MÃ DC -> Case.scope_code` and `db.cc.MÃ DC -> Certificate.line_code`
are Phase 2 compatibility/provenance text. `CaseWorkflowService`,
`CatalogReadService`, catalog API/read models, and frontend `line_code` filters
still consume those strings as compatibility context. They must not use them as
ProductionLine IDs or derive lineage/activity from them. B6G adds nullable
foreign keys and empty line/lineage tables, but no runtime writer owns them.

`CaseEvaluationScope` remains the legacy unphased Case aggregate; it is not a
`CaseScopePhase` revision. `CertificateScope` remains version-owned.

## Evidence Hierarchy And Canonicalization

Only reviewed `EXPLICIT_PHYSICAL_LINE_IDENTITY` evidence can make a source
candidate `CREATE_SAFE`. Legacy `MÃ DC` text is `LEGACY_ONLY_SIGNAL`, including
when case and certificate text agree. Canonicalization performs only Unicode
NFKC, trim, whitespace collapse, and uppercase; it never removes punctuation,
tokens, or semantic words. Therefore `A`, `A+C`, `AC`, and `LINE 1A` remain
distinct.

Candidate identity review is scoped to `(legacy site identity, canonical text)`
only for evidence grouping; it is not a claim that this tuple is a permanent
physical-line key or that GxP is/not an identity dimension.

## Linkage And Staleness

Case and Certificate plans are independent. A certificate may use a linked Case
only as corroborating evidence and must never inherit its line. Every future
write candidate must preserve the source site, compatibility text, expected
nullable FK, canonical row/version data when available, and the approved plan
digest. Site equality is mandatory. A changed source, Site, compatibility text,
or target FK must reject a future apply rather than be repaired downstream.
The source-only plan intentionally records canonical Case/Certificate counts as
`NOT_RUN_NO_DATABASE_READ`; a future apply requires a separately reviewed,
read-only canonical-state enrichment before it can construct any action.

## Non-Inference Rules

No `A+C` value proves `A + C -> AC`; B6H produces no transformations without
explicit lineage evidence. Legacy inspection scope is
`LEGACY_UNPHASED_CASE_SCOPE` and cannot be assigned a lifecycle phase. Latest
flags, dates, numbers, and shared sites do not prove certificate replacement or
supersession.

## Future Apply Boundary

A separately approved B6H apply phase would create reviewed lines, preserve
source provenance, link only approved Cases/Certificates in one transaction,
recheck the plan/fingerprints under lock, remain idempotent, and fail closed on
ambiguity. Rollback is limited to the transaction before commit; historical
compatibility text is never removed or overwritten.

## B6J Approved Legacy Population Boundary

B6J is the separately approved migration-only writer for the legacy `MÃ DC`
candidate set.  Its identity is Site-local `(Site, canonical legacy code)`;
cross-Site reuse is normal.  It creates no transformation, scope-lifecycle, or
certificate-relationship records.  A created line's `effective_from` means
`EARLIEST_EVIDENCED_ACTIVE_DATE`, not commissioning: the earliest valid dated
inspection evidence bound to that exact Site/code, with certificate issue date
only as fallback.  Missing dated evidence blocks creation.  The immutable plan
stores the selected raw date and source state, uses a plan-scoped UUID, locks
and revalidates every target before one all-or-nothing transaction, and rejects
a second application as stale state.  Date cells use the shared Snapshot V2
Excel-1900 date-only conversion owner.  Before writes, B6J also recomputes the
canonical-state semantic digest through the canonical exporter; any unrelated
migration-relevant Site, Case, Certificate, or ProductionLine drift rejects
the plan before target-level fences or mutations run.
