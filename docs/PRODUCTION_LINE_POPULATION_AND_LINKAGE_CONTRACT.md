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
Each canonical Case/Certificate UUID must correspond to no more than one legacy
source ID in B6J canonical state. Multiple legacy IDs mapped to one canonical
owner are inconsistent with the writer's row-level legacy-ID ownership fence
and are rejected, even if their target line UUID would be the same. The writer
also rejects resealed duplicate legacy actions or canonical write owners rather
than silently deduplicating them. B6J validates that all source IDs in each
roster-bound candidate have exactly one Case/Certificate action, including
blocked/no-op actions. An omitted or reassigned source is rejected. Summary
counts are verified against the actual actions. Non-candidate legacy rows
remain covered by the independently retained plan file hash, not by candidate
membership.
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
only as fallback.  Missing dated evidence blocks creation. A dated candidate without an eligible
canonical Case/Certificate link target is retained for accounting as
`BLOCKED_NO_ELIGIBLE_LINK_TARGET` and cannot create an orphan ProductionLine.
The writer separately refuses a resealed create action without a
`LINK_TO_NEW_LINE` owner. The immutable plan
stores the selected raw date and source state, uses a plan-scoped UUID, locks
and revalidates every target before one all-or-nothing transaction, and rejects
a second application as stale state.  Date cells use the shared Snapshot V2
Excel-1900 date-only conversion owner.  Before writes, B6J also recomputes the
canonical-state semantic digest through the canonical exporter; any unrelated
migration-relevant Site, Case, Certificate, or ProductionLine drift rejects
the plan before target-level fences or mutations run. B6J is a **missing-link
population**: already-linked Cases/Certificates that match the planned UUID
are explicit no-ops; conflicting existing links are blocked. The sealed plan
validator and row-lock checks independently refuse to replace any non-null
canonical `production_line_id`.


## Independent B6J Plan Approval Digest

The planner prints both `PRODUCTION_LINE_POPULATION_PLAN_SHA256` and
`PRODUCTION_LINE_POPULATION_PLAN_FILE_SHA256`. Retain these values outside
the plan in an immutable review/approval record. The B6J apply CLI requires
`--expected-plan-sha256` and `--expected-plan-file-sha256` for **every**
execution, including rollback dry-run, before database access. Hashes
calculated again from an already edited plan are **not** independent approval.
This strengthens the CLI entrypoint; direct library callers remain responsible
for trusted-plan provenance and remain restricted by the writer's existing
database fences. Neither the digests nor this CLI change authorize a production
or protected rehearsal operation.

## B6K Cutover Handoff and Required Approval Boundaries

The B6K source-dependency matrix must reflect the active B6J planner,
writer, planner CLI and apply CLI owners. For B6J, the legacy snapshot,
canonical-state semantic digest, B6I candidate roster raw/content hashes
and candidate count, actual Alembic revision, exact database identity and
semantic plan SHA all bind the approved run. The **independent** expected
semantic plan SHA and exact plan-file SHA live outside the plan and are
supplied to the CLI. A B6I roster binds candidate membership; it does not
substitute for an explicit physical-identity review decision or permission
to apply. Before any cutover: re-export the canonical state, rebuild and
review source/roster artifacts, replan at the actual target revision,
record both approval digests independently, and verify the authorized
database/mode. A passing CI run proves code behavior, not completion of
human review, source freeze, or authorization to write.

## B6K Read-only Human Review Alignment

B6J checks the B6I **immutable candidate set** but deliberately does not
interpret decisions such as `APPROVE_NEW_PHYSICAL_LINE`,
`MAP_TO_EXISTING_PRODUCTION_LINE`, `DEFER_INSUFFICIENT_EVIDENCE` or
`REJECT_NOT_PHYSICAL_LINE`. Therefore, passing the B6J writer's technical
fences is not proof that a physical-line identity has been approved.

The read-only `tools/audit_production_line_cutover_readiness_b6k.py` compares
one sealed B6J plan to a separately reviewed B6I roster, requiring the
reviewed roster's source/semantic identities, exact candidate universe,
canonical Site/code and legacy source IDs to match the plan. It reports
blocked/unfinished decisions, missing reviewer, reviewed date or reason,
conflicting new-line display codes, conflicting existing-line targets, and
planner-blocked candidates. It also reports **source-action** blockers in
`source_action_findings`: an approved physical-line candidate can still
have a blocked Case/Certificate action, an unexpected candidate no-op, or
an unknown source-action classification. Source actions not bound to a
candidate are still counted when explicitly blocked. The intended
`NOT_APPLICABLE / ALREADY_LINKED_TO_PLANNED_LINE` no-op does not block
**only when the original canonical FK already equals the planned line**;
a resealed no-op label alone is insufficient. Unknown source classifications
(including unbound sources) and writable links missing canonical owners
are also blockers.
The report includes separate `blocked_candidate_count` and
`blocked_source_action_count`; either nonzero blocks the audit CLI.
Invoke it only with independently retained
`--expected-plan-file-sha256` and
`--expected-reviewed-roster-file-sha256`; these must not be recomputed from
unapproved modified files.

The report always contains `"cutover_authorized": false`, even when
`status` is `REVIEW_ALIGNMENT_PASS`. Such a PASS means **only** that reviewed
decisions align with the technical plan. Frozen source provenance, separate
human sign-off, writer-specific external plan approval, database identity,
authorized revision and authorized operating mode remain independent
requirements. No reviewer decision is invented, and this audit never
creates a line, links a Case/Certificate, or grants permission to apply.

## B6H/B6J Revision 0022 Compatibility Boundary

The B6 owner source tables were checked on disposable PostgreSQL across
`20260929_0017 → 20261008_0022`. The approved revision set is **explicit**,
not a minimum version or automatic forward-compatibility rule. The disposable B6 compatibility integration additionally exercises schema
and source-row survival across the upgrade, fresh export and plan at `0022`,
transactional dry-run rollback, apply on a `gxp_b6c_test_*` database, stale
second apply rejection, and rejection of a `0017` plan at `0022`. The B6H
canonical-state exporter records the **actual database revision**; B6J plans
copy it unchanged and bind it into their semantic SHA, roster provenance, and
plan-scoped UUID. The B6J writer checks that **the target revision equals
the sealed plan revision** before reading current canonical state or writing.

An artifact exported at `0017` must not be replayed against `0022`, even
if all Site/Case/Certificate/ProductionLine rows are otherwise identical.
Re-export and re-plan against the actual target revision using the immutable
candidate roster workflow. A later unknown revision remains blocked.

Protected `gxp_legacy_rehearsal` apply/dry-run remains pinned to exact
`20260929_0017` with its existing 386-candidate and SHA authorization.
All non-rehearsal B6J modes, **including rollback dry-run**, remain
disposable-only (`gxp_b6j_test_*` or `gxp_b6c_test_*`). The B6G/B6H/B6J
integration runners further restrict disposable database names to lowercase
ASCII letters, digits, and underscores after their exact prefix, with at most
63 bytes total; no URL delimiters are accepted before `createdb`. A dry-run performs
writes in a transaction before rolling back, so its target guard must be
identical to the non-rehearsal apply guard. **No production apply, dry-run,
or deploy** is authorized here.
