# GxP CertificateVersion history and historical scope read contract (2026-10-13)

Owner: `backend/app/api/routers/catalog.py` and
`backend/app/services/catalog.py`.

## Read-only endpoint

`GET /certificates/{certificate_id}/versions`

The path requires a canonical aggregate `Certificate.id` UUID. It is not a
legacy certificate integer or a version UUID. Access uses the existing
catalog `ALLOWED_READ_ROLES`, the same authenticated user dependency and
linked-Case / ProductionLine integrity validation as `GET /certificates/{certificate_id}`.

Response: `GxpCertificateVersionHistoryRead`:

- `certificate_id`, `site_id`, `case_id`, `certificate_type`,
  `issuance_basis` and `aggregate_latest_flag` describe the Certificate
  aggregate. `aggregate_latest_flag` **is not** a version marker.
- `latest_version_id` refers only to a stored
  `CertificateVersion.is_latest_version=true` UUID (or null if none).
- `versions[]` is sorted by `version_no` descending. Each item has
  `certificate_version_id`, `version_no`, `row_version`,
  `is_latest_version`, nullable `lifecycle_state`, certificate number,
  issue/expiry dates, applicable standard, issuing authority,
  `scope_summary`, and the complete ordered `scopes[]` owned by **that
  exact version UUID**.
- `scopes[]` uses the existing `CertificateScopeDetailRead` fields:
  `id`, `scope_key`, `scope_text`, `language_code`, `sort_order`.
  Text and scope UUIDs are returned unchanged. Sorting: `sort_order`,
  `created_at`, scope UUID. No current-to-historical fallback.
- `row_version` inside each version is its concurrency value, **not**
  a version identity or version ordinal.
- Nullable `lifecycle_state` must remain nullable: historical imported
  rows may not prove grant state. Do not deduce a status from date or scope.

Error behavior: HTTP 401/403 uses unchanged catalog auth, 404 for missing
canonical Certificate, 409 for malformed canonical Case linkage or more than
one latest CertificateVersion. Zero stored versions -> empty `versions[]`
and null `latest_version_id`, not a fabricated version. The existing
`GET /certificates/{certificate_id}` endpoint continues independently to
return the current-version projection and original readiness contract.

The history API uses only SELECT queries and cannot promote certificates,
alter evidence, create canonical links, or mutate source provenance.

**Important interpretation**: this is an ordered readout of persistent
version records, not a legal attestation that every record is immutable.
Frontend must not infer a historic `CertificateVersion` from legacy
issuance text, `row_version` or `latest_flag`. It must use this endpoint
and exact `certificate_version_id`.

## Frontend integration handoff

Codex PR #3 can add read-only history display using this new API after the
backend SHA is deployed on the development VM. It must keep the existing
current-certificate detail and facility selection semantics unchanged.
OAuth authorization of `http://127.0.0.1:4173` is a separate deployment
configuration issue; never bypass it with hardcoded header identities.

The original DDK `gxp-source-evidence` endpoint is **not** CertificateVersion
history. The original 861 physical source ID CC token observations do not
confer a canonical Certificate UUID nor an approved Certificate link.
