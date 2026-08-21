# ADR 0009: Add a read-only storage probe endpoint

## Status
Approved

## Date
2026-08-13

## Context
Phase 4 storage logic now includes:
- environment-based configuration
- persisted binding lookup
- live folder resolution fallback

The project needs a low-risk way to exercise that flow end-to-end before connecting business workflows or production-like document actions.

## Decision
- Add a read-only endpoint for inspection-folder lookup.
- The endpoint returns only root-relative path and resolution metadata.
- It must not expose absolute UNC paths or credentials.
- If storage is not configured, the endpoint returns `503`.

## Consequences
Positive:
- end-to-end verification is possible without document mutation
- app wiring can be tested independently from future business features

Negative:
- introduces an operational endpoint that should remain internal-only
