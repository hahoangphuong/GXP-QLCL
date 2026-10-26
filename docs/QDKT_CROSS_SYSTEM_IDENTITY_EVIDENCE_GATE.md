# QĐKT — cross-system Case/Application/Site identity evidence gate

This is an offline diagnostic of candidate names only. It DOES NOT query live databases, prove record identity or select a modern owner.

| Legacy QĐKT symbol | Captured legacy source | Modern candidate (unproven) | Remaining question |
|---|---|---|---|
| `HsDK` | `db.ktra` selected row, `ColDB_HSDK_Ktra + 1` | `CaseApplication.dossier_code` | Which legacy `db.ktra` row matches which canonical application, including case and dossier identity? |
| `NgaynopHsDK` | Same `db.ktra` row, `ColDB_HSDK_Ktra` | `CaseApplication.submitted_on` | Is the date a submitted date, received date or other business milestone? What formatting/value rules apply? |
| `Tencoso` | Planning row cell 4 or alternate `db_cso` site row | `Site.site_name` | Which source path was selected for this QĐKT and which registered Site identity does it represent? |

Required independent evidence before source owner adjudication:
- Legacy row and canonical Case/Application/Site stable identity crosswalk (not just matching strings).
- Exact record selection and tie-break rules, including absent/duplicate historical records.
- Value and transformation parity with representative and adversarial GxP examples.
- Explicit decision on whether dossier code/date belongs in the legal QĐKT output, as all four verified templates lack both physical bookmarks.
- Review of source authority and ownership, with no silent `OWNER_PROVEN` promotion.

The `inspect_qdkt_cross_system_identity` diagnostic deliberately returns all verification flags false even if the caller passes the same candidate names as the provenance artifact. It does not authorize typed rendering. The global gate remains 8 `OWNER_BLOCKED`, 6 `OWNER_PARTIAL`, `ready_to_render=False` under Issue #74.
