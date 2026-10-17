# B6K ProductionLine Cutover Evidence Handoff

## Scope and strict boundary

This is an **evidence preparation and independent review** checklist, not an
authorization to migrate or apply a B6J writer. B6I human physical-identity
review, B6J technically sealed plan, B6K alignment, independent plan approvals
and target/mode authorization are **separate gates**. Never equate passing CI,
a B6J dry-run, or `REVIEW_ALIGNMENT_PASS` with permission to write.

Protected `gxp_qlcl` and `gxp_legacy_rehearsal` must not be used for
rehearsal or dry-run without their separately authorized contracts. A B6J
dry-run performs writes before transaction rollback. This handoff contains
**no database writer invocation**.

## Artifacts to identify and retain (one run-specific immutable directory)

| Artifact | Owner | Independent evidence required |
| --- | --- | --- |
| Exact Legacy Snapshot V2 JSON | B6H/source owner | Exact-byte SHA256; source identity/freeze record |
| Canonical-state JSON | B6H exporter | Actual database identity, Alembic revision, semantic SHA256, exact-byte SHA256 and source-state fingerprint |
| B6I v2 roster template JSON, evidence JSON, workbook XLSX | B6I workspace | Matching `candidate_set_sha256`, frozen source/semantic identities and workbook provenance |
| Completed workbook and *reviewed* roster JSON | Human reviewer + B6I importer | Named reviewer(s), case-specific reasons and valid `reviewed_at`; independent exact-byte roster SHA256 |
| B6J sealed population plan JSON | B6J planner | Semantic `plan_sha256`, **separately retained exact-byte plan SHA256**, roster raw/content binding |
| B6K alignment report JSON | B6K read-only auditor | Exact-byte plan/roster SHA fields, blockers/findings, `cutover_authorized: false` |
| Approval and operating-mode record outside artifacts | Authorized human decision makers | Signatures/decision reference, approved SHA values, database, revision, allowed mode, approval scope and time |

Do not create human review decisions, external approvals, or source attestations
from software-generated values. Externally retained SHA values must be reviewed
and approved **before** they are used as expected values in the next audit.

## Offline review and planning workflow

These commands describe the file-only path. Use unique output directories and
new filenames each run; CLIs reject existing artifacts. Paths are placeholders
and must be replaced with real, previously verified files. For XLSX import,
select the approved Node/artifact-tool runtime used by the project.

```powershell
# Step A: Input artifacts have already been frozen and independently checked.
$Snapshot = "<frozen-legacy-snapshot-v2.json>"
$State = "<frozen-canonical-state.json>"
$Workspace = "<fresh-empty-B6I-workspace-dir>"
py -3 tools/build_production_line_review_workspace_b6i.py `
  --snapshot $Snapshot --canonical-state $State --output-dir $Workspace

# Step B: Authorized reviewer edits the produced XLSX and records evidence.
# Do not fill decisions automatically. Import to a NEW JSON file:
$Workbook = "<human-completed-B6I-workbook.xlsx>"
$Template = "<B6I-roster-template-v2.json>"
$ReviewedRoster = "<new-reviewed-roster.json>"
py -3 tools/import_production_line_review_workbook_b6i.py `
  --workbook $Workbook --template $Template --output $ReviewedRoster
# Add --node/--artifact-tool-url if the approved bundled runtime requires them.
# Use --existing-production-line-id only for genuinely bound existing UUIDs.

# Step C: Record exact roster SHA after human review, outside the roster.
# SHA computation is not a review/signature and must not auto-approve a file.
Get-FileHash -Algorithm SHA256 $ReviewedRoster

# Step D: Plan against exactly the reviewed roster and frozen sources.
$CandidateSetSHA = "<verified-candidate_set_sha256-from-B6I-template>"
$RosterRawSHA = "<verified-exact-byte-reviewed-roster-sha256>"
$Plan = "<new-sealed-B6J-plan.json>"
py -3 tools/plan_production_line_population_b6j.py `
  --snapshot $Snapshot --canonical-state $State `
  --candidate-set-sha256 $CandidateSetSHA `
  --candidate-set-roster $ReviewedRoster `
  --candidate-set-roster-sha256 $RosterRawSHA --output $Plan

# Step E: Obtain *independent* file-SHA approvals outside the plan.
Get-FileHash -Algorithm SHA256 $Plan
# The planner prints the semantic plan SHA and exact plan-file SHA.
# Reviewer checks source identities, decisions, actions and plan, then signs.

# Step F: Audit exact artifacts using prior independently retained values.
$ApprovedPlanFileSHA = "<externally-approved-plan-file-sha256>"
$ApprovedRosterFileSHA = "<externally-approved-roster-file-sha256>"
$Alignment = "<new-B6K-alignment-report.json>"
py -3 tools/audit_production_line_cutover_readiness_b6k.py `
  --plan $Plan --reviewed-roster $ReviewedRoster `
  --expected-plan-file-sha256 $ApprovedPlanFileSHA `
  --expected-reviewed-roster-file-sha256 $ApprovedRosterFileSHA `
  --output $Alignment
```

The B6K command exits **0** on alignment PASS, **3** when blocked and
**2** for CLI argument errors. Structural/provenance validation errors also
fail closed. A blocked report is preserved for remediation; after human review
changes, rerun the importer, replan, independently reapprove new hashes and
audit to a **fresh** report path. Never edit SHA fields or approval data solely
to make an existing plan pass.

## Mandatory manual release gates

1. **Source freeze**: Confirm Snapshot V2 bytes, canonical-state DB identity
   and actual Alembic revision. The previous disposable revision compatibility
   check through `20261008_0022` is not production authorization.
2. **B6I human identity review**: Every candidate and its source references
   must have an evidence-based decision; `PENDING`, `DEFER`, `REJECT`,
   `SPLIT_REQUIRED`, `CONFLICT` or planner-blocked classifications do not
   create positive cutover approval. Do not infer physical identity from legacy
   `MÃ DC` text, code similarity, or matching Case/Certificate wording.
3. **B6J action review**: Inspect every Case/Certificate source action,
   including unbound sources, no-ops, blocked actions, existing non-null FK
   states, Site/UUID targets and orphan-creation safeguards.
4. **B6K independent alignment**: Require no unresolved candidate or
   source-action blockers for the authorized cutover scope. Even a PASS report
   always retains `cutover_authorized: false`.
5. **Independent approval**: Preserve approved semantic plan SHA and exact
   plan-file SHA, reviewed roster raw/content hashes, reviewer identities,
   approval timestamp, scoped source and target database identity **outside**
   the plan/roster. Revisions or human decisions changed after approval
   invalidate it.
6. **Separate operation authorization**: Named approvers must explicitly
   authorize target database, revision, exact mode and permitted write window;
   the writer's technical safeguards alone do not establish permission.

## Current non-assertions

No real reviewed roster, independent approval record, frozen target database
state, source-action clearance or production cutover permission is supplied
by this document. CI can validate **code behavior**, not that the specific
human/production evidence gates above have been satisfied.
