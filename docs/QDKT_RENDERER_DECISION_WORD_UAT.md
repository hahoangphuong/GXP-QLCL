# QĐKT dossier renderer contract and Word UAT

Status: technical review package; legal decision **UNDECIDED**, timezone confidence
**PARTIAL_UNPROVEN_BUSINESS_TIMEZONE**, Word UAT **NOT_EXECUTED**.
`ready_to_render=False` for every result, including a complete simulated contract.
Issues #74 and #144 remain OPEN.

## Owner decision matrix

| Concern | A — ADD_BOOKMARKS | B — DEPRECATE_WRITES |
|---|---|---|
| Result | Explicit dossier code and submission date appear in four approved candidate templates. | Output intentionally retains the existing omission. |
| Benefit | Makes the attempted VBA field writes visible and testable. | Preserves current authoritative output and wording with less template change. |
| Cost/risk | Legal wording, insertion location, line wrapping and pagination require approval and Word UAT for every variant. | Owners must accept that dossier fields are intentionally absent; future reviewers must not mistake omission for a defect. |
| Exact names | `HsDK`, `NgaynopHsDK`, case-sensitive, one balanced span each; no case variants, nested or overlapping target spans. | Both names absent; neither scalar write may be dispatched. |
| Placement | **EVIDENCE_MISSING_OWNER_DECISION** for each target in each variant. The existing dossier prose is only a location for owner review, not an authorized insertion point. Approve exact story part, start/end XML paths and semantic context in the decision. | No insertion or replacement. No placement record allowed. |
| Source values | Present, exact Case/Application/Site, version and normalized values must agree before a future renderer can use them. Missing/conflicting values block. | This technical gate still checks source provenance; it does not grant a missing-data waiver. Omitting display fields needs a distinct approved deprecation record. |
| Legal wording/format | Preserve wording, character/paragraph styles, sections, tables, headers, footers and signatures unless each change is explicitly approved. | Preserve existing legal wording and layout. |
| Version/checksum | New independently versioned candidate, different SHA from original, all four variants pinned. | Explicit version/checksum for each approved unchanged template or reviewed candidate. |
| Calls affected | Future QĐKT adapter would map the two approved fields to exact bookmark spans. | Future QĐKT adapter must exclude both operations; owner-authorized legacy maintenance would remove/disable `RecordForm.frm:748-749` writes for i=2, without altering KHKT/BBKT branches. |
| Legacy compatibility | Deliberate visible difference from the existing silent-no-op output. | Existing output retained; omission becomes an explicit audited behavior. |
| Adoption | Legal owner approves template content; business owner approves semantics/date rule; UAT owner accepts exact Word evidence. | Same approvals plus legal-owner `DEPRECATE_WRITES` authorization. |
| Rollback | Withdraw candidate approval, return decision to UNDECIDED, retain originals and prior checksum/version. | Revoke deprecation approval and return UNDECIDED; do not silently resume writes into absent targets. |

Neither option is selected in this PR. The checked-in
`backend/app/document/inspection_qd_kt_renderer_decision.json` has null candidate
versions/checksums, no placement and no approval references. Editing a decision
invalidates approval digests; changing UAT evidence invalidates its approval's
subject digest. Approval references resolve only against a **trusted internal
owner-review ledger**, never a browser payload. This validator scopes evidence;
it does not authenticate reviewers or implement an approval service.

## Confirmed lineage and date contract

Primary sources and hashes remain in `QDKT_DOSSIER_LEGACY_SOURCE_PAIR.md` and
PR #159's source artifact. Legacy `RecordForm.frm:334,343` reads column I/H of
the same selected Rg3 row. Workbook group `ĐĂNG KÝ`, labels `Mã hồ sơ` / `Ngày nộp`
and named ranges prove dossier code / submission date. The writer at 748–749
applies only `Replace('-', '/')`; `Replace_Bookmark:589-603` silently ignores
missing targets. All four originals lack both target bookmarks.

Modern source is the **current persisted CaseApplication**, joined by canonical
Case and registered Site UUIDs. Historical Rg3 reconciliation is independent;
modern Cases with no legacy ID do not need a workbook or KHKT join. The new
reader selects scalar database columns under `no_autoflush`: it does not flush,
overwrite pending edits, or use cached ORM values. Transaction isolation still
limits visibility; no atomic DB/template snapshot is claimed. The caller owns
authorization, transaction scope and expected version capture.

