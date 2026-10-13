-- Independent, VM-local postflight for ONLY DDK GxP provenance migration 0023.
-- READ ONLY. Does not load 3,981 evidence rows or approve Certificate links.
-- Usage (after separate, authorized schema-only apply):
-- sudo -u postgres psql -X -v ON_ERROR_STOP=1 \
--   -h /var/run/postgresql -U postgres -d gxp_legacy_rehearsal \
--   -f scripts/verify_ddk_gxp_0023_postflight_readonly.sql
\set ON_ERROR_STOP on

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';

DO $ddk_0023_postflight$
DECLARE
  actual_revision text;
  revision_count integer;
  group_oid oid;
  ref_oid oid;
  relname text;
  att_count integer;
  att_expected integer;
  check_count integer;
  unique_count integer;
  primary_count integer;
  fk_count integer;
  matched_columns integer;
  group_rows bigint;
  reference_rows bigint;
BEGIN
  IF current_database() <> 'gxp_legacy_rehearsal'
     OR current_setting('transaction_read_only') <> 'on'
     OR current_setting('transaction_isolation') <> 'repeatable read' THEN
    RAISE EXCEPTION 'DDK 0023 postflight requires rehearsal READ ONLY REPEATABLE READ';
  END IF;

  IF to_regclass('public.alembic_version') IS NULL THEN
    RAISE EXCEPTION 'Missing Alembic revision table';
  END IF;
  SELECT count(*), min(version_num) INTO revision_count, actual_revision
  FROM public.alembic_version;
  IF revision_count <> 1 OR actual_revision <> '20261012_0023' THEN
    RAISE EXCEPTION 'Expected exactly Alembic revision 0023, found % / rows %',
      actual_revision, revision_count;
  END IF;

  SELECT oid INTO group_oid
  FROM pg_catalog.pg_class
  WHERE oid = to_regclass('public.business_eligibility_gxp_source_group')
    AND relkind = 'r';
  SELECT oid INTO ref_oid
  FROM pg_catalog.pg_class
  WHERE oid = to_regclass('public.business_eligibility_gxp_reference_evidence')
    AND relkind = 'r';
  IF group_oid IS NULL OR ref_oid IS NULL THEN
    RAISE EXCEPTION 'One or both 0023 provenance base tables are missing';
  END IF;

  -- The source group is exact 17-column / reference exact 7-column additive
  -- schema; an unforeseen extra/missing column must not be accepted silently.
  FOR relname, att_expected IN
    SELECT 'business_eligibility_gxp_source_group', 17
    UNION ALL
    SELECT 'business_eligibility_gxp_reference_evidence', 7
  LOOP
    SELECT count(*) INTO att_count
    FROM pg_catalog.pg_attribute
    WHERE attrelid = CASE
                       WHEN relname = 'business_eligibility_gxp_source_group'
                       THEN group_oid ELSE ref_oid
                     END
      AND attnum > 0 AND NOT attisdropped;
    IF att_count <> att_expected THEN
      RAISE EXCEPTION 'Unexpected source provenance column count for %: %',
        relname, att_count;
    END IF;
  END LOOP;

  -- Exact PostgreSQL owner column types, including length and timestamps.
  SELECT count(*) INTO matched_columns
  FROM (VALUES
    ('id', 'uuid'),
    ('created_at', 'timestamp with time zone'),
    ('updated_at', 'timestamp with time zone'),
    ('source_workbook_sha256', 'character varying(64)'),
    ('source_sheet_name', 'character varying(32)'),
    ('source_row_number', 'integer'),
    ('legacy_dkkd_id', 'integer'),
    ('source_group', 'character varying(3)'),
    ('id_cc_excel_column', 'integer'),
    ('certificate_scope_excel_column', 'integer'),
    ('applicable_standard_excel_column', 'integer'),
    ('business_activity_excel_column', 'integer'),
    ('id_cc_raw', 'text'),
    ('certificate_scope_raw', 'text'),
    ('applicable_standard_raw', 'text'),
    ('business_activity_raw', 'text'),
    ('source_values_sha256', 'character varying(64)')
  ) AS expected(name, data_type)
  JOIN pg_catalog.pg_attribute AS actual
    ON actual.attrelid = group_oid AND actual.attname = expected.name
      AND pg_catalog.format_type(actual.atttypid, actual.atttypmod)
        = expected.data_type;
  IF matched_columns <> 17 THEN
    RAISE EXCEPTION 'GxP source-group column types do not match 0023';
  END IF;

  SELECT count(*) INTO matched_columns
  FROM (VALUES
    ('id', 'uuid'),
    ('created_at', 'timestamp with time zone'),
    ('updated_at', 'timestamp with time zone'),
    ('source_group_id', 'uuid'),
    ('token_index', 'integer'),
    ('raw_token', 'text'),
    ('parsed_legacy_certificate_id', 'integer')
  ) AS expected(name, data_type)
  JOIN pg_catalog.pg_attribute AS actual
    ON actual.attrelid = ref_oid AND actual.attname = expected.name
      AND pg_catalog.format_type(actual.atttypid, actual.atttypmod)
        = expected.data_type;
  IF matched_columns <> 7 THEN
    RAISE EXCEPTION 'GxP reference-token column types do not match 0023';
  END IF;

  -- Every owner-required physical source value and identity field is NOT NULL.
  SELECT count(*) INTO matched_columns
  FROM pg_catalog.pg_attribute
  WHERE attrelid = group_oid AND attnotnull AND NOT attisdropped
    AND attname = ANY (ARRAY[
      'id', 'created_at', 'updated_at', 'source_workbook_sha256',
      'source_sheet_name', 'source_row_number', 'source_group',
      'id_cc_excel_column', 'certificate_scope_excel_column',
      'applicable_standard_excel_column', 'business_activity_excel_column',
      'id_cc_raw', 'certificate_scope_raw', 'applicable_standard_raw',
      'business_activity_raw', 'source_values_sha256'
    ]);
  IF matched_columns <> 16 THEN
    RAISE EXCEPTION 'GxP physical source columns are nullable/missing';
  END IF;

  SELECT count(*) INTO matched_columns
  FROM pg_catalog.pg_attribute
  WHERE attrelid = ref_oid AND attnotnull AND NOT attisdropped
    AND attname = ANY (ARRAY[
      'id', 'created_at', 'updated_at', 'source_group_id',
      'token_index', 'raw_token'
    ]);
  IF matched_columns <> 6 THEN
    RAISE EXCEPTION 'GxP token evidence columns are nullable/missing';
  END IF;

  SELECT count(*) FILTER (WHERE contype = 'p'),
         count(*) FILTER (WHERE contype = 'u'),
         count(*) FILTER (WHERE contype = 'c'),
         count(*) FILTER (WHERE contype = 'f')
    INTO primary_count, unique_count, check_count, fk_count
  FROM pg_catalog.pg_constraint WHERE conrelid = group_oid;
  IF primary_count <> 1 OR unique_count <> 1 OR check_count <> 5
     OR fk_count <> 0 THEN
    RAISE EXCEPTION 'Unexpected source-group PK/unique/check/FK contract';
  END IF;

  -- Validate natural-key index identity, not just constraint existence.
  SELECT count(*) INTO matched_columns
  FROM pg_catalog.pg_constraint AS c
  WHERE c.conrelid = group_oid AND c.contype = 'u'
    AND ARRAY(
      SELECT att.attname::text
      FROM unnest(c.conkey) WITH ORDINALITY AS fields(attnum, ordinal)
      JOIN pg_catalog.pg_attribute AS att
        ON att.attrelid = c.conrelid AND att.attnum = fields.attnum
      ORDER BY fields.ordinal
    ) = ARRAY[
      'source_workbook_sha256', 'source_sheet_name',
      'source_row_number', 'source_group'
    ]::text[];
  IF matched_columns <> 1 THEN
    RAISE EXCEPTION 'GxP group uniqueness is not workbook/row/role owned';
  END IF;

  SELECT count(*) FILTER (WHERE contype = 'p'),
         count(*) FILTER (WHERE contype = 'u'),
         count(*) FILTER (WHERE contype = 'c'),
         count(*) FILTER (WHERE contype = 'f')
    INTO primary_count, unique_count, check_count, fk_count
  FROM pg_catalog.pg_constraint WHERE conrelid = ref_oid;
  IF primary_count <> 1 OR unique_count <> 1 OR check_count <> 2
     OR fk_count <> 1 THEN
    RAISE EXCEPTION 'Unexpected source-token PK/unique/check/FK contract';
  END IF;

  SELECT count(*) INTO matched_columns
  FROM pg_catalog.pg_constraint AS c
  WHERE c.conrelid = ref_oid AND c.contype = 'u'
    AND ARRAY(
      SELECT att.attname::text
      FROM unnest(c.conkey) WITH ORDINALITY AS fields(attnum, ordinal)
      JOIN pg_catalog.pg_attribute AS att
        ON att.attrelid = c.conrelid AND att.attnum = fields.attnum
      ORDER BY fields.ordinal
    ) = ARRAY['source_group_id', 'token_index']::text[];
  IF matched_columns <> 1 THEN
    RAISE EXCEPTION 'GxP reference uniqueness is not source-group/token owned';
  END IF;
  SELECT count(*) INTO matched_columns
  FROM pg_catalog.pg_constraint AS c
  JOIN pg_catalog.pg_attribute AS att
    ON att.attrelid = ref_oid AND att.attnum = c.conkey[1]
  WHERE c.conrelid = ref_oid AND c.contype = 'f'
    AND c.confrelid = group_oid AND att.attname = 'source_group_id'
    AND cardinality(c.conkey) = 1;
  IF matched_columns <> 1 THEN
    RAISE EXCEPTION 'GxP reference FK is not source group only';
  END IF;

  IF NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_indexes
      WHERE schemaname = 'public'
        AND tablename = 'business_eligibility_gxp_source_group'
        AND indexname = 'ix_begxp_group_source_workbook'
     ) OR NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_indexes
      WHERE schemaname = 'public'
        AND tablename = 'business_eligibility_gxp_reference_evidence'
        AND indexname =
          'ix_business_eligibility_gxp_reference_evidence_source_group_id'
     ) THEN
    RAISE EXCEPTION 'GxP provenance owner indexes missing';
  END IF;

  SELECT count(*) INTO group_rows
  FROM public.business_eligibility_gxp_source_group;
  SELECT count(*) INTO reference_rows
  FROM public.business_eligibility_gxp_reference_evidence;
  IF group_rows <> 0 OR reference_rows <> 0 THEN
    RAISE EXCEPTION 'Source-only tables must remain empty at schema-only checkpoint';
  END IF;
END;
$ddk_0023_postflight$;

SELECT 'PASS_SCHEMA_0023_SOURCE_ONLY_EMPTY' AS postflight_status,
       current_database() AS database_name,
       (SELECT version_num FROM public.alembic_version) AS alembic_revision,
       (SELECT count(*) FROM public.business_eligibility_gxp_source_group)
         AS source_group_rows,
       (SELECT count(*) FROM public.business_eligibility_gxp_reference_evidence)
         AS reference_token_rows,
       current_setting('transaction_read_only') AS read_only;

ROLLBACK;
