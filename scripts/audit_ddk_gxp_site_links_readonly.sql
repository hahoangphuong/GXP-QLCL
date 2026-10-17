-- Read-only, rehearsal-only integrity check for GxP ↔ ĐĐK version links.
-- Run on gxp-web-prod with: sudo -u postgres psql -X -v ON_ERROR_STOP=1
--   -d gxp_legacy_rehearsal -f scripts/audit_ddk_gxp_site_links_readonly.sql
-- No DDL/DML, updates, schema creation, or transaction writes are permitted.
BEGIN READ ONLY;

DO $$
BEGIN
    IF current_database() <> 'gxp_legacy_rehearsal' THEN
        RAISE EXCEPTION 'Read-only DDK audit requires gxp_legacy_rehearsal, got %',
            current_database();
    END IF;
END $$;

\echo '=== DDK-GxP LINKS: ALL BUSINESS ELIGIBILITY VERSIONS ==='
WITH linked AS (
    SELECT
        d.id AS ddk_id,
        d.legacy_dkkd_id,
        d.site_id AS ddk_site_id,
        d.company_id AS ddk_company_id,
        s.company_id AS owner_site_company_id,
        v.id AS ddk_version_id,
        v.version_no,
        g.id AS gxp_certificate_id,
        g.site_id AS gxp_site_id,
        c.site_id AS gxp_case_site_id,
        max(v.version_no) OVER (PARTITION BY d.id) AS max_linked_version_no
    FROM business_eligibility_certificate_link l
    JOIN business_eligibility_version v ON v.id = l.business_eligibility_version_id
    JOIN business_eligibility_certificate d ON d.id = v.business_eligibility_certificate_id
    JOIN certificate g ON g.id = l.certificate_id
    LEFT JOIN site s ON s.id = d.site_id
    LEFT JOIN "case" c ON c.id = g.case_id
)
SELECT
    COUNT(*) AS total_version_links,
    COUNT(*) FILTER (WHERE ddk_site_id <> gxp_site_id) AS cross_site_ddk_gxp,
    COUNT(*) FILTER (WHERE ddk_company_id IS DISTINCT FROM owner_site_company_id) AS ddk_company_mismatch,
    COUNT(*) FILTER (
        WHERE gxp_case_site_id IS NOT NULL AND gxp_case_site_id <> gxp_site_id
    ) AS gxp_case_site_mismatch,
    COUNT(DISTINCT ddk_id) FILTER (WHERE ddk_site_id <> gxp_site_id) AS affected_ddk_records
FROM linked;

\echo '=== DDK-GxP: CROSS-SITE OR COMPANY-MISMATCH IDENTITIES FOR OWNER REVIEW ==='
SELECT
    d.legacy_dkkd_id,
    d.id AS ddk_id,
    v.id AS ddk_version_id,
    v.version_no,
    d.site_id AS ddk_site_id,
    d.company_id AS ddk_company_id,
    s.company_id AS ddk_site_company_id,
    g.id AS gxp_certificate_id,
    g.legacy_certificate_id,
    g.site_id AS gxp_site_id,
    g.case_id AS gxp_case_id,
    c.site_id AS gxp_case_site_id
FROM business_eligibility_certificate_link l
JOIN business_eligibility_version v ON v.id = l.business_eligibility_version_id
JOIN business_eligibility_certificate d ON d.id = v.business_eligibility_certificate_id
JOIN certificate g ON g.id = l.certificate_id
LEFT JOIN site s ON s.id = d.site_id
LEFT JOIN "case" c ON c.id = g.case_id
WHERE d.site_id <> g.site_id
   OR d.company_id IS DISTINCT FROM s.company_id
ORDER BY d.legacy_dkkd_id NULLS LAST, v.version_no, g.legacy_certificate_id NULLS LAST;

ROLLBACK;
