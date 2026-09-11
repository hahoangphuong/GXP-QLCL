# Inspection Case Lifecycle — Consolidated Migration Plan

## Status

**PLANNED / NOT YET AUTHORIZED FOR PRODUCTION EXECUTION**

This plan follows the canonical owner matrix in `docs/INSPECTION_CASE_LIFECYCLE_OWNER_MATRIX.md` and the user-confirmed inspection lifecycle.

No production migration should be executed until the read-only legacy profiler has been run against the authoritative workbook and the resulting morphology/null-rate artifact has been reviewed.

## Preconditions

1. Run:

```powershell
py tools/audit_inspection_case_lifecycle_legacy.py <AUTHORITATIVE_WORKBOOK_PATH>
```

2. Review:

```text
artifacts/legacy_audit/inspection_case_lifecycle_legacy_profile.json
```

3. Confirm all of the following:

- workbook SHA256 is recorded;
- `db.ktra` and `db.cc` row counts are plausible;
- no raw business values are persisted in the audit artifact;
- QĐKT composite morphology distribution is understood;
- values without an unambiguous trailing date are classified fail-closed;
- candidate headers for report date, CAPA incoming reference, final evaluation, compliance deadline and approval routing have been manually reconciled to real business columns;
- null rates and legacy value shapes are understood before choosing backfill policy.

## Migration structure

Use one coherent schema migration after evidence review rather than serial one-field migrations.

### A. `inspection_plan`

Add nullable columns:

```text
decision_reference          VARCHAR(255)
decision_date               DATE
decision_raw_legacy_text    TEXT
```

Semantics:

- `decision_reference` = canonical QĐKT number/reference;
- `decision_date` = canonical QĐKT date;
- `decision_raw_legacy_text` = immutable compatibility/audit capture only, not semantic truth.

Keep `decision_document_hint` during transition. Do not silently rename it into canonical truth.

### B. `inspection_outcome`

Add nullable columns:

```text
report_written_on           DATE
final_evaluation            TEXT
compliance_due_on           DATE
```

Semantics:

- `outcome_result` remains the ordinary post-inspection assessment/result;
- `final_evaluation` is the later final disposition after CAPA processing;
- `compliance_due_on` is the structured compliance/re-inspection deadline;
- `report_written_on` is the report creation/written date confirmed by the business owner.

### C. `capa_cycle`

Add nullable column:

```text
incoming_reference          VARCHAR(255)
```

Do not add round-1/round-2 specific columns. Existing `round_no` remains the repeatable owner.

### D. New `inspection_approval_submission`

Create a repeatable routing table:

```text
id                          UUID PK
created_at                  timestamptz NOT NULL
updated_at                  timestamptz NOT NULL
case_id                     UUID NOT NULL FK case(id)
stage                       VARCHAR(32) NOT NULL
sequence_no                 INTEGER NOT NULL DEFAULT 1
reference_number            VARCHAR(255)
submitted_on                DATE
notes                       TEXT
```

Recommended uniqueness:

```text
UNIQUE(case_id, stage, sequence_no)
```

Why sequence-based rather than `UNIQUE(case_id, stage)`:

- the confirmed workflow currently has PCT then CT;
- future correction/resubmission must not force destructive overwrite if multiple submissions for one stage become valid;
- a single current record can still use `sequence_no=1`.

Initial controlled stage codes:

```text
VICE_CHAIR
CHAIR
```

Do not create fixed `pct_*` and `ct_*` columns on `case`.

## DDL vs backfill separation

The DDL migration must **not** parse legacy strings or mutate existing compatibility projections.

Recommended phases:

```text
1. DDL migration
   -> nullable fields/table only

2. Read-only backfill plan
   -> classify every source row
   -> no writes

3. Backfill execution
   -> only unambiguous rows
   -> explicit anomaly output for ambiguous rows

4. Backfill verification
   -> source counts
   -> parsed counts
   -> rejected counts/reasons
   -> exact raw-source fingerprint

5. Runtime owner cutover
   -> new UI/API writes canonical fields
   -> document payload reads canonical fields

6. Compatibility cleanup later
   -> only after proven no downstream consumer depends on old projections
```

