# QĐKT — Rg3 dossier-row and canonical identity evidence gate

This is a read-only, offline evidence assessment. It proves a narrower fact than document ownership: for the MainForm history route, the exact selected `db.ktra` row can be followed to one canonical Case, its CaseApplication and its registered Site. It does not authorize rendering or change the Issue #74 owner classifications.

## Legacy selection trace

The runtime route is selection-driven, not a lookup by facility name, dossier code or date:

1. `MainForm.UpdateListHistory` calls `LoadMappingList` with exact Site ID and GxP filters and, for the applicable GMP view, the production-line code (`MainForm.frm:2792-2808`).
2. `LoadMappingList` scans the whole named range, records every matching row index and has no uniqueness tie-break (`Module1.bas:2148-2238`).
3. The visible list is date-sorted. A prior selected source row is retained if present; otherwise the first displayed row becomes selected (`MainForm.frm:2827-2833`).
4. The hidden first list column stores the `db_ktra` named-range row index. `Get_IdxKtra` returns that exact index (`MainForm.frm:629-632`).
5. `PrepareRecordFormData` assigns it to `Idx_Ktr` (`RecordForm.frm:441-465`).
6. `GetTT_Ktra` executes `Set Rg3 = Names("db_ktra").RefersToRange.Rows(Idx_Ktr)` and reads both dossier fields from that same row (`RecordForm.frm:326-405`).

Within that route, `Rg3` is procedure-local: it is declared at `RecordForm.frm:327`, assigned once at line 334 and released at line 411. The other local declarations at lines 417 and 431 belong to separate procedures (`db.Tdoi` and another `db_ktra` read) and never assign the dossier variables. No reassignment of the dossier-row `Rg3` occurs before `s_MaHsDk`/`s_NgaynopHsDk` are captured at line 343.

The workbook-pinned name is `db_ktra = db.ktra!$A$5:$CV$1549`; named-range index `n` therefore maps to physical worksheet row `n + 4`. The named-range index is not the inspection ID: 917 of 1,496 effective rows have different values.

### Cardinality and tie-break behavior

- Zero filter matches: no history row exists to select, so no `Rg3` dossier row is established.
- One match: that row is selected.
- Multiple matches: all rows remain distinct; the retained UI selection wins, otherwise the first row after display sorting wins.
- Duplicate dossier values and multiple Cases at one Site do not collapse records. Only the selected source row and its legacy inspection ID cross the identity boundary.

## Independent KHKT route

`TaoQDKT_KHKT` reads an ActiveSheet planning row and calls `CreateFile(..., 2, ...)` (`Module1.bas:595-650`). It does not assign `Rg3`, `s_MaHsDk` or `s_NgaynopHsDk`. The only observed assignment of the two dossier variables is from `Rg3` in `RecordForm.frm:343`.

Consequently, the KHKT ActiveSheet route has **no proven db.ktra dossier-row identity**. It must not borrow the MainForm history crosswalk or manufacture a match from names, dates or dossier text.

## Canonical crosswalk

For an effective `db.ktra` row, the importer:

- creates a Case keyed by the row's `legacy_inspection_id`;
- resolves the Case Site through the same row's legacy Site ID;
- creates the Case's one-to-one CaseApplication from that same normalized row, including the literal `dossier_code` and `submitted_on` projections; and
- stores a `LegacyInspectionStorageAnchor` tying the Case to the physical `db.ktra` source row and pinned workbook version.

The accepted identity chain is:

`selected named-range index → physical db.ktra row → legacy inspection ID → canonical Case → CaseApplication + Site`

The anchor's source row/version/hash must agree. Site, display name, dossier value or date alone are never join keys.

Privacy-safe recomputation from the committed snapshot applies the importer's exact Site-FK eligibility rule. A local read-only check of the excluded raw anchor projection pins its aggregate parity result into the tracked contract; when that local projection is present, tests recompute all 1,496 inspection-ID/source-row pairs directly.

The combined evidence establishes:

| Check | Result |
|---|---:|
| Snapshot `db.ktra` rows | 1,543 |
| Effective anchored rows / unique inspection IDs | 1,496 / 1,496 |
| Exact anchor inspection-ID + physical-row matches | 1,496 |
| Legacy ID differs from named-range row index | 917 |
| Sites with more than one Case / maximum Cases at one Site | 276 / 17 |
| Non-placeholder dossier rows | 1,012 |
| Duplicate dossier values / rows carrying one | 138 / 486 |

These aggregates prove why neither Site nor dossier text is a safe record key. The machine-readable contract contains no raw business values; the raw anchor projection remains excluded from Git by repository hygiene policy.

## What is and is not proven

| Question | Status | Reason |
|---|---|---|
| MainForm selected `Rg3` row | `PROVEN` | Hidden row index is passed unchanged into `Idx_Ktr`; `Rg3` indexes the pinned named range. |
| Canonical Case/Application/Site identity | `PROVEN` | Exact legacy inspection ID, Site FK and storage-anchor coordinates agree. |
| Dossier code literal projection | `PROVEN` | Import and render source use the same normalized `db.ktra` row. |
| Submission date literal projection | `PROVEN` | Parsed source value equals `CaseApplication.submitted_on`. |
| Meaning of submission date | `OWNER_PARTIAL` | Evidence does not resolve “submitted” versus “received” business semantics. |
| KHKT planning-row dossier identity | `OWNER_BLOCKED` | That route does not select or assign `Rg3`. |
| Physical `HsDK` / `NgaynopHsDK` bookmarks | `OWNER_BLOCKED` | All four verified templates lack the physical bookmarks; this is separate from record identity. |
| Modern render owner / renderer readiness | `OWNER_BLOCKED` | Identity proof is necessary but not sufficient for legal output ownership. |

`assess_qdkt_rg3_crosswalk` fails closed for zero/multiple rows, missing or duplicate canonical Cases, zero/multiple/wrong-owner CaseApplications, changed source coordinates/version/hash, Site conflicts, value drift and ambiguous date parsing. `inspect_qdkt_rg3_baseline` recomputes the aggregate contract from committed snapshot and anchor artifacts.

The global gate remains **8 `OWNER_BLOCKED`, 6 `OWNER_PARTIAL`, `ready_to_render=False`**. No renderer, owner promotion, API, database, storage or authorization behavior is enabled by this evidence.
