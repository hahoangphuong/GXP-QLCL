# Phase 5 Payload and Source Baseline

## Scope
This phase turns the payload-builder registry and copy-forward planning into executable service-side baseline modules.

## Delivered
- runtime payload builder registry loader
- strict payload envelope builder
- source lookup request builder
- fail-closed source candidate resolver
- DB-backed source candidate query baseline

## Python modules
- `backend/app/document/payload_builders.py`
- `backend/app/document/source_resolver_contract.py`

## Service flow extension
1. Select template and dependency plan.
2. Build payload envelope from registry-known fields.
3. Derive source lookup requests for copy-forward dependencies.
4. Resolve prior documents before any render adapter is invoked.

## Current tradeoffs
- strict mode rejects unexpected input fields by default
- required vs optional field semantics are still deferred
- source resolution currently uses seeded template metadata plus database rows, but still stops before binary access
