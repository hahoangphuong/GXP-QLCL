# Offline QĐKT owner evidence package validator

This is documentary checking, **not an approval service**. It does not select
A/B, authenticate reviewers, run Word, access production systems, change the
checked-in decision or activate rendering. Its output is untrusted audit data,
never input authority for RBAC, DocumentService or renderer gates.

The committed state remains `UNDECIDED`, timezone
`PARTIAL_UNPROVEN_BUSINESS_TIMEZONE`, actual Word UAT `NOT_EXECUTED` and
`ready_to_render=False`. Issues #74 and #144 remain open.

## Manifest and referenced schemas

Use `qdkt-owner-evidence-package/v1`. The Python schema is
`OwnerEvidenceManifest` in `tools/validate_qdkt_owner_evidence.py`; it forbids
unknown fields and coercion. This is a reference envelope, not a second approval
schema. Decision, approval-record and Word-UAT JSON files use the existing
`RendererDecision`, `ApprovalRecord` and `WordUatEvidence` schemas from #186.
No `approved=true` field is supported. Approval JSON is documentary material,
not a trusted ledger, regardless of its reviewer name or APPROVED disposition.

Every evidence entry has a unique `ref_id`, package-relative `path`, raw-file
`sha256` and `kind`. IDs use 1–64 ASCII letters/digits/underscore/hyphen and start
with a letter/digit. Supported kinds:

- `decision`: one file selected by `decision_ref`.
- `source_template`, `candidate_template`: separate references per variant.
- `word_uat`: execution-record JSON, selected by `word_uat_ref`.
- `uat_output`: exact output bytes selected by `word_output_ref`.
- `uat_screenshot`: screenshot bytes selected by each record's `screenshot_refs`.
- `approval_record`: JSON selected by `approval_record_refs`; its `record_id`
  must match a selected ID in the referenced decision's `approval_record_ids`.
- `supporting_document`: owner-supplied document referenced by each approval
  record's `evidence_ref`; wording/meaning/signature is **not** machine-verified.

The four `templates` rows have `gxp_type` GLP/GMP/GMPbb/GSP, `source_ref`,
`candidate_ref`, `candidate_version`, `word_uat_ref`, `word_output_ref`.
Missing optional references are allowed in an incomplete dossier but produce
blockers. Duplicate variants, IDs, path aliases and orphan references block.
There is no filename-, path- or checksum-based identity fallback.

`decision_sha256` is the existing canonical `decision_digest`, **not** the raw
decision JSON checksum. The decision evidence reference also pins that file's
raw SHA. Candidate SHA and version must agree between manifest and decision;
source SHA must match the repository's independently pinned source registry.
The report records candidate version hashes rather than free-text version
labels, and exports no reviewer names, legal text or filesystem paths.

Safe, intentionally incomplete example (zero hashes are placeholders and block):

```json
{
  "schema_version": "qdkt-owner-evidence-package/v1",
  "decision_ref": "decision",
  "decision_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "templates": [
    {"gxp_type": "GLP"},
    {"gxp_type": "GMP"},
    {"gxp_type": "GMPbb"},
    {"gxp_type": "GSP"}
  ],
  "approval_record_refs": [],
  "evidence": [{
    "ref_id": "decision",
    "path": "decision.json",
    "kind": "decision",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  }]
}
```

## Owner procedure

1. Prepare isolated local copies with the existing Word-UAT preparation tool;
   never edit authoritative originals. Its `qdkt-word-uat-package/v1` output
   is a preparation inventory, **not** this validator's manifest. Do not rename
   its schema or automatically promote its flags into evidence.
2. Legal/business owners choose A/B and document the decision, wording or
   omission, exact candidate versions/SHA, date normalization/display policy and
   supporting review documents. Create a separate decision JSON in the package;
   do not populate the checked-in UNDECIDED file automatically.