## QĐKT parsing contract

The business owner confirmed the legacy UI value is a user-authored composite containing decision reference + decision date.

The current source trace shows VBA splitting that cell into `QDKT` and `NgayQDKT`.

Backfill may parse only when the grammar is unambiguous after profiler review. Initial conservative candidate grammar:

```text
<non-empty decision reference> + trailing date
```

with trailing date morphology such as:

```text
d/M/yyyy
dd/MM/yyyy
d-M-yyyy
dd-MM-yyyy
```

The profiler deliberately classifies rather than backfills:

```text
reference_plus_trailing_date
date_only
no_trailing_date
empty
```

Only `reference_plus_trailing_date` is an automatic-backfill candidate unless additional source evidence proves more grammars.

Fail closed on:

- date-only values;
- missing date;
- ambiguous multiple dates;
- malformed date;
- empty reference;
- any row where source/header ownership is not proven.

Do not derive QĐKT date from inspection date, report date, certificate date or workstation date.

## Existing compatibility projections

Current importer behavior may copy legacy `Q. định` into fields such as:

```text
CaseApplication.dossier_reference
InspectionOutcome.decision_reference
```

These values are compatibility projections, not canonical ownership evidence.

During initial schema migration:

- do not delete them;
- do not rewrite them;
- do not make new document logic depend on them when canonical planning fields are available.

After backfill and consumer audit, compatibility cleanup can be planned separately.

## Backfill anomaly contract

Every non-auto-backfilled row must remain represented explicitly.

Suggested reasons:

```text
QD_KT_EMPTY
QD_KT_DATE_ONLY
QD_KT_NO_TRAILING_DATE
QD_KT_MULTIPLE_DATE_CANDIDATES
QD_KT_INVALID_DATE
QD_KT_EMPTY_REFERENCE
HEADER_OWNER_UNRESOLVED
CAPA_REFERENCE_OWNER_UNRESOLVED
FINAL_EVALUATION_OWNER_UNRESOLVED
COMPLIANCE_DUE_OWNER_UNRESOLVED
APPROVAL_ROUTING_OWNER_UNRESOLVED
```

Do not silently coerce an anomaly into a value.

## UI/API cutover direction

The new UI should collect structured values directly:

### Application

```text
dossier_code
submitted_on
```

### Initial assessment

```text
assessed_on
assessment_result
assessor
```

### Inspection decision

```text
decision_reference
decision_date
```

### Inspection execution/result

```text
inspected_on
report_written_on
team members
applicable_standard
outcome_result
```

### CAPA cycle

```text
round_no
incoming_reference
submitted_on
assessed_on
assessor
result
```

### Final disposition

```text
final_evaluation
compliance_due_on
```

### Approval routing

```text
stage
sequence_no
reference_number
submitted_on
```

### Certificate

```text
certificate_number
issue_date
expiry_date
```

Word/VBA bookmark names must not become API field names.

## Acceptance gates before enabling typed QĐKT document creation

Schema availability alone is insufficient.

Required gates:

1. business owner matrix accepted;
2. legacy profile reviewed;
3. DDL migration tested upgrade + downgrade on disposable database;
4. backfill differential reviewed;
5. QĐKT structured owner populated or explicitly missing;
6. template logical-field mapping reconciled;
7. team ordering/render semantics reconciled;
8. facility/location display projections reconciled;
9. document payload validation fail-closed for required missing values;
10. no consumer reads old compatibility projections as canonical QĐKT truth.

Until those gates pass, `INSPECTION_QD_KT` remains `BUSINESS_INPUT_CONTRACT_MISSING` / not ready for production document generation.
