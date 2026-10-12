# DDK GxP provenance source-only load plan — dry-run

**Status: SOURCE BASELINE ACCEPTED / DRY-RUN ONLY — 12 October 2026.**
The owner has waived Microsoft Excel COM as a required gate for the accepted
original XLSB export. That waiver **does not** assert formula validation PASS
and does not approve creating any canonical Certificate link or changing a
historical DDK version. See
`DDK_GXP_SOURCE_BASELINE_OWNER_ACCEPTANCE_20261012.md`.

## Owner, input and immutable acceptance conditions

Owner: `tools/plan_ddk_gxp_provenance_load.py`.

It consumes the two **original accepted read-only XLSB exports**, NOT the
flattened Phase2 importer `linked_certificate_ids` field:

- `gxp_ddk_grouped_source_projection_20261012.json`: all original 16
  physically identified source group cells per DDK row, including empty
  cells and GDP activity fields without a GDP Certificate number;
- `gxp_ddk_idcc_workbook_source_analysis.json`: 861 physical-column and
  DDK-row-bound source token observations;
- `artifacts/phase3q/confirmed_blanked_rows.json`: previously owner-approved
  exclusion decisions, validated against physical Excel row **and** DDK ID.

Input files containing private source records must be kept locally and not
committed to public GitHub. The planner requires an externally specified
**original XLSB SHA-256** and externally supplied row/exclusion/token counts,
rather than hardcoding a particular company's or workbook's data into
business logic. For the current accepted baseline:

| Invariant | Expected |
|---|---:|
| Original DDK source rows | 830 |
| Previously approved blanked rows, excluded | 50 |
| Effective DDK source rows in load preview | 780 |
| Complete four-group source provenance rows | 3,120 |
| Source field positions preserved | 12,480 |
| Reference evidence tokens (NOT canonical links) | 861 |
| GMP / GLP / GSP / GDP tokens | 851 / 9 / 1 / 0 |
| Companion-only groups | 25, including GDP activity: 6 |

The planner validates row-3 group identity through the supplied physical
source headers, checks each group contains all four consecutive source
column positions, the individual DDK physical row and original legacy ID,
the accepted workbook SHA-256, **exact multiset of source references**,
independent exclusion row keys, and all expected counts. It refuses
malformed/empty/nonpositive ID CC tokens, missing fields, mismatched source
group identities, overwritten/modified inputs and nonempty excluded rows.
It does **not** assume `physical_excel_row = legacy_dkkd_id + 4`: some
genuine source rows have different offsets. A physical row number is its
own independent identity.

## Output contract

Plan JSON `GXP_DDK_GXP_PROVENANCE_DRY_RUN_V1` contains:

- `status=DRY_RUN_ONLY_NOT_APPLIED`;
- source SHA-256; original/excluded/effective row counts;
- the 3,120 original grouped source records, with all four verbatim values
  **as retained by the accepted original XLSB export**, all source column
  ordinals and deterministic SHA-256 of their four-field value array;
- 861 original semicolon token observations, with source
  row+group logical key, 1-based token position and integer parsed legacy
  ID (NOT a canonical Certificate FK);
- 50 excluded physical DDK row/ID pairs in the original source manifest;
- SHA-256 over the complete logical load payload and independent hashes of
  the exact three input JSON files.

No UUIDs are invented or preallocated; no link to
`BusinessEligibilityVersion`, `Certificate`, `CertificateVersion`,
Case, Site coverage, or ProductionLine is inferred.
`database_state=NOT_CONNECTED_NOT_INSPECTED`,
`sql_writes_executed=0` and `canonical_link_changes=0` explicitly report
what this plan **cannot** prove. An eventual writer would need a separately
authorized database-state snapshot, checked target Alembic revision
`20261012_0023`, exact uniqueness/FK guards, transaction, sealed rollback,
and independent after-image reconciliation.

### Local read-only command (from current PR #7 checkout)

```powershell
py -3 -m tools.plan_ddk_gxp_provenance_load `
  --groups-json "D:\GXP-DDK-EVIDENCE\gxp_ddk_grouped_source_projection_20261012.json" `
  --references-json "D:\GXP-DDK-EVIDENCE\gxp_ddk_idcc_workbook_source_analysis.json" `
  --approved-exclusions-json "artifacts\phase3q\confirmed_blanked_rows.json" `
  --expected-workbook-sha256 "c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d" `
  --expected-ddk-rows 830 `
  --expected-excluded-ddk-rows 50 `
  --expected-reference-tokens 861 `
  --output "D:\GXP-DDK-EVIDENCE\ddk_gxp_provenance_dry_run_20261012.json"
```

Each output path must be new: the tool never overwrites source evidence or an
earlier sealed dry-run. A source artifact drift aborts before output.

## Boundaries and future release gates

The accepted exports may have stripped surrounding text whitespace, unlike
direct Excel `Value2`. This is a known owner-accepted limitation and is not
silently "repaired" by extrapolating formula/display values. A dry-run preview
does not certify that the target PostgreSQL tables exist or are empty. The
Alembic `0023` migration has only been run on disposable CI infrastructure
so far. No target rehearsal/production DB is accessed, mutated or deployed.

Before a data-writing population slice: explicitly inspect
`gxp_legacy_rehearsal` revision, target table shape and current rows using
a read-only connection; require owner authorization for a fresh source-only
write, isolate it from canonical relationship approval, and check physical
source hashes and all row counts again. Do not alter `gxp_qlcl` or
`gmpnn_ai`, and do not merge unrelated frontend PR #3.