| Evidence | Established fact | Limit |
|---|---|---|
| Initial Alembic revision `7ad763833b09`, `case_application` | `submitted_on` is `sa.DateTime(timezone=True)`, PostgreSQL `TIMESTAMP WITH TIME ZONE`. | Schema declaration is not a live production DB inspection. |
| Current `CaseApplication` ORM | `Mapped[datetime | None]`, `DateTime(timezone=True)`. | Not `Date`, despite date-oriented UI. |
| Migration history | No later migration changes this column. `Date` fields in revision 0012 belong to approval submissions, not CaseApplication. | Do not borrow semantics across tables. |
| API/workflow | `CaseApplicationUpsertRequest.submitted_on` accepts `datetime`; workflow assigns the provided value. | No business timezone policy is enforced there. |
| Legacy importer `phase2_import.parse_dt` / application import | Parses date formats to naive `datetime`; strips literal `+00:00` in its compatibility parser. | Does not establish UTC or Vietnamese timezone. This PR does not change migration behavior. |

Pure `normalize_submission_date` supports only:

- `ISO_DATE_ONLY`: a real `date` or strict `YYYY-MM-DD`, preserving the calendar day.
- `AWARE_RECORDED_OFFSET_DATE`: an aware ISO timestamp, preserving its recorded
  offset's calendar day. This is a **proposal requiring business-owner approval**,
  not a claim that the stored offset is the business timezone.
- `UNDECIDED`, naive timestamps (including midnight), invalid/ambiguous strings
  and implicit timezone conversions fail closed. No guessed timezone or offset
  stripping occurs. Equal instants with different recorded calendar days remain
  conflicting source representations.

PostgreSQL can return the same instant with a session-dependent offset. Therefore
owners may reject the proposed recorded-offset rule and require a different
future contract. No rule is activated here; the unresolved business decision
keeps confidence PARTIAL.

## Preflight state and approval responsibilities

`assess_renderer_preflight` collects distinct blocker codes for identity/value
conflict, missing source, stale version, date conversion, unapproved decision,
missing/stale/rejected ledger records, template SHA/version, physical bookmark
absence/casing/placement, synthetic evidence, and missing/mismatched Word UAT.

Sequence: persisted owner comparison → date contract → scoped legal/business
approval → exact candidate audit → physical target rule → four Word UAT records
and UAT-owner acceptance. All incomplete states return
`contract_evidence_complete=False`. A complete internal evidence set returns
`contract_evidence_complete=True`, **still `ready_to_render=False`**. This module
is not wired into an endpoint or DocumentService and cannot override any source,
team, renderer, storage, issuance, RBAC or idempotency gate from #74/#144.

Approval roles: LEGAL_OWNER for LEGAL_TEMPLATE and (B) DEPRECATE_WRITES;
BUSINESS_OWNER for DOSSIER_SEMANTICS and DATE_NORMALIZATION; UAT_OWNER for WORD_UAT.
Each ledger entry includes reviewer reference, recorded approval time with
offset, evidence reference, disposition and decision SHA. WORD_UAT also binds
the SHA of all four execution records. No self-reported `approved=true` field is
supported. Real ledger integration and reviewer authentication remain future
owner-system work; tests simulate that boundary and grant no legal acceptance.

## Four-template Word UAT matrix

Source version for each row is `legacy-sha256:<full hash>`. Candidate version,
candidate SHA, target placement and Word page are **EVIDENCE_MISSING** until
the owner selects A/B and approves candidates. Generic dossier prose coordinates
are recorded by the preparation command; no Word page is inferred from XML.

| GxP | Original DOTX | Source SHA-256 | Story parts | Actual Word UAT |
|---|---|---|---|---|
| GLP | `2. QD KT - GLP.dotx` | `c55695dbdaafa48f0b2a4211a8adda7b97443a44439d9a81de306ce98729ec19` | document paragraph 15 (outside table), header1 | NOT_EXECUTED |
| GMP | `2. QD KT - GMP.dotx` | `490d534580ce00844b6175e64ca4e2fdc345d7957be8813f0f62d03a9b82c1a5` | document paragraph 15 (outside table), header1 | NOT_EXECUTED |
| GMPbb | `2. QD KT - GMPbb.dotx` | `fec4dc35ac5fbb2f2ef6b56750fe6dcf5316dafc0898395279d9ff281b2ca771` | document paragraph 15 (outside table) | NOT_EXECUTED |
| GSP | `2. QD KT - GSP.dotx` | `890df5e2345e2927b286f4a3adb107a984825eff21e998ae253020ecac46eea1` | document paragraph 13 (outside table) | NOT_EXECUTED |

Coordinates refer to existing plain-text dossier prose, not proposed bookmark
placement. `test_inspection_qd_kt_submission_timestamp_postgres.py` additionally
queries the real column type in disposable CI PostgreSQL and demonstrates the
same instant returning different calendar days under two explicit session zones.
It reads no business rows and does not prescribe either zone for production.

## Reproducible isolated procedure

