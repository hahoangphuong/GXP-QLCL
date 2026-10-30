# QĐKT primary evidence status — 2026-10-29

**Outcome B: BLOCKED_PENDING_OPERATOR_PRIMARY_EVIDENCE.** PR #206 remains
OPEN/DRAFT. `UNVERIFIED_VERSION_BINDING` is unresolved. No new implementation
defect or independently authenticated live evidence was found in this pass.
Do not continue extending the package without a specific missing control or
new primary evidence. The next blocking action belongs to an authorized operator.

## Baseline and bounded acquisition

Starting #206 HEAD: `c8f1155144cb9940dacf114852fe67d75723228c`.
Starting main: `318d3663add7be34c8fc6e842494c89514ed6f4e`.
Main #216 changes only an existing PostgreSQL retry regression, not a QĐKT
interface. Its complete diff was reviewed and preserved through normal merge;
no storage/test code was edited. PR #217 is outside this task and untouched.
PR #215's parser is already on main; no duplicate parser was reintroduced.

During this pass the backend owner merged #217; main advanced to
`0f456b3d5e7735220bd819d91d179969561b6d5a`. Its test-only retry parameterization
was audited and preserved by synchronizing main, without editing that file or
performing a PR #217 merge action. QĐKT imports and contracts are unaffected.

Read the previous handoff, protocol, consolidation review, fixtures, audit,
collector, assessor, acquisition and source verification tools, and current
GitHub PR/issue comments. No new operator report was supplied there. Search was
bounded to the repository, local legacy/artifacts and existing QĐKT evidence
directories, including ignored files. The three precommit ZIPs remain the known
Python/manifest packages, not an attested VBA build/distribution chain. No claim
is made about inaccessible original build systems or another operator's computer.

Fresh `--verify-local-artifacts` reacquired six supplied inputs, checked immutable
bytes before parsing and reproduced the pinned source/encoding capture. A separate
bounded read of the explicitly named original workbook reproduced the pinned
loader capture. No Excel/VBA/Word execution, binary write or template edit occurred.
Exit 2 means blocked readiness, not verification of runtime identity.
Raw results and process preflight are outside Git in
`.codex/evidence/qdkt-primary-evidence-20261029/`.

Exact reviewed inputs remain:

- ZIP SHA-256 `6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7`.
- Add-in SHA-256 `52725cba1fd87107814d07da1dbae8d79c77127765018b0daf4b6fe6f44b1b58`, 1017208 bytes.
- Embedded project member SHA-256 `84afc3e2d431b550e7f7f6b392f1a363d6d476efe444ba7aab3b4932dba4bcfe`.

`tests/fixtures/inspection_qd_kt_runtime_source_evidence.json` preserves exact raw
export hashes for Module1/RecordForm/TTVForm, procedure locations and all 14 paired
writer lines. Source representation is decoded text with LF-only normalization,
not compiled code. No trim/case/punctuation/Unicode normalization. Get_Tpl's nine
encoding differences are outside i=2; Get_TTV2's one Fail-handler message may be
reached on i=2 failure but actual execution is unproven. Reviewed ZIP encoding and
the source of its original export remain unattested; do not infer semantic change.

The local process-name survey found **zero visible EXCEL processes** at collection
time. This is a scoped OS observation, not proof about another session/machine or
authenticated custody. No COM attachment, Excel launch/reload or user-session
mutation was attempted. A running add-in cannot be inferred from its disk copy.

## Evidence classification and acceptance, axis by axis

| Axis/item | Evidence class | What is established | Remaining primary evidence |
|---|---|---|---|
| Reviewed source | Available and independently verified within pinned supplied snapshots | Exact raw ZIP/module hashes; 14 writer lines and nine complete procedures source-equivalent with LF-only normalization | Approved export origin and executable correspondence |
| Export origin | Missing; requires source custodian | Supplied ZIP bytes preserved, not a witnessed export | Original export log/witness, project identity, tool/version, export encoding and raw module hashes |
| Export encoding | Available but ambiguous | Add-in PROJECTCODEPAGE=1252; historical reviewed decoder cp1258 fallback; exact differences preserved | Authoritative export encoding; text equality under cp1252 is insufficient |
| Build | Missing | No attested input/output/tool/process/time mapping found | Original build/packaging commands, dependencies/references, input/output checksums and authenticated build record |
| Distribution | Missing | Supplied add-in is a known snapshot, not a witnessed distribution event | Distribution/release manifest tying the built bytes to delivered bytes and their custody |
| Disk artifact | Available and independently verified for the supplied local snapshot only | Fresh exact add-in/member bytes and size match existing pins | Separate operator acquisition of the physical path reported by the actual session; this still does not prove load-time bytes |
| Loaded Excel runtime | Requires live Windows/Excel operator | No live target/host workbook or session report acquired | Existing-session PID/start/session/HWND, host Name/FullName, target add-in Name/FullName, other PIDs/same-name paths, capture order and custody |
| Executable VBA/p-code | Missing; requires independently reviewed acquisition method | Static source extraction does not establish memory or execution | Load-time/in-memory executable identity and p-code/source correspondence; do not enable security settings or execute a macro to manufacture it |
| Independent custody | Missing | Local manifests and synthetic test reports are self-generated, not authenticated witness evidence | Approved collector/operator identity, independent witness or approved signing records, raw-file checksums and chain of custody |
| Business/legal acceptance | Requires business/legal owner acceptance | Existing owner blockers unchanged | Separate business/date/timezone/Word/legal acceptance; runtime identity cannot substitute |

