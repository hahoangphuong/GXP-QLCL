# QĐKT runtime observation — authorized operator protocol

This procedure collects observations, not authorization or proof of executed VBA.
Outcome B remains valid: PR #206 stays OPEN/DRAFT while
`UNVERIFIED_VERSION_BINDING` remains. No live observation was performed by the
coding agent. Synthetic test observations are not operator evidence.

## Four identities that must remain separate

| Identity | What can be established here | What is not established |
|---|---|---|
| Excel-reported loaded path | Filename lookup on an existing COM instance, checked against an operator-selected PID and HWND | Which bytes were loaded or executed |
| On-disk file | Bounded immutable snapshot, size and SHA-256 at collection time | Memory contents, load time, unchanged file since load |
| In-memory executed VBA | No positive attestation provided by this protocol | Source/p-code equivalence, code actually executed, absence of background macros |
| Reviewed source | Independently pinned source/capture and character-exact comparisons | Export/build/distribution identity or legal approval |

`collector_id`, timestamps, acquisition-method strings and all fields in an
observation JSON are unauthenticated claims. Matching every field does not close
the blocker. The assessor rejects inconsistencies but never authenticates the
operator or promotes runtime identity. A disk hash alone is not loaded-code proof.

## Verifier trust-boundary review

| Threat | Current boundary and evidence |
|---|---|
| Changed binary, same metadata | Actual immutable-byte SHA checked before parsing; negative tests cover all six inputs |
| Changed binary and matching expected checksum | Entire independently pinned capture is checked first; correlated replacement is rejected |
| Symlink, alternate root or normalized path | Existing bounded offline reader owns acquisition; payload paths are never reopened by the assessor |
| Malformed project streams | Foreign bytes cannot reach extraction past unchanged pins; no new input bypass was found |
| Duplicate/case-colliding modules or projects | Extractor rejects ambiguity and closes its parser; component fault injection is not a claim of a reachable byte-pin bypass |
| Duplicate ZIP entries/order | No first/last-wins selection; duplicate names rejected in memory; raw package pin precedes parsing |
| cp1252/cp1258 difference | Raw line hex/SHA and character differences preserved; export encoding remains ambiguous |
| Same filename, other add-in | Filename lookup supplies a path observation only; separate byte snapshot and loaded-code evidence remain necessary |
| Cached evidence labelled fresh | Explicit fresh mode reacquires bytes and extracts; default capture/observation modes do not set fresh-verification success |
| Mutually consistent forged chain | Unsigned PID/path/hash/collector claims are consistency-checked only; runtime identity always remains unverified |
| Escaped lone Unicode surrogate | Demonstrated RED accepted-invalid-UTF8 gap; shared parser now rejects it before canonicalization, without NFC/case/punctuation changes |

This is an input-boundary claim, not protection against a compromised Python
runtime, extractor dependency or reviewed repository code. Existing Linux
acquisition tests exercise OS link boundaries; inability to create Windows
symlinks locally is not reported as native Windows link-verification PASS.

## Preparation and authorization

An authorized operator must already have access to the relevant Excel session.
Do not launch Excel, open a workbook/add-in, enable macros, change Trust Center,
unlock a project, edit a cell, run a generator or change any installation state.
Do not execute unknown VBA. Do not use an execution-policy bypass or elevation
to overcome a collection failure. Existing background Excel activity is outside
the collector's control; the collector makes no claim that none occurred.
The operator must independently trust the Office executable/ROT provider before
attaching. An EXCEL process name is not publisher verification. If that trust
cannot be established, do not run the collector: preserve a denied/unavailable
observation. Read-only getters are not a sandbox against a malicious COM server.

Keep raw observations/screenshots and paths outside Git, in an approved local
evidence directory. Redact unrelated workbook/cell/user details from screenshots.
The collector does not collect cell values, workbook titles, module text or NAS
credentials. It writes JSON only to stdout and never closes the user's Excel.

The collector requires Windows PowerShell 5.1/.NET Framework. Its deliberate
`-AuthorizedObservation` switch records an operator action, not authenticated
approval. Without it, the script exits before inspecting processes or COM.

## 1. Select an existing session

### Reproducible operator kit — offline preparation

Use a reviewed repository checkout on Windows 11, with Python and Windows
PowerShell 5.1 available. The kit is a source-checkout manifest, not a standalone
executable bundle, signed attestation, or automatic Excel discovery tool.
It has no automatic macro execution or security-setting action.

