# ADR 0013: DocumentService Selection and Payload Contract

## Status
Accepted

## Context
The project now has:
- a curated document family registry;
- a schema baseline for template binding and generation runs;
- proven copy-forward dependencies in legacy VBA.

What is still missing is the service-level contract that defines:
- what a generation request looks like;
- how template selection behaves;
- how payload fields are passed without pushing raw VBA behavior into controllers or storage adapters.

## Decision
Adopt a fail-closed `DocumentService` baseline with:
- `DocumentGenerationRequest` as the application-facing request shape;
- `DocumentPayloadEnvelope` as a typed payload container;
- deterministic template selection from curated registry entries;
- explicit `SourceDependencyPlan` derived from copy-forward dependencies.

Selection rules:
- match by `family_code` first;
- optionally narrow by `storage_scope`, `source_application`, `gxp_type`, and `legacy_mode`;
- fail closed on zero or multiple matches.

Payload rules:
- payload fields carry a source label for traceability;
- payload redaction is performed before persistence into generation-run audit data;
- payload structure remains flat in the baseline until real template binaries justify a richer DSL.

## Consequences
- Controllers and future API endpoints can submit generation requests without knowing template filenames.
- `DocumentService` stays the only owner of template selection logic.
- Audit and retry flows can persist redacted input safely.
- The current baseline remains compatible with future richer payload schemas.
