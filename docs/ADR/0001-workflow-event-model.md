# ADR 0001: Replace `db.ktra` Wide Row With Workflow/Event Model

## Status
Accepted

## Context
Phase 0 reverse engineering shows that `db.ktra` mixes:
- application intake
- assessment
- planning
- inspection execution
- decision metadata
- certificate linkage
- downstream history fields

This layout is convenient for Excel formulas but not a safe target relational design.

## Decision
The web target will not mirror `db.ktra` 1:1.
It will model:
- stable case record
- stage/event records for intake, assessment, planning, execution, outcome
- explicit links to certificate/document entities

## Consequences
- Migration needs transformation logic, not direct sheet copy.
- Reconciliation must verify semantic parity, not table-shape parity.
- Reporting can still project a legacy-like flattened view when needed.