1. From repository root, verify original hashes and prepare a **new** local package:

   ```powershell
   python -m tools.prepare_qdkt_word_uat --template-dir legacy/Templates --output .codex/evidence/qdkt-word-uat-20261027
   Get-FileHash '.codex/evidence/qdkt-word-uat-20261027/*.dotx' -Algorithm SHA256
   ```

   Existing output directories are refused. The tool copies verified originals,
   synthetic input JSON and this procedure. It creates no rendered document;
   `execution=NOT_EXECUTED`, `candidate_approved=false`. Original files stay intact.

2. Legal/business owners review A/B and the date policy. For A, edit **separate
   candidate copies**, approve exact legal context and target bookmark locations
   via Word Insert → Bookmark, preserving case; never edit originals. For B,
   explicitly authorize omission/deprecation. Record approved version and SHA for
   all four, exact placements for A, and trusted ledger references. Revalidate
   with `RendererDecision.model_validate_json` and `inspect_renderer_candidates`.
   Any changed checksum needs a new approval and UAT execution.

3. On the isolated Windows UAT workstation record Word build, tester and time:

   ```powershell
   $qdktWord = New-Object -ComObject Word.Application
   try { $qdktWord.Version; $qdktWord.Build } finally { $qdktWord.Quit() }
   Get-Date -Format o
   ```

   Microsoft Word presence alone is not UAT. No approved modified template was
   supplied for this task; therefore actual Word execution is NOT_EXECUTED.

4. For **each approved candidate**, use Word File → New → Personal/custom template
   to create a new synthetic DOCX. Use only code `UAT-SYNTHETIC-001` and ISO source
   date `2026-01-02`. The exact approved display string and legal sentence must be
   recorded by owners before testing (currently EVIDENCE_MISSING). For A populate
   only the two approved targets in this isolated document; verify exact values
   and no duplicate/hidden old value. For B verify neither write is attempted and
   both fields are intentionally omitted under the approval reference.

5. Execute missing-code, missing-date, wrong Case/Application and stale-template
   scenarios through the pure preflight regression before opening Word. Expected:
   distinct blocker and no document dispatch. These negative UAT checks are not
   satisfied merely because a Word document looks correct.

6. Compare baseline and candidate side by side in **Microsoft Word Print Layout**.
   Capture every affected page plus signature, header/footer and page boundaries.
   Record page number, table/cell if applicable and paragraph for each target.
   Confirm no changed legal wording beyond approved additions; no clipped text,
   orphaned signature, unexpected blank page, altered section numbering, lost
   fonts/styles, broken tables, margins or header/footer positioning. Page count
   and wrapping must equal baseline unless owner explicitly accepts the exact
   difference. Test a long synthetic code up to the canonical 128-character
   limit and date boundary cases separately; screenshot any wrapping changes.

7. Save outputs only inside the isolated package; compute exact output SHA with
   `Get-FileHash -LiteralPath <synthetic-output.docx> -Algorithm SHA256`. Record
   Word version/build, tester reference, timestamp with offset, screenshot refs,
   input SHA, template version/SHA, output SHA and all eight acceptance checks in
   `WordUatEvidence`. A failure or missing item remains blocking. The UAT owner
   approves the digest of the four evidence records through the trusted ledger.
   Archive package checksums; do not commit binaries/screenshots/person names.

## Regression and reproduction

```powershell
python -m pytest tests/test_inspection_qd_kt_renderer_contract.py tests/test_prepare_qdkt_word_uat.py -q -p no:cacheprovider
python -m pytest tests/test_inspection_qd_kt_dossier_bookmark_evidence.py tests/test_inspection_qd_kt_dotx_binary_audit.py tests/test_inspection_qd_kt_cross_system_identity_evidence.py tests/test_inspection_qd_kt_draft_storage_audit.py -q -p no:cacheprovider
python tools/check_repo_hygiene.py
```

Synthetic positive tests exercise both decisions only in memory. They do not
change the committed UNDECIDED record or prove original Word behavior. Supported
CI uses Python 3.12/Linux and all six required jobs; local Windows/Python 3.14
limitations must be reported separately.

## Risks, rollback and remaining decisions

- Legal owner: choose A or B and approve all four exact versions, wording,
  locations/display format, or intentional omission. No option has authority yet.
- Business owner: choose date-only domain semantics versus timestamp and explicit
  normalization policy; existing timestamp storage/import do not settle it.
- UAT owner: run and accept actual Word visual evidence for all four variants.
- Engineering: trusted approval ledger integration remains separate from this
  pure validation contract. No request flag can serve as its authentication.
- Independent #74 owners, team/title/other bookmark constraints remain blocking.
- Rollback of this technical package is code-only: revert its commit if needed.
  It changes no schema, runtime renderer, template registry or production data.
  For candidate adoption rollback, revoke approvals and restore the pinned prior
  template version through a separately approved release. Never overwrite source
  templates; preserve candidate history and failed UAT evidence.