From the checkout root, record `git rev-parse HEAD`, `git status --short`, the
approved operator reference and an independently chosen custody witness in a
ledger **outside Git**. Record exact modified-file/line-ending differences rather
than treating a changed checkout as the reviewed commit. Then create a local
manifest without private binaries, Excel or COM:

```powershell
python -m tools.qdkt_operator_evidence_package --dry-run > operator-manifest.json
python -m tools.qdkt_operator_evidence_package --check-manifest operator-manifest.json
powershell.exe -NoProfile -File .\tools\Observe-QdktExcelRuntime.ps1
```

All three commands deliberately exit 2 because readiness remains blocked.
For manifest comparison, inspect `package_files_match=true`; for denial, inspect
`QDKT_OPERATOR_OBSERVATION_REQUIRED`. An error exit alone is not a successful
dry-run or package-integrity result. Preserve output, then move the local manifest
to the approved evidence directory. The named JSON must be inside the explicit
root for bounded acquisition; use a plain safe filename, not a path through a
link/reparse point. Do not add this operator-specific manifest to Git.

The deterministic manifest records collector schema/version, script SHA-256 and
size, selected protocol/tool/fixture hashes, reviewed source/export hashes,
expected private artifact relative paths/hashes and the acceptance matrix. It
does not enumerate all transitive Python dependencies; use the full reviewed
checkout. Private original binaries are not bundled or required for this dry-run.
Hashes cover exact checkout bytes, including line endings; different checkout
line endings legitimately produce different hashes and need review, not silent
normalization. Repeating against unchanged bytes is deterministic. The manifest
has no generated clock/session/operator values. Its checksum is tamper detection
relative to an independently preserved baseline, not independent custody proof.
Regenerating a manifest after replacing code does not authenticate either one.

Have the independent witness preserve the approved commit and manifest checksum
through an existing approved channel. If an approved signing system is already
available, sign the manifest/evidence checksums there and preserve signer identity,
verification result and custody records. This tool neither creates keys nor
validates signatures. Without independent custody, retain
`independent_custody=EVIDENCE_UNAVAILABLE`; a self-reported operator ID is insufficient.

### Artifact and session ledger

Keep one append-only ledger entry per acquisition; never replace an earlier raw
observation. Record these values separately from the assessor's input schema:

| Entry | Required observation / limitation |
|---|---|
| Collector | Approved commit, exact script hash/size, manifest hash, collector version, operator reference, witness/signing reference or unavailable |
| Reviewed add-in | Operator-chosen physical path, snapshot size/hash; expected reviewed hash in the manifest; no path inferred from filename alone |
| Filesystem metadata | Optional `Get-Item -LiteralPath 'D:\approved-addins\GPs.xlam'` then `Select-Object FullName,Length,CreationTimeUtc,LastWriteTimeUtc`; separate self-reported observation, not atomic with the byte snapshot |
| Clock | UTC acquisition stamp, explicit local UTC offset and workstation clock authority if known; filesystem timestamp resolution/rounding/copy behavior is unverified |
| Source/build | Reviewed export hashes and original encoding/export/build/distribution manifest/log, or unavailable; Office producer version is insufficient |
| Excel session | Explicit PID/start/session/HWND, target GPs.xlam Name/FullName; other reported PIDs and same-name paths remain ambiguous, never automatically selected |
| Host workbook | In the already-open Excel UI, independently record the intended host workbook's exact Name/FullName, visible session association and separately authorized on-disk snapshot hash if available; do not open/reload/save it for evidence |
| Loaded inventory | Collector observes only the selected ROT instance's target and available same-name AddIns; this is not an exhaustive list of loaded modules or all Excel instances |
| Raw custody | Original JSON, screenshots if authorized, byte snapshot/hash, file metadata, manifest, independent witness/signature references; redact unrelated personal paths/workbooks from shared copies |

Do not add ledger fields to the strict v1 observation JSON: preserve a sidecar.
The collector does not enumerate unrelated open workbook names or collect their
contents. If the intended host/session cannot be independently identified, record
unavailable; target filename lookup does not establish that the host invoked it.
File timestamps can be copied or altered, clocks can be wrong, and the file may
have been replaced after Excel loaded it. Neither timestamp equality nor a later
matching disk hash proves load-time or executable-memory identity.

