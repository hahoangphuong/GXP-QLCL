# QĐKT — offline Case↔db.ktra cohort audit

This workflow is **read-only evidence collection**. It does not certify that a
`db.ktra` ID identifies the VBA-selected KHKT row, and it does not enable
QĐKT document creation.

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
  `ready_to_render=False` regardless of cohort coverage.
* **Separate business lineage work:** prove precisely which VBA-selected
  planning row supplied `DaychuyenDD`, `Tinhthanh`, and `TTVdd` for
  each Case. No free-text heuristic or joins by displayed name.
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
