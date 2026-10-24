# QĐKT — offline Case↔db.ktra cohort audit

This workflow is **read-only evidence collection for historical import identity**, not a prerequisite for creating or rendering a modern Case. **Business-confirmed rule:** on creation, Case data is entered by the user, or inherited from the originating Case for eligible repeat/reinspection workflows. No Case-creation field is sourced from KẾ HOẠCH KIỂM TRA (KHKT). An ID join to `db.ktra` cannot authorize QĐKT creation.

## Input provenance and execution

1. Obtain **Danh sách Kiểm tra GPs.xlsb** from the authorized legacy source,
   verify its SHA-256 equals
   `c12537ea5a5c9f470e42fb5bdbe214f36983e310fceac7c560ad38885209fe3d`.
   Do not modify the original workbook.
2. On an authorized offline workstation, use
   `backend.app.domain.legacy_snapshot_v2.build_snapshot(Path(...))`
   and `snapshot_bytes(...)` to create the `legacy-workbook-snapshot/v2`
   JSON. This is **different** from `db_ktra_semantic_inventory.json` or
   the normalized importer input.
3. Independently confirm the exact `db.ktra` source header row number and
   record the workbook/sheet evidence. Literal `ID` and uniqueness are
   rechecked by the CLI; merely finding a matching value does not prove
   header provenance.
4. Export a read-only, access-controlled JSON array of canonical Case pairs
   from **rehearsal**, with precisely:
   `[{"case_id": "<uuid>", "legacy_inspection_id": 123}, ...]`.
   A null legacy ID is allowed. Do not export names, addresses, inspection
   data or passwords. Do not copy this input into the Git repository.
5. Run locally in the repository's pinned Python environment:

```bash
python -m tools.audit_qdkt_snapshot_cohort \
  --snapshot /protected/legacy-workbook-snapshot-v2.json \
  --cases-json /protected/case-ids-rehearsal.json \
  --attested-header-row <SOURCE_ROW_NUMBER> \
  --confirm-header-provenance \
  --output /protected/qdkt-case-db-ktra-aggregate.json
```

The output records SHA-256 digests of both inputs, total Case count and
aggregate statuses. It deliberately does **not** include Case IDs, personnel,
raw cells, source row numbers, or business text.

Never substitute old semantic inventory row counts for a real cohort match
rate. The source snapshot hash is a hash of the exported JSON bytes; the
embedded workbook checksum independently proves the original XLSB identity.

## Acceptance gates

* Unique source ID is only a candidate `db.ktra` link; missing/duplicate
  source IDs remain explicitly classified.
* Sparse absent ID cells are skipped without inventing identities, whereas
  duplicate coordinate cells, an entirely unobserved ID column, a false
  header, or wrong workbook SHA fail closed.
* `planning_row_proven=False`, `qdkt_business_atoms_proven=False`,
  `ready_to_render=False` here reflect the **historical audit's limited scope**, not an unsatisfied KHKT prerequisite for modern Case workflows.
* **Separate modern QĐKT contract:** derive document atoms from persisted Case-owned inputs (user-provided or inherited from the original Case), including the Case's inspection team and associated registered site. Validate the selected fields against QĐKT template bookmarks. Do not fetch, infer, or backfill them from KHKT. If a necessary Case field is missing, require a Case-owned input rather than a planning-sheet join.
* No production QĐKT POST, schema change, document storage, VM/NAS writes,
  or alteration of historical exceptions.

## Private report output safety

The CLI now creates the aggregate JSON only after all source and cohort
validation gates pass. It uses exclusive file creation (`O_EXCL`) with POSIX
permissions `0600`, and fails if the output already exists, is a symlink, or
resolves to either input. It does **not overwrite** a previous report. Use a
new path per verified run in a private directory; do not commit cohort inputs
or their report without a separate disclosure review. CLI validation errors
are intentionally generic and do not echo source cells or Case IDs.

## Optional automated read-only rehearsal Case export

When an authorized rehearsal-only database account is available, the minimal
Case cohort may be exported without manual SQL copying:

```bash
# Supply the PostgreSQL URL securely through the named environment variable.
# It must target database gxp_legacy_rehearsal, NOT gxp_qlcl.
python -m tools.export_qdkt_case_cohort_readonly \
  --database-url-env QDKT_REHEARSAL_DATABASE_URL \
  --output /protected/case-ids-rehearsal.json
```

The exporter allows only a PostgreSQL connection whose database is named
`gxp_legacy_rehearsal`. It starts an explicit `SET TRANSACTION READ ONLY`
transaction and reads only `Case.id` and `Case.legacy_inspection_id`,
then writes a private mode-0600 JSON array with exclusive file creation.
Do not publish the input JSON or database URL. Use a credential restricted
to SELECT as an additional independent protection, and only on the authorized
rehearsal environment. The export does not prove source-lineage equivalence.

## Optional private exception investigation

When aggregate counts show missing or duplicated links, request a **separate**
private exception manifest. The ordinary aggregate output remains free of Case
identifiers. The exception manifest contains only Case IDs and unresolved
classification statuses, not inspectors, facility names, source cells, or
arbitrarily selected source row numbers.

```bash
python -m tools.audit_qdkt_snapshot_cohort \
  --snapshot /protected/legacy-workbook-snapshot-v2.json \
  --cases-json /protected/case-ids-rehearsal.json \
  --attested-header-row <SOURCE_ROW_NUMBER> \
  --confirm-header-provenance \
  --output /protected/qdkt-aggregate-new.json \
  --exceptions-output /protected/qdkt-exceptions-private-new.json
```

Exception output is **opt-in**, mode `0600`, exclusive-create only. Never
upload it into GitHub, CI artifacts, issue comments, or public documentation.
The manifest includes the SHA digests of its snapshot/cohort inputs so it
cannot be mistaken for another source run. A Case with `SOURCE_ROW_UNIQUE` is intentionally omitted; that result is only a historical `db.ktra` identity match and neither establishes nor replaces modern Case-owned QĐKT input validation.

## Snapshot content-integrity gate

Before matching Case IDs, the offline CLI verifies the `db.ktra` sheet's
`content_sha256` using the same deterministic `raw_rows` JSON canonicalization
as `legacy_snapshot_v2._sheet_payload`. It checks the row and cell-coordinate
counts and sheet width against the extractor's recorded inventory. A JSON file
with a legitimate-looking workbook SHA but edited source IDs is rejected.

This **does not cryptographically prove workbook authorship**: an adversary
with control of the whole JSON file could recompute its digest. Keep original
XLSB checksum verification, independently attested header-row provenance,
and trusted acquisition of the snapshot as separate mandatory gates.
Older partial/synthetic Snapshot V2-shaped JSON without extractor integrity
fields must not be substituted for a complete extractor output.
