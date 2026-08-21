# Phase 1 Schema Baseline

## Scope
This baseline turns the Phase 0 target model into executable SQLAlchemy metadata for PostgreSQL-oriented schema design.

Implementation source:
- `backend/app/db/models/phase1.py`
- `backend/app/db/base.py`
- `backend/app/db/enums.py`
- `backend/app/db/schema.py`

Rendered artifact:
- `artifacts/phase1/schema.sql`

## Domain slices covered
- Master data: `company`, `site`, `person`, `person_role`, `professional_license`, `inspector_profile`, `dictionary_value`
- Workflow: `case`, `case_application`, `case_assessment`, `inspection_plan`, `inspection_event`, `inspection_team`, `inspection_team_member`, `inspection_outcome`
- Certification: `certificate`, `certificate_version`, `certificate_scope`
- Business eligibility: `business_eligibility_certificate`, `business_eligibility_version`, `business_eligibility_certificate_link`
- Change management: `change_request`, `change_request_detail`, `change_approval`
- Document model: `document`, `document_variant`, `document_version`, `document_relation`, `template_definition`, `template_binding`, `document_generation_run`, `document_source_dependency`
- Storage/audit/RBAC: `storage_binding`, `storage_resolution_log`, `rbac_role`, `app_user`, `app_user_role`, `audit_event`, `migration_anomaly`, `current_projection_conflict`, `legacy_id_map`

## Invariants encoded in schema
- Legacy IDs are preserved with dedicated unique fields instead of reused as primary keys.
- `db.ktra` is split into case/application/assessment/plan/event/outcome tables.
- DDKD to certificate relation is modeled explicitly through `business_eligibility_certificate_link`.
- Document model is separated into logical document, variant, and version.
- Document family identity is registry-driven via `document.family_code`.
- Template selection and document execution are modeled explicitly through `template_binding` and `document_generation_run`.
- Copy-forward provenance is modeled through `document_source_dependency`.
- Storage binding uses stable legacy triplet: `year + site_legacy_id + inspection_legacy_code`.
- Storage binding triplet must be all-null or all-present.
- `document_version` may hold the exact binary locator used for source-document reads or output-document lineage.
- Every `document` must belong to at least one supported parent entity.
- `document_generation_run.output_document_version_id` can be populated before binary write finalization.
- `template_definition` may hold the exact template-binary locator used by template-aware render adapters.
- `current_projection_conflict` provides an auditable fail-closed surface for duplicate-current legacy keys that cannot yet be resolved safely.

## Intentional non-goals in this phase
- No FastAPI endpoints yet.
- No service-layer implementation yet.
- No live Alembic environment or applied database migration yet.
- No import pipeline from workbook snapshot yet.

## Next expected step
- Phase 3p conflict adjudication contract:
  - surface duplicate-current conflicts explicitly,
  - keep auto-resolution disabled until a business-safe rule is proven,
  - preserve adjudication payload separately from imported source truth.
