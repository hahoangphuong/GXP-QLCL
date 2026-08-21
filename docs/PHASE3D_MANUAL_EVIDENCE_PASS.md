# Phase 3d - Manual Evidence Remediation Pass

## Goal
Separate the remaining non-placeholder anomalies into:

- high-confidence overrides that can be replayed deterministically
- a prioritized manual review queue that still needs human confirmation or external evidence

## Historical note
This phase documents how the team investigated the anomaly queue before the business-owner clarification on August 14, 2026.

For the rows now covered by [PHASE3Q_CONFIRMED_BLANKED_ROWS.md](/D:/GXP-QLCL/docs/PHASE3Q_CONFIRMED_BLANKED_ROWS.md):
- they should no longer be interpreted as active manual-review backlog;
- this document should be read as historical investigation context only.

## Inputs
- [artifacts/phase2/reconciliation.json](/D:/GXP-QLCL/artifacts/phase2/reconciliation.json)
- [artifacts/phase3c/legacy_snapshot.json](/D:/GXP-QLCL/artifacts/phase3c/legacy_snapshot.json)
- [artifacts/phase3/case.json](/D:/GXP-QLCL/artifacts/phase3/case.json)
- [artifacts/phase3/site.json](/D:/GXP-QLCL/artifacts/phase3/site.json)

## Tools
- [tools/phase3d_manual_evidence.py](/D:/GXP-QLCL/tools/phase3d_manual_evidence.py)
- [tools/analyze_phase3d_manual_evidence.py](/D:/GXP-QLCL/tools/analyze_phase3d_manual_evidence.py)
- [tools/run_phase3d_high_confidence_reimport.py](/D:/GXP-QLCL/tools/run_phase3d_high_confidence_reimport.py)

## Findings
On August 13, 2026:

- Baseline anomalies: `294`
- High-confidence suggestions: `5`
- Manual review queue items: `143`

The five high-confidence suggestions are all `db.cc` rows where:
- the legacy certificate row still has meaningful payload
- the imported site is known
- `site + gxp + scope` collapses to exactly one candidate case

Suggested certificate -> case mappings:
- `db.cc ID=548` -> `case_legacy_id=575`
- `db.cc ID=1330` -> `case_legacy_id=1255`
- `db.cc ID=1451` -> `case_legacy_id=1255`
- `db.cc ID=1527` -> `case_legacy_id=1279`
- `db.cc ID=1600` -> `case_legacy_id=1317`

## Replay impact
After replaying only the high-confidence overrides:

- `applied_override_count`: `5`
- `db.cc` target rows: `1458 -> 1463`
- `db.cc` skipped rows: `170 -> 165`

Important nuance:
- `migration_anomaly` remains `294` because overridden anomalies are still persisted for auditability; they move from `open` to `overridden`, not deleted.

## Queue composition
The manual review queue is dominated by `db.cc` rows with strong site/type payload but multiple plausible cases at the same site.

High-priority non-placeholder items include:
- many `db.cc` rows with 2-12 candidate cases after exact site/gxp/scope filtering
- `db.Tdoi2 ID=155`, whose root `db.Tdoi ID=187` is placeholder-only

Medium-priority items include:
- `db.dkkd ID=704`, which carries English address text but no exact site match in the current imported site export

## Output artifacts
- [artifacts/phase3d/manual_evidence_analysis.json](/D:/GXP-QLCL/artifacts/phase3d/manual_evidence_analysis.json)
- [artifacts/phase3d/high_confidence_overrides.json](/D:/GXP-QLCL/artifacts/phase3d/high_confidence_overrides.json)
- [artifacts/phase3d/manual_review_queue.json](/D:/GXP-QLCL/artifacts/phase3d/manual_review_queue.json)
- [artifacts/phase3d/reconciliation_high_confidence.json](/D:/GXP-QLCL/artifacts/phase3d/reconciliation_high_confidence.json)

## Decision value
Phase 3d shows that:

- the remaining anomalies are no longer one undifferentiated backlog
- a small subset can be replayed safely with exact evidence rules
- the larger unresolved subset now has concrete candidate lists and review priority

## Next recommended step
Historical next step at the time:
- proceed to a curated review pass over [artifacts/phase3d/manual_review_queue.json](/D:/GXP-QLCL/artifacts/phase3d/manual_review_queue.json), likely in this order:

- `db.Tdoi2 ID=155`
- `db.cc` rows with 2-3 candidates first
- `db.cc` rows with explicit rename/address-change notes
- residual `db.dkkd` and placeholder-rooted anomalies

Current successor state:
- the review queue should not be reused blindly as a current business-review backlog without first removing rows superseded by Phase 3q.
