# Phase 3c - Evidence-Based Auto Remediation Pass

## Goal
Run one conservative remediation pass that only applies overrides when the legacy workbook provides a single, directly supported answer.

## Historical note
This phase captured the first strong signal that many anomalies were placeholder-like rows. That interpretation has now been strengthened and superseded by explicit business-owner confirmation on August 14, 2026 for the review-report scope:
- the relevant rows are intended blanked legacy rows kept only to preserve Excel `INDEX`-based row positions;
- see [PHASE3Q_CONFIRMED_BLANKED_ROWS.md](/D:/GXP-QLCL/docs/PHASE3Q_CONFIRMED_BLANKED_ROWS.md).

## Inputs
- [artifacts/phase2/reconciliation.json](/D:/GXP-QLCL/artifacts/phase2/reconciliation.json)
- [artifacts/phase3c/legacy_snapshot.json](/D:/GXP-QLCL/artifacts/phase3c/legacy_snapshot.json)
- [artifacts/phase3/site.json](/D:/GXP-QLCL/artifacts/phase3/site.json)

## Tools
- [tools/export_legacy_snapshot.py](/D:/GXP-QLCL/tools/export_legacy_snapshot.py)
- [tools/phase3c_remediation.py](/D:/GXP-QLCL/tools/phase3c_remediation.py)
- [tools/analyze_phase3c_remediation.py](/D:/GXP-QLCL/tools/analyze_phase3c_remediation.py)
- [tools/run_phase3c_auto_reimport.py](/D:/GXP-QLCL/tools/run_phase3c_auto_reimport.py)

## Findings
On August 13, 2026:

- Baseline anomalies: `294`
- Auto-resolvable anomalies with strict evidence: `1`
- Auto-applied override count after replay: `1`
- Remaining anomalies after replay: `293`

The single auto-resolved case is:
- `db.ktra ID=257` -> `site_legacy_id=36`

Evidence:
- upstream `db.ktra` row `257` is effectively placeholder-only
- downstream `db.cc ID=268` references inspection `257`
- the same certificate row carries `ID CƠ SỞ=36`
- no conflicting downstream site reference was found for inspection `257`

## Placeholder-heavy anomaly population
The analysis also shows a large share of anomaly rows are effectively placeholder rows with no business payload beyond `ID`:

- `db.cso`: `3`
- `db.ktra`: `37`
- `db.cc`: `17`
- `db.dkkd`: `49`
- `db.Tdoi`: `22`
- `db.Tdoi2`: `1`

This is strong evidence that many remaining anomalies are not resolvable by FK inference alone and may require:
- manual business confirmation
- alternate provenance sources outside the core workbook sheets
- explicit archival/exclusion rules

Current interpretation for the confirmed report scope:
- these rows should be excluded as confirmed blanked legacy rows;
- they are not current manual-review backlog.

## Output artifacts
- [artifacts/phase3c/remediation_analysis.json](/D:/GXP-QLCL/artifacts/phase3c/remediation_analysis.json)
- [artifacts/phase3c/remediation_overrides.auto.json](/D:/GXP-QLCL/artifacts/phase3c/remediation_overrides.auto.json)
- [artifacts/phase3c/reconciliation_auto.json](/D:/GXP-QLCL/artifacts/phase3c/reconciliation_auto.json)

## Decision value
Phase 3c reduces uncertainty more than it reduces row count:

- it proves the override replay path works end-to-end
- it identifies where deterministic inference is genuinely possible
- it separates placeholder legacy rows from potentially remediable business rows

## Next recommended step
Historical next step at the time:
- proceed to a manual evidence review pass focused on the non-placeholder anomalies that still carry downstream payload, especially:
- `db.cc` rows with non-empty site/type/scope but missing case linkage
- `db.Tdoi2 ID=155` because it references missing root `db.Tdoi ID=187`
- any legacy cases where external folder/document evidence can establish the missing site identity

Current successor state:
- the confirmed review-report population is now excluded, not queued for review.