3. A requires exactly one balanced `HsDK` and `NgaynopHsDK`, exact story/XML
   locations, no case variants/nesting/overlap, separate candidate checksum and
   version, and legal wording/placement evidence. B requires both names absent,
   no placement, explicit deprecation evidence plus legal/business acceptance
   of omitted fields. Canonical approval purposes/roles are unchanged.
4. Follow the actual four-variant Word procedure in
   [QDKT_RENDERER_DECISION_WORD_UAT.md](QDKT_RENDERER_DECISION_WORD_UAT.md).
   Record Word build, tester, offset-bearing time, output SHA, screenshots and
   all acceptance checks only after execution. `evidence_origin` is UNVERIFIED
   by default. Do not label synthetic execution as actual Word. The CLI checks
   declarations and file consistency, not whether the declarations are true.
5. Reference review documents and documentary exports from the real owner
   review process. Never invent approvals. WORD_UAT acceptance binds the
   `word_uat_digest` of all four records and cannot predate their executions.
   Changing decision content or UAT content requires renewed owner review.
6. Assemble the reference manifest, pin raw file hashes, and run from repo root:

   ```powershell
   python -m tools.validate_qdkt_owner_evidence --manifest C:/isolated/package/manifest.json --format json
   python -m tools.validate_qdkt_owner_evidence --manifest C:/isolated/package/manifest.json --format markdown
   ```

Both formats go only to stdout. There is no report-file writer or overwrite
option. If an auditor archives stdout, the auditor owns exclusive creation of a
new destination outside the source package. Exit status is **always 2**: offline
checking never provides a successful authorization signal. A malformed CLI
invocation also uses argparse's exit 2. Inspect the structured findings instead.

## Report meanings

- `evidence_complete`: no documentary schema/reference/content/scope blockers.
  Even a forged but internally consistent dossier may satisfy this value.
- `trusted_authorization_verified`: always false; no trusted owner system is
  connected and package JSON never enters preflight's trusted-ledger argument.
- `word_uat_verified`: always false; no real Word operation or visual review is
  independently observed. Documentary execution metadata does not prove UAT.
- `ready_to_render`: always false, regardless of documentary completeness.
- `documentary_blockers` versus `trust_blockers`: separate missing/inconsistent
  documents from the non-negotiable lack of authenticated authorization/UAT.
- Provenance: report/manifest schema versions, SHA of exact manifest bytes,
  canonical decision digest, candidate/version hashes, per-reference declared
  and observed SHA/status, selected date policy and both owner checklists.
  `version_matches_manifest` is null when either version is missing; two absent
  versions never produce a positive match claim.

JSON has stable ordering and no wall-clock timestamps. Markdown embeds exactly
the same JSON. Reordering/changing manifest bytes deliberately changes its SHA.
Reports include findings only, never Pydantic payloads or filesystem exceptions.

## Blocker catalogue

All codes start `QDKT_PACKAGE_`. Suffixes identify only a safe reference ID,
canonical GxP, evidence kind, approval purpose or exact bookmark name.

