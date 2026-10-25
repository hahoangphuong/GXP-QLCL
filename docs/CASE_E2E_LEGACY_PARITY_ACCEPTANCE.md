# Case end-to-end acceptance baseline vs. legacy Excel/VBA (2026-10-25)

Pinned repository source: `9e48206e75508143017f77c9094f77ec5a0405bd`. Machine-readable source-level checklist: `artifacts/legacy_audit/case_e2e_parity_acceptance_v1.json`.

## What this proves (and does not)

This matrix records **source-level** evidence only: a frontend symbol and backend module exist for some steps, while other steps are blocked or internal-only. It does NOT certify that each step has been tested in a real browser, works on a deployed system, produces a Word binary matching VBA or is approved for production. All 12 steps are initially `uat_state=not_verified` and `production_parity=false`.

Original legacy owner map: `docs/LEGACY_SYSTEM_MAP.md`, including `MainForm`, `RecordForm`, `FilterForm`, `TTVForm` and Synology/Office automation. Frontend implementation is concentrated in `frontend/src/pages/SearchPage.tsx`; note that `/reports` remains a placeholder in `frontend/src/App.tsx`. Do **not** assume all of `/workflow` or `/documents` being placeholder means there are no real Case operations in Search.

## First Case workflow to complete

| Step | Current code evidence | Remaining acceptance |
| --- | --- | --- |
| 1. Search Site and select explicit Case | `searchFacilities`, `getCaseWorkspace` in SearchPage | Real A/B OIDC tests: selection, stale response, 403, historical exception handling |
| 2. Create/update Case | `createInspectionCase` and workflow routes | Real authorized create; Case→Site→GxP ownership and audit verified |
| 3. Enter KHKT and team | `upsertInspectionPlan`, `upsertInspectionTeam` | Real persistence, concurrency/version conflict, reload and roster order |
| 4. Generate KHKT DOCX | `getCaseInspectionPlanRuntimeReadiness`, `renderCaseInspectionPlan` | Real template and binary, version lineage, Word open/save/storage recovery |
| 5. Draft QĐKT | Readiness and offline test components | BLOCKED until Issue #74 bookmark owners are resolved and guarded typed Case renderer exists |
| 6. Record approved QĐKT + official team | Decision-owned roster schema/service in PR #117–#118 | BLOCKED until independent external approval evidence, authorized API/transaction and frontend confirmation |
| 7. Outcomes, CAPA, documents | `upsertInspectionOutcome`, `createCapaCycle`, document-content paths | Real Case-bound cycle and Word storage validation |
| 8. Filter/report/export | Current `/reports` placeholder | Implement FilterForm-equivalent saved filters, lists and Excel export with source-grounded parity |

## Acceptance protocol

Use an **approved isolated rehearsal**, not production, with authorized test accounts A and B and representative cases for GMP/GLP/GMPbb and relevant legacy exceptions. For each step: record code SHA, deployed SHA, schema revision, actor role, Case/Site identity, preconditions, actual API request/response (redacted), resulting readback, expected vs. actual behavior, and file hash if a document is produced. Prove authorization denial, stale version, duplicate replay, rollback and cross-Case containment. For office flows additionally verify Word desktop display, numbering, table/conditional bookmarks, save and version checksums. Do not alter source workbook or real Synology data.

Completion is allowed **only after** user-visible successful end-to-end operation and operator-accepted evidence. CI green is only a development gate. In particular, do not promote `qdkt_draft`, `qdkt_approved`, `document_storage` or `report_export` on the basis of source code alone.

External blockers remain: Issue #74 (QĐKT bookmark owner contract), Issue #8 (OIDC browser-origin/authenticated rehearsal), Issue #6 (historical GMP certificate link exceptions), Issue #14 (backup freshness and restore drill). Not all blockers must affect every step, but each must be explicitly accounted for before cutover.

## Next implementation slice for Codex (frontend owner)

Extend the **existing SearchPage Case workspace**, not a new duplicate Case screen. Surface QĐKT readiness from the existing protected `GET /cases/{case_id}/documents/inspection-qd-kt/readiness` and current-team provenance endpoint. Show explicit `ready_to_render=false` and blocker details; **no Create QĐKT control while Issue #74 remains**. Preserve Case-selection and in-flight request isolation, 401/403/409 feedback, keyboard focus and the existing KHKT flows. Use real backend contracts, not mock responses. This should be a separate frontend PR with browser tests.

## Next implementation slice for backend owner

Complete the approved-decision handoff boundary and its evidence/permission model before a POST is registered. Review decision→plan→Case ownership, document-version/draft lineage, three roster modes, signed-approval provenance, concurrency, idempotency and audit. Do not infer issuance from draft DOCX, nor mutate an existing append-only roster.