Restarting Excel, reloading an add-in, changing Trust Center, enabling VBProject
access or saving a workbook would change the state being observed. They are
outside this protocol. If safe in-memory/p-code observation is unavailable, retain
that limitation rather than restarting/reloading to manufacture correspondence.

Record the collection purpose and operator reference in the evidence ledger.
Use this read-only process listing; do not start/stop any listed process:

```powershell
Get-Process -Name EXCEL | Select-Object Id, StartTime, SessionId
```

The operator must identify the intended session. Repeat separately for every
relevant Excel process; one ROT lookup does not enumerate all sessions. No
available session means `EVIDENCE_UNAVAILABLE`, not permission to launch one.

## 2. Observe path and context without invoking VBA

From the reviewed repository, with the real PID and authorized collector reference:

```powershell
powershell.exe -NoProfile -File .\tools\Observe-QdktExcelRuntime.ps1 `
  -AuthorizedObservation -TargetExcelProcessId 12345 -CollectorId 'OPERATOR-REFERENCE' `
  > D:\approved-evidence\excel-observation.json
```

Replace the example values/path explicitly; no script discovers a NAS location
or writes to production. The collection script:

1. Connects only to an existing `Excel.Application` ROT object.
2. Maps the returned application HWND to a PID; rejects the wrong ROT instance.
3. Looks up `Workbooks.Item('GPs.xlam')` and reads Name/FullName/version/build.
4. Records same-name entries from available AddIns and their Installed property.
5. Rechecks PID creation time, records OS session ID and UTC capture timestamps.
6. Releases only its own COM references, without invoking VBA or changing settings.

UTC here is acquisition metadata from an untrusted workstation clock, not a
business timezone or issuance-date rule. PID/start-time consistency is not
independent authentication or proof of an executable's publisher/signature. A failed COM lookup, denied access, process change,
wrong ROT instance or collection limit returns a failure record; no fallback
to another process or cached evidence is allowed. Do not close/reopen Excel to
manufacture a successful capture. On multi-instance mismatch, record the failure
and request a separately reviewed acquisition method for that session.

Use a 60-second operator observation budget. COM property calls may block when
Excel is busy/modal; the script is scope/count-bounded, not a proven RPC-timeout
mechanism. If it does not return, cancel only the collector with Ctrl+C, preserve
any failure context and mark evidence unavailable. Do not dismiss Excel prompts,
kill/restart Excel, increase the budget to force a result or call partial output
a completed observation. Live collection remains unverified until an operator
performs it; syntax/denial tests are not a live-Excel PASS.

The assessor requires identical serialized process creation stamps before/after;
it does not coerce .NET 100ns fractions to Python microseconds to make different
stamps compare equal. This is an observation-identity guard, not a business date
normalization or proof of a trusted clock.