| Code suffix | Meaning / owner action |
|---|---|
| `SCHEMA_INVALID`, `JSON_INVALID`, `JSON_DUPLICATE_KEY` | Fix schema/type/encoding/duplicate keys; no last-key-wins parsing. |
| `PATH_UNSAFE`, `LINK_FORBIDDEN`, `FILE_TYPE_INVALID`, `FILE_UNAVAILABLE` | Supply regular local files through safe paths; links, special files and hardlinks are forbidden. |
| `FILE_TOO_LARGE`, `FILE_CHANGED` | Reduce input size or provide a stable snapshot; no blind retry. |
| `PLATFORM_UNSUPPORTED` | Required safe acquisition primitives unavailable; do not bypass the reader. |
| `REFERENCE_DUPLICATE`, `REFERENCE_PATH_CONFLICT`, `REFERENCE_MISSING`, `REFERENCE_KIND_OR_ID_INVALID`, `UNREFERENCED_EVIDENCE` | Correct reference identities, kind, ownership and unused/aliased entries. |
| `REFERENCE_SHA_CONFLICT` | Raw referenced bytes differ from the manifest pin. |
| `VARIANT_SET_INVALID`, `DECISION_UNAVAILABLE`, `DECISION_DIGEST_CONFLICT`, `DECISION_UNDECIDED`, `DATE_POLICY_UNDECIDED` | Supply four unique variants and the correct explicitly reviewed decision/policy; do not let the tool choose. |
| `SOURCE_TEMPLATE_SHA_CONFLICT`, `CANDIDATE_TEMPLATE_SHA_CONFLICT`, `CANDIDATE_UNDECLARED`, `CANDIDATE_VERSION_CONFLICT`, `CANDIDATE_NOT_INDEPENDENT` | Reconcile source/candidate identities and independently approved SHA/version. |
| `TEMPLATE_BINARY_INVALID`, `PLACEMENT_INCOMPLETE`, `BOOKMARK_CONFLICT`, `DEPRECATION_PLACEMENT_CONFLICT`, `DEPRECATED_BOOKMARK_PRESENT` | Check bounded ZIP/DOTX content and exact A/B target rules; no legal layout inference. |
| `APPROVAL_REFERENCE_DUPLICATE`, `APPROVAL_RECORD_INVALID`, `APPROVAL_RECORD_CONFLICT`, `APPROVAL_SELECTION_CONFLICT`, `APPROVAL_DOCUMENT_MISSING`, `APPROVAL_SCOPE_CONFLICT`, `APPROVAL_SUBJECT_UNEXPECTED` | Correct documentary selection/purpose/role/disposition/digest/time/evidence links. Still not reviewer authentication. |
| `WORD_UAT_SET_INCOMPLETE`, `WORD_UAT_INVALID`, `WORD_UAT_IDENTITY_CONFLICT`, `WORD_UAT_NOT_ATTESTED`, `WORD_UAT_INCOMPLETE`, `WORD_UAT_TIME_INVALID`, `WORD_UAT_OUTPUT_CONFLICT`, `UAT_SUBJECT_CONFLICT`, `UAT_ACCEPTANCE_TIME_CONFLICT` | Reconcile four execution declarations, inputs, output/screenshots, offset times and acceptance digest; perform actual UAT separately. |
| `AUTHORIZATION_NOT_VERIFIED`, `WORD_EXECUTION_NOT_VERIFIED` | Permanent offline trust blockers; only separately authenticated review/actual UAT can establish these facts. |

## Local read boundary and limits

The manifest's explicit parent directory is the package root. References are
relative slash-separated portable ASCII components (interior spaces allowed),
without `..`, absolute/UNC/device/ADS paths, reserved Windows names, trailing
dots/spaces, symlinks/junctions or hardlinks. Trusted repository metadata is read
separately by existing contract validators; it is not supplied by the package.

POSIX acquisition uses no-follow directory descriptors for every ancestor and
the file. Windows pins ancestors and the file with handles denying write/delete
sharing, rejects reparse points, and compares final handle paths. File type,
link count, size and before/after metadata are checked; hashing/parsing consumes
the same bounded captured bytes, never a reopened path. Files and directories
are never created, changed, extracted or deleted by the CLI.

Limits: 1 MiB manifest/JSON evidence, 32 MiB other files, 128 MiB acquired package
bytes, 128 references, 16 approval references, 256 ZIP members and 64 MiB declared
uncompressed template content, plus the existing per-Word-part audit limits.
Supporting documents, outputs and screenshots are hashed but not executed or
visually interpreted. This is content consistency, not filesystem freshness,
an atomic cross-file snapshot, immutable storage generation or legal truth.

Still missing in the real repository: A/B owner decision, four approved
candidate versions/checksums and A placements/wording or B deprecation,
dossier/date policy approval, authenticated owner ledger integration and actual
four-variant Word UAT/acceptance. No synthetic test closes those gaps.
