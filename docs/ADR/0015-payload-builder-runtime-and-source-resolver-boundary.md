# ADR 0015: Payload Builder Runtime and Source Resolver Boundary

## Status
Accepted

## Context
The project already has:
- a curated payload-builder registry;
- document generation planning with copy-forward dependency plans;
- schema support for generation runs and source dependencies.

The remaining gap is the runtime boundary between:
- raw application/domain values,
- normalized payload envelopes,
- and fail-closed source document lookup requests.

## Decision
Introduce two runtime baseline modules:
- `payload_builders.py`
- `source_resolver_contract.py`

Rules:
- payload building is family-driven and defaults to strict field acceptance;
- payload values are mapped only through registry-known fields;
- source lookup requests are derived from `DocumentGenerationPlan`;
- source candidate resolution fails closed on zero or multiple matches.

## Consequences
- `DocumentService` orchestration can be exercised before a render adapter exists.
- Copy-forward lookup becomes a first-class domain concern instead of an ad-hoc filesystem read.
- Unknown input fields are surfaced early instead of silently passing through to templates.
