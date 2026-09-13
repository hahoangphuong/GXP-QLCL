# db.ktra Read-Only Reconciliation Plan

## Scope

This batch reads the committed `artifacts/phase3c/legacy_snapshot.json` only.
It neither invokes the production importer nor changes a database. The parser
profile is evidence for a separately approved rehearsal apply batch.

## Provenance

- Snapshot byte identity: `b3bde05963e4e4d14d5b244e7c62b0f810f1cbbe206750574def6a366bdf7296`
- Extraction input: canonical `db.ktra` snapshot, 1,533 valid legacy IDs.
- Artifacts retain hashes, shapes, and parsed structure rather than raw prose.

## Parser Evidence

| Source | Result |
| --- | --- |
| `Q. định` | 1,220 `KNOWN`, 12 `PARTIAL`, 67 `UNRESOLVED`, 234 `MISSING`. Only one reference plus one `dd/mm/yyyy` date is a future split candidate. |
| `B. bản` | 1,150 `KNOWN`, 3 `RAW_ONLY`, 6 `UNRESOLVED`, 374 `MISSING`. The proven `YYYY-MM-DD HH:MM:SS+HH:MM` morphology preserves its source calendar date and local clock time without offset conversion. It is minutes-record metadata only, never an inspection period input. |
| `ĐÁNH GIÁ CUỐI` | 1,294 non-sentinel values and 239 missing values; it remains distinct from the initial outcome. |
| `HẠN KT TUÂN THỦ` | 405 `KNOWN`, 3 `PARTIAL`, and 1,125 missing. Proven ISO timestamps contribute their source calendar date only; no workflow behavior is inferred from clock time or offset. |
| `T.tra viên` | 1,293 parseable ordered display lists and 240 missing values. The full profile proves 1,290 comma-only lists and 3 single-name values; no newline, semicolon, slash, or mixed delimiter appears. Ordinals map to `LEADER`, `SECRETARY`, then `MEMBER`; identity resolution remains exact-only. |
| PCT / CT | PCT: 370 `KNOWN`, 13 `UNRESOLVED`, 1,150 missing. CT: 315 `KNOWN`, 15 `UNRESOLVED`, 1,203 missing. Neither parser fabricates completion, rounds, or CT parentage. |
| `ID CC GPs` | 1,326 exact integer candidates and 207 missing values. Future linking additionally requires unique certificate and case/site/type compatibility. |

## Future Comparison

`python -m tools.plan_db_ktra_reconciliation --compare-rehearsal --database-url-env DATABASE_URL`
is intentionally PostgreSQL-only and accepts only `gxp_legacy_rehearsal` at
Alembic revision `20260912_0012`. It executes `SET TRANSACTION READ ONLY`,
verifies `transaction_read_only`, then rolls back and closes. The current local
run did not receive `DATABASE_URL`, so its plan/contamination artifacts record
`NOT_RUN_DATABASE_URL_ABSENT`; no contamination count is claimed.

## Owner Guardrails

- `Kết quả` may be compared with `InspectionOutcome.outcome_result`; equality
  with `CaseAssessment.assessment_result` is evidence of old-owner
  contamination, not authorization to clear it.
- `Q. định` targets only split `InspectionPlan` fields; legacy application and
  outcome compatibility fields remain report-only.
- `B. bản` targets only minutes date/time/raw provenance and never
  `inspected_on`, `inspected_to_on`, or period segments.
- No Person, InspectorProfile, certificate, approval parent, or CAPA completion
  is synthesized from source text.
- The read-only comparison emits fact-level evidence for results, decisions,
  minutes, final evaluation, compliance due date, ordered team members, PCT/CT,
  and certificate linkage. It separately quantifies all four historical
  wrong-owner paths; no report authorizes cleanup.