Build and distribution are separate missing links. The existing machine key
`build_distribution` is a conservative aggregate diagnostic, not proof of either
axis. Its v1 contract is retained; this report does not invent submitted build or
distribution data. `collector_authenticated`, `runtime_identity_verified` and
`ready_to_render` remain false even for perfectly consistent forged metadata.

No new primary contradiction was discovered. Existing CONTRADICTED bookmark
statuses concern source/policy differences, not proof that a real Word document
changed. Self-reported PID/path/hash/time, source-capture flags and Installed
properties remain claims; absence of contradiction is not positive proof.

## Implementation audit and test disposition

Collector returns path/session observations only; assessor never promotes these
to in-memory identity. Available AddIns are not exhaustive loaded-code inventory.
The target is looked up by filename; the host workbook is independently recorded
in the operator sidecar. Wrong ROT/PID fails before workbook access. Multiple
instances, same-name paths, changed process creation stamps, missing offsets,
100ns ordering, disk/path mismatch and later file replacement remain explicit
negative paths. Filesystem timestamps are not atomic with byte capture. No
submitted payload path is reopened, and no cache replaces requested acquisition.

Existing tests cover forged consistent reports, wrong binary/same filename,
correct bytes/different path, stale-session chronology, multiple processes/paths,
altered manifest/JSON types, invalid Unicode/duplicates, missing input and 100ns
precision. No redundant adversarial cases or artificial RED patch were added.
No new security root cause was demonstrated; RED/GREEN is not applicable to this
documentation/evidence result. Offline regression is not live observation.

## Operator actions and independent replay

Use `docs/QDKT_RUNTIME_OBSERVATION_PROTOCOL.md` from the reviewed checkout:

1. Preserve approved commit, collector script hash, operator reference and witness
   records. Run offline manifest dry-run/check and the collector deny-mode first.
2. On the machine with the intended **already-running** session, list existing
   Excel PIDs and start/session times. If none exists, stop; do not launch/reload.
3. Identify the actual host workbook and target session independently. Run the
   existing collector with explicit PID and authorized operator reference. Wrong
   ROT, busy/denied access or ambiguity stays unavailable; do not change settings.
4. Preserve original COM JSON and host/custody sidecar. Acquire the explicitly
   reviewed physical add-in file separately, with size/hash and timestamp caveats.
   No NAS locator is inferred. Preserve raw inputs before any combined metadata.
5. Send reviewed raw observation, disk snapshot record, checksums and custody
   evidence through an approved channel. Separately provide original export,
   build and distribution records. Do not send credentials or unrelated workbooks.
6. An independent reviewer can run `--assess-runtime-observation` offline using
   the explicit evidence parent and relative JSON filename, and compare the
   immutable-byte snapshot through the bounded acquisition tool if supplied.
   Reproduction establishes consistency/bytes only; identity and legal acceptance
   are assessed separately. Missing executable evidence remains missing.

Codex can automatically recheck supplied bytes, JSON/manifest integrity, capture
ordering, source comparisons and deterministic assessment after receipt. It
cannot authenticate self-reported custody or infer executed VBA from disk hashes.
No macro execution, Trust Center change, original save, close/restart/reload,
issuance or production access is authorized by this procedure.

## Unchanged business gates

CONTRADICTED: Fulldate, Diachicoso, QDKT, NgayQDKT.
BLOCKED: Diadiem, Diadiemx, VKNx, VKN.
PARTIAL: Tencoso, HsDK, NgaynopHsDK, TT3x, TT3Del, TTx.
Zero VERIFIED; original owner accounting 8 BLOCKED/6 PARTIAL. Four-template
inventory remains 22/22/14/11. Source transformation, runtime implementation,
business semantics and Word output are distinct acceptance levels.

Keep Issues #74/#144 OPEN; `decision=UNDECIDED`, `ready_to_render=False`, Word UAT
`NOT_EXECUTED`, business timezone unverified; renderer/legal issuance disabled.
No API/schema/RBAC, business owner, production DB/NAS/GCS, source binary/template,
storage writer/finalization/reconciliation or backend #217 changes.
