# PR #206 consolidation and operator handoff

## Scope and integration boundary

Starting PR HEAD: `bab20da1e52462562dc143b09849c07a6ae37f3c`.
Latest main at initial reconciliation: `e68daafe2cfa68871afbca02071ee32552cba810`.
Merge-base: `dc8d106c3671788fdf3de3e96fdbd4a63dab20d5`.
Main #211 changes only reconciliation CI node identity validation; #212/#213
change the read-only storage reconciliation report and its tests; #214 adds a
real PostgreSQL rollback regression. None modifies a QĐKT imported interface,
fixture pin, acquisition reader, source owner or renderer. Normal merge preserves
all five upstream changed files. No reset, rebase or forced history update.

## Review of the original 17-file inventory

| File | Owner / necessity / disposition |
|---|---|
| artifacts/legacy_audit/inspection_qd_kt_transformation_audit.json | Deterministic generated audit projection; retain, regenerate from source |
| backend/app/document/inspection_qd_kt_provenance_gate.py | Existing shared JSON/provenance owner; independent parser hardening extracted to PR #215 |
| backend/app/document/inspection_qd_kt_runtime_identity.py | Offline diagnostic contracts and pinned identity chain; retain in Draft |
| backend/app/document/inspection_qd_kt_runtime_provenance.py | Independent capture pin and actual-byte boundary; retain in Draft |
| backend/app/document/inspection_qd_kt_transformation_audit.py | Single audit projection owner; retain, no business approval |
| backend/app/document/inspection_qd_kt_vba_bookmark_series.py | Physical target validation at existing owner; retain with source-specific tests |
| docs/QDKT_14_BOOKMARK_TRANSFORMATION_AUDIT.md | Generated human-readable projection; retain, no manually edited statuses |
| docs/QDKT_RUNTIME_OBSERVATION_PROTOCOL.md | Operator-facing procedure, restrictions and trust assumptions; retain/strengthen |
| tests/fixtures/inspection_qd_kt_runtime_identity_evidence.json | Independently pinned sanitized static companion; retain unchanged |
| tests/fixtures/inspection_qd_kt_runtime_source_evidence.json | Reviewed capture replay without private bytes; retain unchanged |
| tests/test_qdkt_runtime_identity.py | Synthetic adversarial tests, not live attestation; retain runtime-specific coverage |
| tests/test_qdkt_runtime_provenance.py | Byte/extraction/target/negative-path regression; retain source-specific coverage |
| tools/Observe-QdktExcelRuntime.ps1 | Operator-only existing-session COM getter collector; never auto-invoked; retain |
| tools/audit_qdkt_source_transformations.py | Analyst CLI, explicit mutually exclusive acquisition modes; retain |
| tools/qdkt_runtime_identity_evidence.py | Optional private-byte encoding/loader reproduction; no macro execution; retain |
| tools/qdkt_runtime_observation.py | Bounded offline observation/disk acquisition through existing reader; retain |
| tools/qdkt_runtime_source_verification.py | Optional static extractor using oletools==0.60.2; retain outside application dependencies |

No duplicate parser or acquisition implementation is introduced. Backend audit
imports runtime contracts; observation tools invoke those contracts; optional
extractor imports the encoding companion only at reproduction time. This delayed
import breaks the source/encoding capture dependency cycle without a fallback.
These modules are offline tooling, not API endpoints or renderer dispatch paths.
The collector does not invoke the assessor, macros or any issuance action.

The fixtures contain relative artifact/module references, hashes, source-line
encoding evidence and static code observations. They do not contain operator
identity, live PID/session data, email, credentials, tokens, host private paths or
runtime binary payloads. User-supplied binary artifacts remain excluded from Git.
Synthetic Windows paths/PIDs in tests are explicitly not real operator evidence.

## Class A / Class B separation decision

Choose Outcome 2 for the **shared JSON parser only**. Its pre-existing owner on
main already services source/owner/physical audit inputs. Rejecting escaped lone
surrogates and numeric exponent overflow is independently useful and can be
reproduced with a few bytes, without a new runtime fixture, private artifact,
business policy or readiness assertion. PR #215 contains exactly the parser-owner
change and independent regressions. Five RED cases (three surrogates, two overflow
numbers) become GREEN; existing duplicate/nonfinite/size/type protections remain.

Other strict observation validation and 100ns ordering are evidence-independent
controls *within the new observation contract*, which exists only in #206.
Extracting them alone would introduce a partial new assessor or duplicate schema
ownership on main. Keep those together in Draft #206. Source-specific physical
bookmark checks likewise stay with their audited targets and negative tests.

