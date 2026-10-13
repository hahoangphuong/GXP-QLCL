# DDK original four-group GxP source evidence read API (development, 2026-10-13)

Owner: `backend/app/services/catalog.py` and `backend/app/api/routers/catalog.py`.
Backend PR #7. The actual VM rehearsal DB `gxp_legacy_rehearsal` has
3,120 original GxP source groups and 861 reference tokens, loaded after
Alembic `20261012_0023` and verified by independent count queries.
This is development/test; no merge into go-live `gxp_qlcl`.

## Endpoint

`GET /business-eligibility-certificates/{business_eligibility_certificate_id}/gxp-source-evidence`

- Requires exactly the same authenticated read roles as the existing
  `GET /business-eligibility-certificates/{id}` catalog endpoint.
- The path parameter is the **canonical BusinessEligibilityCertificate UUID**.
  The server obtains its stored `legacy_dkkd_id`, then selects the complete
  original Excel `db.dkkd` physical source row. It never selects by
  certificate number, GxP Certificate legacy ID, Site/Company address, or
  the `linked_gxp_certificates` list.
- Response `BusinessEligibilityGxpSourceEvidenceRead` includes
  `source_status` (available / legacy_identity_missing /
  not_in_imported_source), source workbook fingerprint, physical sheet/row,
  `canonical_links_included=false`, and exactly four source groups when
  available. Each group includes its own source UUID, physical column anchors
  and **all four verbatim original cells**; each token contains source-token
  UUID, 1-based ordinal, literal raw value and parsed source legacy integer.
  Those UUIDs are evidence-row identities, never canonical GxP Certificates.
- Token order is preserved. Distinct DDK rows, workbook snapshots, and GxP
  roles are not merged; empty source ID CC does not eliminate companion
  scope, standard or business-activity values.
- If a canonical DDK has no source legacy identity or was not included in
  the accepted import, the response has an explicit status and empty
  `groups`. Multiple matching original physical rows or incomplete four-group
  source evidence return HTTP 409, not a best-effort or inferred view.
- Missing canonical DDK UUID -> HTTP 404. Authentication/authorization uses
  unchanged 401/403 behavior. This endpoint performs SELECTs only.

## Scope and frontend implications

This data is **source provenance only**: `parsed_legacy_certificate_id`
does *not* establish a canonical Certificate UUID, approval, grant, valid
certificate, DDK historical version or same-Site coverage. The original
workbook contains known anomalous cross-Site/Company references that remain
unresolved. Do not merge these tokens with existing
`BusinessEligibilityDetailRead.linked_gxp_certificates`; that field keeps its
existing canonical meaning and response contract unchanged.

The current record describes original workbook source rows, **not**
CertificateVersion history and not business-eligibility version chronology.
Do not show green completion indicators based on source cell presence.

No frontend PR #3 files or migrations are changed in this slice. The
API code must be deployed separately to the VM before Codex can mark
REAL_BACKEND_VERIFIED for this endpoint. Importing the 3,981 evidence rows
was not a web-service redeploy.