Add-in title, filename and physical FullName are different concepts. Available
AddIns/Installed entries do not prove all loaded code is enumerated. Loaded
add-ins may require explicit filename lookup instead of Workbooks enumeration.
These scopes follow Microsoft's [AddIn reference](https://learn.microsoft.com/en-us/office/vba/api/excel.addin).
The HWND is a read-only application handle ([Microsoft](https://learn.microsoft.com/en-us/office/vba/api/excel.application.hwnd));
ROT access obtains an existing instance, not a new one ([Microsoft .NET Framework](https://learn.microsoft.com/en-us/dotnet/api/system.runtime.interopservices.marshal.getactiveobject?view=netframework-4.8.1)).

## 3. Optionally observe the on-disk bytes

First preserve the raw COM output. Only after operator review of its exact path,
use an explicitly chosen local parent and filename, for example:

```powershell
python -m tools.audit_qdkt_source_transformations `
  --observe-runtime-file 'D:\approved-addins' 'GPs.xlam' --format json `
  > D:\approved-evidence\disk-observation.json
```

This reads one local file through the existing bounded no-link offline reader,
hashing and sizing the same immutable byte snapshot. It does not attach to Excel.
Unavailable/network/reparse/linked/changed/oversized input stays unavailable;
do not substitute the repository copy or normalize an alternate path to hide it.
A copy acquired elsewhere needs its own custody record and is not automatically
the physical file reported by Excel. A subsequent file replacement does not
change the meaning of an earlier disk snapshot.

The `runtime_disk_observation` object includes path, size_bytes, sha256,
captured_at and acquisition_method. An exact reviewed hash/size proves only the
on-disk snapshot relationship. It never establishes memory or execution identity.

## 4. Assess unsigned metadata, without reopening payload paths

```powershell
python -m tools.audit_qdkt_source_transformations `
  --assess-runtime-observation 'D:\approved-evidence' 'excel-observation.json' `
  --format json > D:\approved-evidence\observation-assessment.json
```

An observation with `on_disk: null` is valid and reports disk evidence unavailable.
Optionally prepare a separate combined metadata copy preserving both originals:
populate `on_disk` with exactly path, size_bytes, sha256, captured_at and
acquisition_method from the disk observation. Do not copy readiness/result fields.
The assessor compares exact path strings without resolving them; it never reads
a file named inside the payload. Internal mismatch rejects or reports a
contradiction. A perfectly consistent forged report still receives
`UNAUTHENTICATED_OPERATOR_CLAIMS_INTERNAL_CONSISTENCY_ONLY`,
`RUNTIME_IDENTITY_UNVERIFIED` and `UNVERIFIED_VERSION_BINDING`.

The assessor's `qdkt-runtime-assessment/v1` output exposes a separate acceptance
matrix for supplied snapshot, reviewed source, export encoding, reported disk,
build/distribution, loaded runtime, executable VBA, independent custody and
business-owner acceptance. Invalid schema/Unicode/time/path data raises a fixed
diagnostic; unavailable file acquisition stays unavailable, with no fallback.
A valid disk mismatch is `CONTRADICTED`, not an accepted runtime. A matching disk
claim is only `VERSION_BINDING_UNVERIFIED`. Disk capture chronology is reported
relative to the claimed session; a capture predating that session is explicit.
No freshness threshold or business timezone is inferred. Even altered but
self-consistent timestamps remain unauthenticated acquisition-clock claims.
Multiple process IDs or same-name paths are reported, never resolved by first,
latest or installed heuristics. No submitted manifest/custody claim can promote
business or executable-code identity through this assessor.

Exit 2 is intentional: it is NOT successful readiness. No assessment, checksum,
collector reference or installed flag is an owner/legal approval token.

## 5. Optional independent module inspection

The collector intentionally does not access VBProject or alter its trust setting.
`runtime_module_source_status=NOT_COLLECTED` must remain unless an operator
separately attempts authorized inspection. If existing permissions permit it,
use the existing session's editor to view the project/procedure without running,
editing, saving or exporting over an original. Record session/PID association,
exact project/path/procedure, acquisition method, hashes of separately captured
evidence, collector and capture times. If denied, use `ACCESS_DENIED`; never
enable Trust Center access or bypass a project password. A reported source capture
can be labelled `OPERATOR_REPORTED_SOURCE_CAPTURE` in a separate metadata copy,
but does not prove that compiled p-code or executed code matched the displayed
source. Keep raw captures outside Git and subject to independent custody review.

## Evidence request needed to close identity, not business readiness

Provide the originals with size/SHA and provenance for all of:

- Authoritative export encoding and export log linking each reviewed ZIP module
  and WinAPI to the primary project; timestamps/filenames alone are insufficient.
- Original build/packaging commands, dependency/reference manifest and distribution
  checksums binding that source set to the distributed add-in. No such mapping was
  found in the bounded repository/local evidence search.
- Operator-selected existing session observations for all relevant instances,
  independently reviewed loaded-path and disk acquisition records, with collector
  identity/custody authenticated outside the JSON claims.
- An independently reviewable method establishing load-time/in-memory executed-code
  identity and p-code/source correspondence. This protocol alone does not provide it.
- Resolved template versions from the actual invocation context and separate
  business/legal and Word acceptance. Do not execute QĐKT generation to collect these
  under this protocol.

Remain at Outcome B until independently sufficient evidence exists. Even Outcome A
must keep the 14 business-operation statuses, Process A/B separation and legal
gates unchanged without separately approved business evidence:
`decision=UNDECIDED`, Word UAT `NOT_EXECUTED`, business timezone unverified,
`ready_to_render=False`. No renderer/issuance activation, deployment, production
DB/NAS/GCS mutation or original template change. Issues #74/#144 remain OPEN.