PR #215 passed all six required exact-HEAD CI gates on
`bb49944ade24844396da81b39e7ba63afba71664` and was squash-merged as
`a857a801d6bc0d0d70eb5a76fc54dd9bbee3537d`. Backend: 3906 PASS/73 SKIPPED/0 FAIL;
frontend 531 PASS; explicit PostgreSQL reconciliation 10 PASS/no skips.
CI: https://github.com/hahoangphuong/GXP-QLCL/actions/runs/40839783190 .
Its squash commit was integrated into #206 by normal merge. The parser now has
zero diff against main; redundant parser-only cases moved out of runtime suites
into the stronger independently merged 12-case suite. This does not merge #206
or resolve `UNVERIFIED_VERSION_BINDING`.

## Operator package and machine-readable acceptance

`python -m tools.qdkt_operator_evidence_package --dry-run` emits a deterministic
manifest for the reviewed checkout. `--check-manifest` detects changed listed
files and type-lossy JSON (False must not become 0). Both exit 2 because neither
integrity comparison nor a manifest is render readiness. Scope is an explicit file
list, not a self-contained executable bundle or all transitive dependencies.
The protocol specifies how to preserve approved commit/script/manifest hashes,
operator/witness records, timestamps with precision caveats, raw observations and
host workbook identity without changing the session. Signing, if already approved,
is external; no tool authenticates a self-reported custodian.

The runtime assessment output is versioned `qdkt-runtime-assessment/v1`. Strict
input remains `qdkt-excel-observation/v1`; extra manifest/business/approval fields
are rejected instead of silently upgrading authority. Invalid input produces a
fixed diagnostic; missing acquisition is unavailable; disk contradiction remains
separate from missing evidence. No pathname in submitted metadata is reopened.

| Acceptance dimension | Current category / limit |
|---|---|
| Supplied snapshot | BYTE_IDENTITY_PROVEN, provided artifact/member only |
| Reviewed source | SOURCE_EQUIVALENCE_PROVEN, 14 lines/nine procedures only |
| Export encoding | ENCODING_AMBIGUOUS |
| Reported disk | EVIDENCE_UNAVAILABLE; matching unsigned claim VERSION_BINDING_UNVERIFIED; mismatch CONTRADICTED |
| Build/distribution | VERSION_BINDING_UNVERIFIED |
| Loaded runtime | RUNTIME_IDENTITY_UNVERIFIED |
| Executable VBA/p-code | RUNTIME_IDENTITY_UNVERIFIED |
| Independent custody | EVIDENCE_UNAVAILABLE; report agreement is insufficient |
| Business owner acceptance | EVIDENCE_UNAVAILABLE; no approval token accepted |

The static audit does not reacquire private bytes. Its captures are reproducible
offline and explicitly labelled as replay. Fresh private-byte extraction is a
separate explicit mode; it cannot fall back to a cache. Disk capture before the
reported session, after observation, or multiple same-name paths/PIDs is reported
without a freshness heuristic or automatic choice. Replaced files and consistently
forged clock metadata never prove memory identity. Live Excel collection and
p-code/source correspondence remain unverified.

## Unchanged safety and business disposition

PR #206 stays OPEN/DRAFT. Issues #74/#144 stay OPEN. All 14 operation statuses
remain unchanged: zero VERIFIED; original owner summary 8 BLOCKED/6 PARTIAL.
Four template bookmark counts remain 22/22/14/11. Existing source/trace/helper and
runtime capture pins are unchanged. CONTRADICTED does not prove a Word document
changed. No new primary binary acquisition is claimed in this consolidation pass.

KHKT -> draft DOCX keeps blank issuance date; after approval the user supplies
decision number/date/team. Team reuse does not silently copy other KHKT data to
Case. Existing lifecycle regression remains the guard; no new business fallback.
`decision=UNDECIDED`, `ready_to_render=False`, Word UAT `NOT_EXECUTED`, business
timezone unverified. Renderer/legal issuance remain disabled. No production
DB/NAS/GCS writes, deployment, original binary changes, API/schema/RBAC changes,
Excel launch/reload, macro execution or Trust Center changes.

Exact operator inputs still needed: attested export encoding/log; source/build
commands/references and distribution manifest/checksums; independently authenticated
existing-session/custody observations; independent load-time/in-memory executable
identity and p-code/source correspondence; actual template resolution and separate
business/legal/Word acceptance. The protocol provides commands, not those facts.
