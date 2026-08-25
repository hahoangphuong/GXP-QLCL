# Phase 3s Confirmed Blanked Resurrection Contract

## Purpose
Define the only allowed path for reviving a row that is already covered by the confirmed-blanked contract.

This is intentionally separate from generic remediation overrides:
- generic overrides repair unresolved business rows;
- this contract re-authorizes a row that the business owner previously classified as a semantic deletion.

## Inputs
- [confirmed_blanked_rows.json](/D:/GXP-QLCL/artifacts/phase3q/confirmed_blanked_rows.json)
- [confirmed_blanked_resurrections.json](/D:/GXP-QLCL/artifacts/phase3q/confirmed_blanked_resurrections.json)

## Rules
- A row in `confirmed_blanked_rows.json` stays excluded by default.
- A generic `remediation_overrides` entry must not resurrect that row by itself.
- Resurrection requires an explicit matching approval entry in `confirmed_blanked_resurrections.json`.
- The approved override must match exactly by:
  - `source_sheet`
  - `source_row_key`
  - approved remediation key
  - approved target legacy ID
- If the approval file is absent or does not match, importer must fail closed.

## Artifact shape

```json
{
  "rows": [
    {
      "source_sheet": "db.cc",
      "source_row_key": "256",
      "approved_override": {
        "site_legacy_id": 34
      },
      "approved_on": "2026-08-25",
      "approval_note": "Business owner explicitly wants this row materialized again."
    }
  ]
}
```

## Operational meaning
- This file is not a heuristic suggestion list.
- Each row is a named owner decision that supersedes the default exclusion rule for exactly one override payload.
- Future refresh/rehearsal imports remain deterministic because the same snapshot plus the same approval artifact yields the same result.

## Guardrails
- Do not infer resurrection from technical exact matches alone.
- Do not auto-populate this file from analysis tooling.
- Do not use it as a catch-all fallback for unresolved anomalies.
- If the owner has not made an explicit resurrection decision, keep the row excluded.
