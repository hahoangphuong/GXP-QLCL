# ADR 0026: Runtime Template Contract Gate

## Context
Phase 5 now has:
- a curated VBA-derived payload registry;
- a real-template audit against active binaries under `legacy/Templates`;
- a reconciliation artifact that shows which families are exact, variant-grouped, or unresolved.

Directly feeding payload field names into the DOCX renderer is no longer a safe long-term assumption.

## Decision
Introduce a runtime template-contract layer between payload builders and DOCX XML mutation.

The first runtime baseline is intentionally narrow:
- enable contract-driven replacement only for families whose scalar field reconciliation is fully `exact`;
- keep all other families on raw payload passthrough;
- fail closed later when a family is explicitly promoted into richer alias/expansion behavior.

## Consequences
- The renderer now has a clean seam where family-specific physical bookmark contracts can be introduced without changing business payload builders.
- Safe exact-match families such as `DDKD_CERTIFICATE` and scalar portions of `INSPECTION_CAPA_*` can move first.
- Ambiguous families are not silently auto-translated.
- Future 1-to-many bookmark expansion can be added on top of the same contract layer once adjudicated.
