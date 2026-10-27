# QĐKT dossier bookmark and submission-date evidence

This is a read-only primary-source audit. It connects the authoritative QĐKT
template bytes, the VBA `Rg3` assignment path and the canonical
Case/Application/Site crosswalk. It does not enable document creation.

## Primary sources

| Source | Pinned identity | Relevant evidence |
|---|---|---|
| `Danh sách Kiểm tra GPs.xlsb` | SHA-256 `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d` | `db_ktra = db.ktra!$A$5:$CV$1549`; row 3 group `ĐĂNG KÝ`; row 4 columns H/I `Ngày nộp` / `Mã hồ sơ`; named ranges `db_NgayDky_ktra` and `Ngay_nop_HS`. |
| `GXP-VBA code.zip` | SHA-256 `6227fb0a6b3d74fa0f4cc655b94b021a40d65a508c2f2eefc62f1724c7b89ff7` | `RecordForm.frm:334,343,589-603,748-749`. |
| Four `2. QD KT - *.dotx` originals | SHA-256 values pinned by `inspection_qd_kt_template_assets.json` | Full `word/document.xml` plus every present `word/headerN.xml` / `word/footerN.xml` story part. |

The privacy-safe observation is stored in
`artifacts/legacy_audit/inspection_qd_kt_dossier_bookmark_source_evidence.json`.
It contains coordinates, hashes and aggregate structure only—no dossier value,
facility name or personal identifier.

## Physical bookmark result

| Variant | SHA matches manifest | Scanned parts | `HsDK` | `NgaynopHsDK` |
|---|---:|---|---|---|
| GLP | yes | document + header1 | `VERIFIED_ABSENT` | `VERIFIED_ABSENT` |
| GMP | yes | document + header1 | `VERIFIED_ABSENT` | `VERIFIED_ABSENT` |
| GMPbb | yes | document | `VERIFIED_ABSENT` | `VERIFIED_ABSENT` |
| GSP | yes | document | `VERIFIED_ABSENT` | `VERIFIED_ABSENT` |

There are no exact-case or case-variant starts for either target, hence no
target bookmark ID, end, XML location, enclosing paragraph, field-code context
or span to record. Generic template prose mentions a dossier request, but it is
plain text and is not either target bookmark. Other bookmarks do contain nested
and overlapping spans; the audit records these instead of mistaking them for a
target or rejecting a structurally valid legacy package.

VBA nevertheless calls `Replace_Bookmark` for both names. That helper runs
under `On Error Resume Next` (`RecordForm.frm:589-603`), so the missing targets
silently no-op. The source therefore proves an attempted write, not a physical
field in the current authoritative templates.

## Runtime values and semantics

`RecordForm.frm:343` reads both values from the one selected `Rg3` row:

- `s_MaHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra + 1).Value`;
- `s_NgaynopHsDk = Rg3.Cells(1, ColDB_HSDK_Ktra).Value`.

The writer passes the code unchanged to `HsDK` and applies only
`Replace("-", "/")` to the date string before attempting `NgaynopHsDK`.
This is display punctuation replacement, not date parsing or timezone
normalization.

The workbook itself closes the former semantic uncertainty: column H is under
the `ĐĂNG KÝ` group, is headed `Ngày nộp`, and is independently named
`db_NgayDky_ktra` / `Ngay_nop_HS`. Its business meaning is therefore
`DOSSIER_SUBMISSION_DATE`, not receipt date, inspection date, decision date or
KHKT creation date. The code value in column I is `DOSSIER_CODE`.

## Canonical comparison

For the MainForm route, PR #142's exact selected-row crosswalk remains the
identity owner:

`Rg3 row → legacy inspection ID + source anchor → one Case → one CaseApplication → exact Site`

`CaseApplication.dossier_code` is a verified canonical mapping when the exact
source and canonical values agree. `CaseApplication.submitted_on` is the
correct semantic owner, but its normalization confidence remains `PARTIAL`:
the legacy input is a date-like value parsed at midnight while the canonical
column is `DateTime(timezone=True)` and no business timezone is yet proven.
Aware/naive conversion must not be guessed.

The combined gate rejects missing/duplicate template variants, wrong SHA,
malformed or duplicate bookmark spans, case-only matches, zero/multiple/stale
Case owners, wrong Site or Application, conflicting/missing dossier values,
invalid dates, stale anchors and the KHKT route without `Rg3` lineage.

## Readiness

The primary result is `PHYSICAL_BOOKMARKS_VERIFIED_ABSENT`. This resolves the
physical question but is a blocking result, not renderer approval.
`ready_to_render=False` remains mandatory. No template is rewritten, no missing
bookmark is synthesized, and no MainForm `Rg3` ownership is borrowed by KHKT.
