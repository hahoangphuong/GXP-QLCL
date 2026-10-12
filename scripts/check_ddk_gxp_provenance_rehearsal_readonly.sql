-- DDK GxP physical-group provenance: VM-local schema/count diagnostics.
-- No new migration, no DML/DDL, no read of source business text.
-- Command (with the PR #7 script present on VM):
-- sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d gxp_legacy_rehearsal \
--   -f scripts/check_ddk_gxp_provenance_rehearsal_readonly.sql
--
-- This is the first, *plan-independent* read-only check. It is NOT the
-- full-source-payload comparison done by tools/preflight_ddk_gxp_rehearsal.py.
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

DO $gxp_preflight_guard$
BEGIN
    IF current_database() <> 'gxp_legacy_rehearsal' THEN
        RAISE EXCEPTION 'Refusing non-rehearsal database: %', current_database();
    END IF;
    IF current_setting('transaction_read_only') <> 'on'
       OR current_setting('transaction_isolation') <> 'repeatable read' THEN
        RAISE EXCEPTION 'Read-only REPEATABLE READ transaction required';
    END IF;
END;
$gxp_preflight_guard$;

\echo '=== DDK GxP PROVENANCE: DB/ISOLATION ==='
SELECT current_database() AS database_name,
       current_setting('transaction_read_only') AS transaction_read_only,
       current_setting('transaction_isolation') AS transaction_isolation;

\echo '=== ALEMBIC REVISION (NO TABLE ASSUMPTION) ==='
SELECT CASE WHEN to_regclass('public.alembic_version') IS NOT NULL
            THEN '1' ELSE '0' END AS gxp_has_alembic \gset
\if :gxp_has_alembic
SELECT version_num FROM public.alembic_version ORDER BY version_num;
\else
\echo 'MISSING: public.alembic_version'
\endif

\echo '=== PHYSICAL PROVENANCE TABLE PRESENCE ==='
SELECT target.table_name,
       COALESCE(c.relkind::text, 'ABSENT') AS relation_kind,
       CASE WHEN c.relkind IN ('r','p') THEN 'YES' ELSE 'NO' END AS base_table_present
FROM (VALUES
  ('business_eligibility_gxp_source_group'::text),
  ('business_eligibility_gxp_reference_evidence'::text)
) AS target(table_name)
LEFT JOIN pg_catalog.pg_namespace AS n ON n.nspname = 'public'
LEFT JOIN pg_catalog.pg_class AS c
  ON c.relnamespace = n.oid AND c.relname = target.table_name
ORDER BY target.table_name;

\echo '=== STRUCTURE: COLUMN NAMES/TYPES/NULLABILITY ==='
SELECT c.relname AS table_name,
       a.attnum AS position,
       a.attname AS column_name,
       pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
       a.attnotnull AS not_null
FROM pg_catalog.pg_namespace n
JOIN pg_catalog.pg_class c ON c.relnamespace = n.oid
JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = 'public'
  AND c.relname IN (
    'business_eligibility_gxp_source_group',
    'business_eligibility_gxp_reference_evidence'
  )
  AND c.relkind IN ('r','p')
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum;

\echo '=== STRUCTURE: PRIMARY/UNIQUE/CHECK/FOREIGN KEY CONSTRAINTS ==='
SELECT c.relname AS table_name,
       k.conname AS constraint_name,
       k.contype AS constraint_type,
       pg_catalog.pg_get_constraintdef(k.oid, true) AS constraint_definition
FROM pg_catalog.pg_constraint k
JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN (
    'business_eligibility_gxp_source_group',
    'business_eligibility_gxp_reference_evidence'
  )
ORDER BY c.relname, k.contype, k.conname;

\echo '=== STRUCTURE: INDEX DEFINITIONS ==='
SELECT tablename, indexname, indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
    'business_eligibility_gxp_source_group',
    'business_eligibility_gxp_reference_evidence'
  )
ORDER BY tablename, indexname;

\echo '=== COUNT CHECK: ONLY IF PHYSICAL TABLE EXISTS ==='
SELECT CASE WHEN to_regclass('public.business_eligibility_gxp_source_group') IS NOT NULL
  AND EXISTS (
     SELECT 1 FROM pg_catalog.pg_class
     WHERE oid = to_regclass('public.business_eligibility_gxp_source_group')
       AND relkind IN ('r','p')
  ) THEN '1' ELSE '0' END AS gxp_has_group \gset
SELECT CASE WHEN to_regclass('public.business_eligibility_gxp_reference_evidence') IS NOT NULL
  AND EXISTS (
     SELECT 1 FROM pg_catalog.pg_class
     WHERE oid = to_regclass('public.business_eligibility_gxp_reference_evidence')
       AND relkind IN ('r','p')
  ) THEN '1' ELSE '0' END AS gxp_has_token \gset

\if :gxp_has_group
SELECT 'business_eligibility_gxp_source_group' AS table_name,
       count(*) AS existing_rows
FROM public.business_eligibility_gxp_source_group;
\else
\echo 'NOT INSTALLED: business_eligibility_gxp_source_group; count unavailable'
\endif

\if :gxp_has_token
SELECT 'business_eligibility_gxp_reference_evidence' AS table_name,
       count(*) AS existing_rows
FROM public.business_eligibility_gxp_reference_evidence;
\else
\echo 'NOT INSTALLED: business_eligibility_gxp_reference_evidence; count unavailable'
\endif

\echo '=== READ-ONLY PREFLIGHT COMPLETE: NO MIGRATION OR DATA CHANGES ==='
ROLLBACK;
