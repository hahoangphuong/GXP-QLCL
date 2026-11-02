# Release candidate compatibility and operator preflight

Version2.0 — 2026-11-02. This consolidates the four owner documents from local
commit `423a46c85a708d7bbdf56ff4446b622e8f0052bd` onto audited main
`7c226ad53e4dcaa05886a7f0e77ee8f9ce79974f`. Only documentation is changed.
No deployment, migration, backup/restore, scheduler/OAuth change, real-environment
write or NAS operation is authorized. Google accounts/roles and authenticated
UAT/write scope remain unapproved; do not ask for credentials or record identities.

## Current source and runtime — 2026-11-02

| Item | Evidence/status |
|---|---|
| Audited executable source | `7c226ad53e4dcaa05886a7f0e77ee8f9ce79974f` — SOURCE_VERIFIED |
| Baseline frontend tree | `4a6f6677796fa3a38256818d9fb226aca62ff55e`, identical application source to PR253 |
| Baseline backend tree | `1800c6d316ec22e5a7271aea9ed19e1e42ecbc8e` — SOURCE_VERIFIED |
| Migration tree/head | `bd9fdb502df1aa7e9345682b3d3a7622b39e187d` / `20261101_0027` — SOURCE_VERIFIED |
| Baseline CI | [41363691990](https://github.com/hahoangphuong/GXP-QLCL/actions/runs/41363691990), exact7c226ad, six required jobs SUCCESS |
| Runtime metadata | Fresh public JSON reports `97182e58c3a673938d1b263c7eeaab41d28147b4`, `google_oidc`, `gxp_legacy_rehearsal` — RUNTIME_VERIFIED as reported metadata only |
| Runtime schema | Reports actual=deployed-expected `20261012_0023`; candidate requires0027 — INCOMPATIBLE; physical DB/schema objects NOT_VERIFIED |
| Runtime executable/frontend Git | NOT_VERIFIED; neither metadata nor a JS digest attests the executable archive |
| Runtime JS | `/assets/index-COeZJt9i.js`, SHA256 `54530256db621527e9d17ed546fb04bff3a64a711a53cf963184903279b6ba99` — asset RUNTIME_VERIFIED, different from candidate |
| Candidate build JS | `/assets/index-fr5rTWgE.js`, SHA256 `ae2eac6b5157ee38c84e39bb1e5d3d4ec7a5b355530ac0a53434eb2336d08000`; application build COMPATIBLE within local/CI scope |
| Browser origin | Fresh unauthenticated Edge observes `https://gxp.qlcl-dav.cc`; GIS loads; OAuth Web-client type/authorized origin NOT_VERIFIED |
| Real Google A/B | AUTHENTICATED_UAT_BLOCKED; accounts, role matrix and permitted synthetic/write scope absent |

Health checks are JSON `/api/healthz`, `/api/readyz`, `/api/app/status`200 and
no-bearer `/api/auth/me`401. Unprefixed health paths return SPA HTML and cannot
attest API readiness. No protected rehearsal record or credential was accessed.

**Exact-source rule:**7c226ad is the audited base, not automatic approval for the
documentation consolidation's final commit. Adding these QA documents changes
the full `frontend/` Git tree even though application JS is unchanged. Gate0 must
resolve the final consolidation PR HEAD/merge SHA, its exact six-job CI and its
actual frontend/backend trees from Git/GitHub evidence. Never reuse the old
frontend tree pin, assume cross-head overlay is deployable, or bypass the existing
exact-source gate. The final tested/merge manifest is recorded outside Git at
`.codex/evidence/release-candidate-consolidation-20261102/completion.md` to avoid
self-referential commit hashes. Any later source drift requires a fresh review.

The backend source gate compares **all tracked non-frontend paths**, not only
`backend/`. This PR also changes `docs/LEGACY_VBA_EXCEL_PARITY_STATUS.md`; keeping
the base backend pin can therefore fail even with an unchanged backend subtree.
Both complete source pins require review for the final candidate. Read-only
diagnostics confirmed rejection of an old frontend pin and an old non-frontend
pin; self-comparison matches but is explicitly **not operator approval**.

### Operator receipt and read-only commands

Keep a sanitized receipt containing: exact candidate/tested/merge SHA and CI URL;
candidate frontend/backend/full trees; approved frontend and backend source SHAs;
reviewer/approval reference (aliases, no identities/secrets); environment alias,
reported and independently attested runtime/physical DB/schema; asset digest;
backup freshness/checksum/restore evidence references; Gate0–6 results and explicit
permitted UAT actions. Empty or conflicting approval fields keep the gate blocked.

From a reviewed checkout, these are read-only command templates. Populate the
three SHA arguments from an actual operator approval; never treat a self-pin
diagnostic, a base hash in this document or a CI overlay as that approval:

```bash
python -m tools.verify_rehearsal_release_sources --repo "$REVIEWED_REPO" \
  --target-sha "$CANDIDATE_SHA" \
  --approved-backend-sha "$APPROVED_BACKEND_SHA" \
  --approved-frontend-sha "$APPROVED_FRONTEND_SHA"
```

Require exit0 and `REHEARSAL_SOURCE_EXACT_MATCH`; any failure is STOP, never an
instruction to change the gate. Separately, on the authorized VM or a complete
operator snapshot, the existing active-baseline tool accepts
`python -m tools.audit_active_release_baseline_readonly --root "$VM_ROOT" --expected-sha "$EXPECTED_ACTIVE_SHA"`.
It inspects source metadata/symlinks/artifacts only and cannot certify DB restore.
For an already provided local dump/sidecar, the existing offline checker accepts
`python -m tools.audit_existing_pg_backup_pair_readonly --backup "$EXISTING_DUMP"`.
Do not download a dump, access GCS/NAS or run restore under this audit. These last
two checks were not run against VM/real backup files; operator evidence is absent.

## Backend changes preserved; no frontend feature activation

PR259 schema0027, PR260 PostgreSQL immutability, PR261 UNRESOLVED intake, PR262
canonical UUIDv4 actor/UTC timestamps and PR263 DB permission enforcement are
upstream backend work, preserved without edits. Intake now requires canonical
active AppUser and a canonical database grant for `gmp.coverage_evidence.intake`.
That permission is not granted by the default role map; even a synthetic admin
role is not a grant. Caller-supplied roles cannot substitute for the DB check.

Source search finds no frontend UI/request path or HTTP router exposing intake,
no VERIFIED approval API and no new default permission. UNRESOLVED review evidence
does not permit relinking a Case across Sites, promote a certificate or replace
runtime link validation. No UI fallback/feature/action is introduced. Issue6 stays
open; existing HTTP409 semantics and canonical UUID/version ownership are intact.

## Cutover preflight — Gate0 through Gate6

Gate results distinguish source evidence, publicly reported runtime metadata and
operator-only attestation. A PASS for one subcheck cannot make the whole gate PASS.

| Gate | Current result | Required evidence / operator action | Abort condition |
|---|---|---|---|
|0 Source identity|SOURCE_VERIFIED for baseline; final consolidation exact CI/merge recorded in completion; release approval BLOCKED|Approve exact candidate SHA and frontend/backend trees, six-job CI, clean tracked source and local/remote parity. Preserve original untracked evidence. Review remaining relevant PRs and scope; PR206 is deferred legal work, not an automatic clearance.|Missing/mismatched SHA/tree, non-green required job, unreviewed drift, critical unresolved dependency|
|1 Environment identity|BLOCKED_PENDING_OPERATOR_EVIDENCE|Attest exact approved rehearsal URL, executable archive/symlinks, frontend asset, physical DB/instance, schema objects and auth client/origin. Public metadata alone is insufficient; establish no production DB/NAS ambiguity.|Unexpected database/instance/origin, conflicting archive/metadata, unknown storage boundary|
|2 Backup/rollback|BLOCKED_PENDING_OPERATOR_EVIDENCE|Read-only verify active policy, latest successful opportunities, paired dump/checksum metadata, freshness and approved isolated restore evidence; review schema/bootstrap/data rollback plan. Issue14 remains OPEN/ON HOLD.|Stale/missing/unverified backup, absent restore proof, unsafe downgrade or ambiguous restore target|
|3 Schema|SOURCE_VERIFIED; runtime INCOMPATIBLE0023→0027|Review chain/FKs/checks/triggers and empty-table guards below. Separately approve exact target DB/migration operation; no automatic historical backfill or cleanup.|Unexpected populated0024 snapshots, downgrade guard, unknown schema objects, any proposed evidence deletion to force upgrade/downgrade|
|4 Deployment compatibility|INCOMPATIBLE for deployed pairing|Approve one deployable frontend/backend commit. Verify67candidate routes versus61runtime, canonical read-model/action contracts, OAuth behavior and no coverage feature activation. Recheck after any separately approved deployment.|Missing required route, wrong source pairing, unsafe fallback, legal/coverage action unexpectedly enabled|
|5 Authenticated UAT|AUTHENTICATED_UAT_BLOCKED|Approved URL/origin/Web client, two aliases and canonical roles/permissions, synthetic records and explicit allowed mutations; human Google login; sanitized state/audit evidence. Read scope does not imply write scope.|No approval/accounts, origin error, unexpected authorization, cross-owner data, duplicate write or canonical identity mismatch|
|6 Go/no-go|NO_GO for cutover; BLOCKED_PENDING_OPERATOR_EVIDENCE for reassessment|Operator reconciles every prior gate and explicitly approves any future operation. CI_READY is not deployment/UAT/production readiness.|Any prior gate not satisfied; do not infer permission from a green build or this document|

There is no GO decision in this audit. No deploy, migration, snapshot, restore,
backup job, scheduler activation or real write was executed.

### Backup policy and migration/rollback review

Read-only source review finds `gxp-postgres-nightly-backup.timer` scheduled01:30UTC
with `Persistent=false`, and its service has `GXP_NIGHTLY_BACKUP_ENABLED=0`.
The source scheduler exists and is inert by default. Active VM trigger status,
freshness, checksum contents and restore ability are NOT_VERIFIED; do not repeat
the historical hypothesis that a scheduler is absent as a current fact.
Issue14's inventory is historical, not a current age calculation.

`deploy_rehearsal.sh` requires explicit frontend/backend source approval before
the existing exact-tree gate. `deploy_prod.sh` has required backup, Alembic and
template metadata bootstrap before release switching. A source audit of those
scripts is not permission to invoke them. Backup writes local/GCS data; restore
is a separately guarded destructive operation for a dedicated loopback disposable
target and checksum pair. Neither script was run. Use existing read-only audit
tools and operator evidence; no duplicate deploy/backup automation is provided.

| Chain | Source effects and compatibility limits |
|---|---|
|0023→0024|New empty draft roster tables, Case/document-version/team/member FKs, uniqueness/positive position/role/nonblank checks; no historical backfill. Nonempty downgrade denied.|
|0024→0025|Upgrade requires empty unlinked snapshots before durable draft identity; never invent IDs. Case+draft unique and PostgreSQL append-only UPDATE/DELETE triggers. Empty-only downgrade.|
|0025→0026|Decision-owned issued roster/member tables with decision/draft/confirming-user FKs, source-shape checks; reuses0025 trigger function. Empty-only downgrade.|
|0026→0027|New version/Site/Case/user-bound review event, enum/shape/digest-length/nonblank checks; UPDATE/DELETE trigger and nonempty downgrade guard. Schema/evidence only; no accepted coverage/backfill/Case-Certificate mutation.|

Repository CLI/helper derive head0027; no newer revision was found at audited
source. CI disposable PostgreSQL verifies clean upgrades and0027 trigger behavior;
it does not attest rehearsal schema. Digest length and individual FKs are not
complete provenance/business validation. Existing source intake checks and runtime
link policy keep their own owners. Never truncate evidence to bypass a guard.
Symlink/service rollback does not undo schema, template bootstrap or accepted data.

## Current acceptance evidence and module matrix

Fresh evidence is under `.codex/evidence/release-candidate-consolidation-20261102/`.
The eleven-module matrix below is retained with its narrow source-contract scope;
current probes reconfirm61runtime/67candidate routes, six missing KHKT/QĐKT and
certificate metadata routes, different bundle and four optional workspace action
fields. Matching OpenAPI version0.1.0/shapes does not prove authenticated payloads.
The underlying source matrix is COMPATIBLE only within declared tests/disposable
contracts; real acceptance for every module is BLOCKED. No stale payload fallback.

Fresh local SQLite/header_stub API checks, production-browser1366×768/1920×1080/
390×844 and local contracts are reported with this session's counts in completion.
Historical211/686/4006 counts below remain historical and are not silently updated.
No frontend defect was reproduced; application owners/layouts are unchanged.

All16 real Google A/B scenarios remain NOT_EXECUTED. Synthetic GIS/clock/header_stub
checks cover owner changes, logout, role change, pending GET/POST, expiry,409 and
accepted-write/GET503 recovery; they are not Google-issued credential, DB role
revocation, Word/NAS, screen-reader or production UAT evidence. No credential,
cookie or real identity is requested or recorded. PR206 stays OPEN/DRAFT and
Issues6/8/74/144 stay open; QĐKT rendering remains blocked.

## Historical audit — 2026-11-01 (retained)

Everything below is the prior package from423a46c. Its candidate/source hashes,
measurements and test totals describe that session, not the final consolidation.

Audit date: 2026-11-01. No deployment, migration, account provisioning, OAuth
change, real-environment write or storage operation is authorized by this document.
The owner explicitly confirmed that real A/B acceptance and write scope are not
approved. Google A/B remains **AUTHENTICATED_UAT_BLOCKED**.

## Source identity and evidence scope

Initial local main was `9e3ffbd87066bc542ab6b610fb75b886f80fd17c` (PR253).
The task checkpoint was `120338a4c691e1fd3435ecde1cb0ab27a595d7a2` (PR259).
Audited main subsequently advanced to `1e47bd7dbcc98078bf22a4d2b0b613aa7f8eab38`
(PR260, PostgreSQL trigger test only). All three upstream changes since PR253
were preserved; no backend owner code was edited.
Final audit candidate is `1ed3c40e6cd25ca2f9a7f538e4f0108d46f7d315` (PR261).
Its added intake service and test were reviewed: intake can append only UNRESOLVED
events, has no registered API/router caller and does not confer coverage/link
approval. Local added test1PASS. Frontend/API entrypoints/migrations are unchanged;
this audit neither invokes that service on rehearsal nor exposes a frontend action.
The fresh disposable server/browser run used120338a before that drift; PR260 was
test-only and PR261 added an unrouted service/test. Existing API entrypoints,
frontend and migrations were unchanged; this is not claimed as a restarted
exact-SHA1ed3c40 server. The added intake test is separately verified.

| Identity | Current evidence |
|---|---|
| Candidate frontend source | main `1ed3c40`; frontend tree `4a6f6677796fa3a38256818d9fb226aca62ff55e`, identical to PR253 |
| Candidate backend source | main `1ed3c40`; backend tree `38dfaf288f57ee38c940c6001ea746fb2aa86ece` |
| Required Alembic revision | `20261101_0027`, independently derived by Alembic and runtime-schema source helper |
| HTTPS backend | publicly reports `97182e58c3a673938d1b263c7eeaab41d28147b4`; executable/source archive not attested |
| HTTPS database | publicly reports `gxp_legacy_rehearsal`; physical DB identity/schema objects not inspected |
| HTTPS revision | `/api/readyz` reports actual=expected `20261012_0023`; current for the deployed runtime, not this candidate |
| HTTPS auth/origin | `google_oidc`; fresh browser actual origin `https://gxp.qlcl-dav.cc`; authorized origin and Web OAuth client type not attested |
| HTTPS frontend Git SHA | NOT_VERIFIED; asset hash is not a Git-source attestation |
| HTTPS entry asset | `/assets/index-COeZJt9i.js`, SHA256 `54530256db621527e9d17ed546fb04bff3a64a711a53cf963184903279b6ba99` |
| Candidate entry asset | `/assets/index-fr5rTWgE.js`, SHA256 `ae2eac6b5157ee38c84e39bb1e5d3d4ec7a5b355530ac0a53434eb2336d08000` |

`/api/app/status`, `/api/healthz` and `/api/readyz` return JSON200; no-bearer
`/api/auth/me` returns401. Unprefixed `/healthz` and `/readyz` return SPA HTML
and are not API health evidence. No protected real record was fetched.

## Module compatibility matrix

Source COMPATIBLE below means current in-repo frontend/API contracts plus the
specified disposable evidence. It does not certify every business scenario,
legacy parity, binary output or compatibility with the HTTPS deployment.

| Module | Source contract | HTTPS contract evidence | Authenticated HTTPS acceptance |
|---|---|---|---|
| Facility search | COMPATIBLE | NOT_VERIFIED: relevant OpenAPI shapes match; payload/authorization not exercised | BLOCKED_BY_RUNTIME |
| Case selection | COMPATIBLE | NOT_VERIFIED: workspace adds four optional typed document-action fields | BLOCKED_BY_RUNTIME |
| Case Application/assessment | COMPATIBLE | NOT_VERIFIED: relevant OpenAPI shapes match | BLOCKED_BY_RUNTIME |
| Inspection Plan | COMPATIBLE | INCOMPATIBLE: KHKT readiness/render routes absent | BLOCKED_BY_RUNTIME |
| Inspection Outcome | COMPATIBLE | NOT_VERIFIED: relevant OpenAPI shapes match | BLOCKED_BY_RUNTIME |
| CAPA | COMPATIBLE | NOT_VERIFIED: relevant OpenAPI shapes match | BLOCKED_BY_RUNTIME |
| Approval | COMPATIBLE | NOT_VERIFIED: relevant OpenAPI shapes match | BLOCKED_BY_RUNTIME |
| GMP certificates | COMPATIBLE | NOT_VERIFIED: issue/update/promote shapes match; document metadata absent as below | BLOCKED_BY_RUNTIME |
| GxP/ĐĐK | COMPATIBLE | INCOMPATIBLE: both certificate document-metadata routes absent | BLOCKED_BY_RUNTIME |
| Dashboard/Admin Overview | COMPATIBLE | NOT_VERIFIED: relevant OpenAPI shapes match | BLOCKED_BY_RUNTIME |
| QĐKT metadata only | COMPATIBLE, rendering remains blocked | INCOMPATIBLE: current-team/readiness routes absent | BLOCKED_BY_RUNTIME |

Both APIs advertise version `0.1.0`, despite61 runtime paths versus67 candidate
paths. The version string cannot attest compatibility. Missing routes:

- `/cases/{case_id}/documents/inspection-ke-hoach-kt/readiness`
- `/cases/{case_id}/documents/inspection-ke-hoach-kt/render`
- `/cases/{case_id}/documents/inspection-qd-kt/current-team`
- `/cases/{case_id}/documents/inspection-qd-kt/readiness`
- `/certificates/{certificate_id}/document-metadata`
- `/business-eligibility-certificates/{business_eligibility_certificate_id}/document-metadata`

Workspace schema additions are `create_endpoint`, `create_http_method`,
`create_input_readiness` and `create_input_blocked_reason` within contextual
document actions. This additive difference alone is not asserted to be breaking.
No filename/path fallback or permissive document action was added to compensate.

## Migration impact and rollback limits

**SCHEMA_SOURCE_VERIFIED**. Rehearsal **SCHEMA_RUNTIME_VERIFIED is not established**
beyond its publicly reported revision. CI disposable PostgreSQL is a separate
environment; never substitute its schema proof for inspection of rehearsal.

| Revision | Upgrade impact | Guards and PostgreSQL semantics |
|---|---|---|
|0023|Source provenance group/reference tables; no new historical backfill in this audit|Versioned provenance FKs/uniqueness; downgrade refuses populated evidence tables|
|0024|New empty draft snapshot/member tables|Case, document-version, team/member FKs; document-version uniqueness; positive positions/revision, roles, nonblank values; downgrade refuses populated tables|
|0025|Adds durable `draft_id` identity to0024|Upgrade fails if snapshots already contain rows; no invented identity/backfill. Case+draft unique; UPDATE/DELETE denied by PostgreSQL triggers; downgrade requires both tables empty|
|0026|New decision-owned issued roster/member tables|Decision unique/FK, optional draft FK, confirming-user FK; source/link-shape, digest/position/name/role constraints. Reuses0025 append-only trigger function; downgrade requires empty tables|
|0027|New `gmp_coverage_review_event`, schema only|Version/Site/optional Case/reviewer/recorder FKs; known decision/status and Case-shape checks; digest-length and nonblank-source checks; UPDATE/DELETE trigger. Downgrade refuses any row|

0027 records evidence, not permission to change certificate coverage or Case
links. It has no accepted historical backfill or new frontend action contract.
Digest length checks are not a complete provenance review or hex-content proof;
individual FKs do not establish every cross-entity business invariant. Existing
runtime link validation remains authoritative and Issue6 stays open.

The isolated prototype `gmp_coverage_evidence_ledger` is separate metadata, not the
new runtime event table; no production ledger grant/service was activated.

Additive schema does not mean automatic rollback is safe. Once evidence exists,
these downgrade guards deliberately stop. Never delete evidence to force a
downgrade. Symlink/service rollback does not roll back migrations, template
metadata bootstrap or accepted commands. Backup/restore evidence and a reviewed
forward/rollback plan remain operator prerequisites; no backup/restore was run.

Local Docker daemon was unavailable and no local PostgreSQL runtime was claimed.
PR259 CI proves a clean PostgreSQL upgrade through0027. PR260 adds a dedicated
test requiring database `gxp_qlcl_test`: insert synthetic event, reject UPDATE and
DELETE, preserve rationale, roll back all rows. Check its exact-SHA CI outcome
before counting this as CI PostgreSQL execution, not a local run. Final main
`1e47bd7` [CI41321838641](https://github.com/hahoangphuong/GXP-QLCL/actions/runs/41321838641)
is6/6SUCCESS. Its full backend suite has4005PASS/73SKIPPED/5warnings, versus
4004PASS/73SKIPPED before the one-test PR260; the CI disposable database matches
that test's explicit guard. This supports CI execution of the0027 immutability
test, not rehearsal schema verification. Nonempty downgrade remains a reviewed
source guard, not a newly executed local PostgreSQL rollback experiment.

## Reproducible acceptance and current results

Evidence root outside Git:
`.codex/evidence/release-compatibility-oidc-ab-20261101/`.

- `compatibility_audit.py`: public read-only source/OpenAPI comparison; no real credentials.
- `api_probe.py`, `security_matrix.py`: actual FastAPI + fresh local SQLite/header_stub,211 checks; denied/read requests preserve whole-DB digest and audit count. A=admin, B=inspector; B's allowed application/PCT writes are retained. This is not Google authentication or real RBAC revocation.
- `browser-identity.cjs`, `browser-pending-expiry.cjs`, `browser-recovery.cjs`: production build + actual disposable API; synthetic GIS/clock explicitly separate. Verify same-credential revalidation, pending GET/POST owner replacement, expiry, logout/Back/Forward, draft/token retention, real409, accepted write followed by injected canonical GET503, and no blind replay.
- `acceptance_matrix.py`: validate saved disposable evidence and emit16-scenario `acceptance-plan.json`; every real Google scenario remains NOT_EXECUTED/AUTHENTICATED_UAT_BLOCKED.
- Three viewports:1366×768,1920×1080,390×844. Candidate document widths1366/1366,1920/1920,390/390; focus-only navigation issues zero GETs. F2/Enter/Escape/Tab/Shift+Tab and IME no-save checked. Screenshots stay local.
- Fresh unauthenticated HTTPS widths1366/1366,1920/1920,390/469; zero protected GETs/zero writes. This old asset's overflow is not a new candidate regression.
- QĐKT readiness metadata returns `ready_to_render=False` for all three disposable GxP contexts. No legal rendering or binary/storage UAT.

Current source CI and local command results are recorded in completion.md.
Local relevant contracts88PASS plus the added PR261 intake test1PASS with
`python -X utf8`; an initial CP1252 source-read
failure is retained as a diagnostic, not a product defect. Ownership/header/CAPA
targeted regressions13PASS twice. Frontend application tree is unchanged from
PR253; full frontend686PASS/40files is verified in current source CI.

## Operator gates before any real Google A/B execution

1. Approve one exact deployable source pair and intended frontend/backend trees;
   do not equate runner cross-head overlay with a deployable archive. Recheck main
   and migrations if source advances. The audited candidate is not deployment approval.
2. Operator independently attests executable release/archive, backend/frontend
   symlinks, physical DB name and schema objects. Use existing read-only source
   and active-release audit tools; this audit does not replace them.
3. Approve backup/restore and migration/rollback constraints. Existing rehearsal
   wrapper requires explicit frontend/backend source pins and invokes the exact
   source gate before staging, backup, migration and switching. Do not bypass the
   required backup or run scripts from an old checkout. No duplicate deploy or
   backup automation was added.
4. Infrastructure owner confirms Web OAuth client type and exact JavaScript
   origin (scheme, host, port). GIS loading/public client presence does not prove
   authorization. Do not change Console/client/DNS/settings under this audit.
5. Provide two approved Google account aliases, canonical role/permission
   expectations, allowed URL and read/write record scope. No real identity,
   password, token or cookie in evidence. Human performs Google login.
6. After a separately authorized compatible release, repeat public status,
   JSON health/readiness, source/bundle, schema and contract checks. Abort on
   drift, unexpected database, origin error, missing contract or readiness mismatch.
7. Run A/B reads first: canonical `/auth/me`, Site/Case reads, role-aware dashboard
   and Admin. Then account-switch/pending/expiry/downgrade scenarios. B is not
   assumed read-only. Server403 is authorization proof; disabled UI is not.
8. Run write/deny/concurrency scenarios only with separately approved synthetic
   records and scope. Check exact UUID/version, before/after state and audit;
   never blind retry409 or replay an accepted-but-unverified mutation. A local
   write-blocker405 is not backend RBAC proof.

**Verdict:** source-side frontend/backend contract compatibility is verified only
within the declared disposable/CI scope. **CI_READY** is verified at final candidate
`1ed3c40`: [CI41322889008](https://github.com/hahoangphuong/GXP-QLCL/actions/runs/41322889008)
has all six required jobs SUCCESS, backend4006PASS/73SKIPPED/5warnings and
frontend686PASS. Skips are not counted as PASS. **DEPLOYMENT_BLOCKED** and
**AUTHENTICATED_UAT_BLOCKED** remain. `AUTHENTICATED_UAT_PASSED` and
`PRODUCTION_READY` are not established. This documentation branch is not a
release candidate: QA documentation changes its frontend Git tree. Releasing a
different commit requires new exact-source approval; no gate is bypassed.

PR206 remains OPEN/DRAFT; Issues6/8/74/144 remain open. Native existing-tab
inspection failed with computer-use kernel asset initialization; no screen-reader,
Word/VBA runtime, NAS/binary or production acceptance is claimed. No frontend
defect was reproduced and no product-change PR is warranted by this audit.
