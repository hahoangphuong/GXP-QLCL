# ADR 0014: Registry-Seeded Template Metadata and Payload Builders

## Status
Accepted

## Context
Phase 5 already established:
- curated document family registry;
- schema support for template definitions, bindings, and generation runs;
- service-level selection and payload contracts.

What remained missing was a deterministic bridge between curated registry evidence and seedable application metadata.

## Decision
Derive two baseline artifacts from the curated registry:
- seed-oriented template metadata (`template_definition` + `template_binding` baseline)
- payload-builder registry baseline

Rules:
- document type code is derived deterministically from `family_code`
- variant type is derived from source application:
  - `Word` -> `editable_docx`
  - `Excel` -> `editable_xlsx`
- selection hints such as `{GP}` or `Moi/Tai` are preserved as binding metadata, not hard-coded service branches
- payload-builder baseline is bookmark-driven and traceable to source procedures

## Consequences
- Later database seeding can be deterministic and rerunnable.
- Payload builder implementation can progress family by family without losing provenance.
- Excel-backed support documents remain represented honestly in the target model.
