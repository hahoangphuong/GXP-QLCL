# ĐĐK: persisted version history and per-version GxP FK evidence

Backend PR #7, development rehearsal only. No Alembic/schema or data changes.

## API

`GET /business-eligibility-certificates/{business_eligibility_certificate_id}/versions`

Catalog authenticated read roles (unchanged). Parameter is the canonical
`BusinessEligibilityCertificate.id` UUID. No use of source ID CC as a
certificate UUID, no legacy string matching, no source-to-canonical rescue.

Response schema: `BusinessEligibilityVersionHistoryRead`.

- Aggregate metadata: `business_eligibility_certificate_id`, original
  nullable `legacy_dkkd_id`, `site_id`, `company_id`,
  `aggregate_latest_flag`, `latest_version_id`.
- `latest_selection_method="max_persisted_version_no"` emphasizes that
  **DDK BusinessEligibilityVersion has no is_latest_version column**.
  The maximal saved `version_no` is the same selection contract used by
  the existing current DDK detail, not a guessed historical status.
- `versions[]` contains every stored `BusinessEligibilityVersion`,
  sorted by decreasing `version_no`. Each has its actual
  `business_eligibility_version_id`, `version_no`, concurrency
  `row_version`, all original business fields including unmodified
  `issuance_history_text`, `business_activity_text`, notes and license
  information, plus `stored_link_records[]` for that exact version UUID.
- Every `stored_link_records[]` item holds the persisted FK row
  `link_id`, canonical `certificate_id`, and `link_role`. It does **not**
  assert the linked Certificate was valid on the DDK issue date, covered
  the same site/company or was historically approved. The response
  expressly marks `canonical_link_status="stored_fk_only_not_validated"`.
  It does not automatically cross-join latest CertificateVersion records.
- `gxp_source_tokens_included=false` separates this endpoint from
  `/gxp-source-evidence`: the 861 original physical ID CC token observations
  are **not** canonical Certificate links. Nor does source `issuance_history_text`
  become reconstructed BusinessEligibilityVersion objects.
- Missing aggregate: 404. Existing aggregate without saved versions:
  `versions=[]`, `latest_version_id=null`. No synthetic versions.
  Unauthorized access preserves standard 401/403.

## For Codex frontend

The new history endpoint is read-only and independent of both the current
`/business-eligibility-certificates/{id}` projection and original
`/gxp-source-evidence` view. Keep the three presentation semantics separate:
persisted DDK versions, stored canonical GxP FK link rows, and raw Excel
GMP/GLP/GSP/GDP source cells. No completion indicators based on raw ID CC.

No frontend PR #3 modifications in this backend slice. Deployment requires
an explicit separate rehearsal deploy to `gxp-web-prod`; GitHub HEAD alone
does not prove web runtime availability.
