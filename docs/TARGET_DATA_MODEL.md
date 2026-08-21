# Target Data Model

## Core principles
- Preserve legacy IDs as external references, not as the only primary key strategy.
- Separate business entities from document/file artifacts.
- Separate workflow state from certificate/document outputs.
- Model Synology path resolution as infrastructure metadata, not as domain identity.
- Treat issued-successor creation and current-state promotion as different business events.

## Proposed entities
### Master data
- `company`
- `site`
- `person`
- `person_role`
- `professional_license`
- `inspector`
- `dictionary_value`

### Workflow and case
- `case`
- `case_type`
- `case_application`
- `case_assessment`
- `inspection_plan`
- `inspection_event`
- `inspection_team`
- `inspection_team_member`
- `inspection_outcome`
- `capa_cycle`

### Certification
- `certificate`
- `certificate_version`
- `certificate_scope`
- `certificate_status_event`
- `certificate_lineage_edge`
- `business_eligibility_certificate`
- `business_eligibility_version`
- `business_eligibility_status_event`
- `business_eligibility_lineage_edge`
- `certificate_link`

Certificate-specific note:
- `certificate.case_id` must be nullable.
- A certificate may be:
  - case-backed: issued from a real inspection/case
  - non-case-backed: reissued or administratively issued without a real inspection case
- `site_id` remains mandatory for `certificate`.
- A successor certificate version created from change flow must not automatically become `current`.
- Promotion from issued-successor to current-active should be modeled as an explicit status event, because legacy does this through later operator confirmation.

### Change management
- `change_request`
- `change_request_detail`
- `change_approval`
- `change_request_affected_artifact`
- `change_request_issued_artifact`

### Documents
- `document`
- `document_variant`
- `document_version`
- `document_relation`
- `template_definition`
- `template_binding`
- `document_generation_run`
- `document_source_dependency`

### Storage and audit
- `storage_binding`
- `storage_resolution_log`
- `audit_event`
- `legacy_id_map`

Audit-event note:
- `audit_event` is not only an append-only text log.
- It must preserve:
  - `changed_fields_json`
  - `old_values_json`
  - `new_values_json`
  - optional `request_id`
- `payload_redacted` must never carry secrets, tokens, auth headers/cookies, or file binary content markers; current baseline treats it as a non-secret operational payload snapshot.

CAPA note:
- `capa_cycle` is a child workflow of `case`, not a replacement for `case.state`.
- The latest CAPA cycle for a case determines whether the case may advance from `inspection_completed` to `awaiting_certificate_decision`.
- The same latest-cycle rule also gates case-backed certificate issuance, current-certificate promotion, and `awaiting_certificate_decision -> certified`.
- `capa_cycle.assessor_user_id` is the authoritative authenticated assessor identity when the action occurs in the web app.
- `capa_cycle.assessor_name` remains nullable as a legacy-compatible display snapshot / imported free-text field when no authenticated historical user can be bound.
- Legacy evidence currently proves round 1 and round 2 flows; the target model therefore stores `round_no` as open-ended rather than hardcoding a maximum of 2.

## Legacy mapping
| Legacy source | Target concept |
|---|---|
| `db.cty` | `company` |
| `db.cso` | `site` |
| `db.ktra` | `case` + `case_application` + `case_assessment` + `inspection_plan` + `inspection_event` + `inspection_outcome` |
| `db.cc` | `certificate` + `certificate_version` + `certificate_scope` + lineage/status events |
| `db.dkkd` | `business_eligibility_certificate` + `business_eligibility_version` + lineage/status events + relation to one or more `certificate` rows |
| `db.Tdoi` | `change_request` / `change_approval` / affected-artifact links / issued-successor links |
| `db.Tdoi2` | `change_request_detail` |

## Required legacy key preservation
- `legacy_company_id`
- `legacy_site_id`
- `legacy_inspection_id`
- `legacy_certificate_id`
- `legacy_dkkd_id`
- `legacy_change_id`

## Folder identity model
- `storage_binding` must resolve by:
  - `year`
  - `site_legacy_id`
  - `inspection_legacy_code`
- Descriptive folder name is stored as observed label only.

## DDKD relationship note
- `db.dkkd.ID CC` proves that one DDKD record may refer to multiple certificate IDs.
- Model as join table, not single FK field.
- Legacy also proves that one DDKD successor row can exist before it becomes current.
- Promotion to current should be modeled explicitly, not inferred only from row creation time.

## Lineage and status note
- Legacy flat tables combine at least four concepts that should be separated in target design:
  - business artifact identity
  - issued row/version payload
  - predecessor/successor lineage
  - current/effective status transitions
- For both GPs certificates and DDKD:
  - successor creation and current-state promotion are different business events
  - status should support at least `draft_or_incomplete`, `issued_not_current`, `current`, `obsolete`, `invalidated`, and `expired` where applicable
- `certificate_lineage_edge` and `business_eligibility_lineage_edge` should preserve predecessor/successor links independently from current-state flags.
- `certificate_status_event` and `business_eligibility_status_event` should preserve when and why a row became current, obsolete, invalidated, or expired.

## Current lookup projection note
- Legacy also depends on workbook-maintained current-row lookup projections such as `db_LastID_CCGPs`, `db_LastIDCs_DDK`, and `db_LastID_ktra`.
- These should not be migrated as primary truth tables.
- Legacy evidence also shows a separate sheet-level key grid plus `MATCH(...)` formula layer sitting above those projections.
- Reconciliation evidence now shows that the sheet-level grid can drift stale relative to base-table current mirrors.
- Instead, target architecture should expose a derived read model such as:
  - `current_certificate_projection`
  - `current_business_eligibility_projection`
  - `current_case_projection`
- Those projections may be implemented as SQL views, materialized views, or projection tables, but they must be downstream of transactional truth rather than the source of truth itself.
- Duplicate-current-key anomalies in legacy mean the projection builder must be able to flag non-unique “current” candidates instead of silently picking one.

Additional projection-conflict note:
- Target current-state projections should expose an explicit conflict surface such as:
  - `current_projection_conflict`
  - or equivalent projection-refresh anomaly table
- That conflict record should preserve:
  - projection type
  - business key under evaluation
  - candidate legacy row IDs
  - refresh timestamp
  - adjudication status

## Document model note
- One logical document can have:
  - one or more editable `.docx` versions
  - one or more editable `.xlsx` versions for Excel-backed support flows
  - derived `.pdf`
  - scanned `.pdf`
  - signed `.pdf`
- Keep version lineage separate from business document type.
- `template_definition` stores logical template identity, legacy template name, source application, and current contract version.
- `template_definition` may also carry the exact binary locator of the managed template asset.
- `template_binding` maps a logical document family and business branch to a concrete template definition.
- `document_generation_run` stores generation inputs, template version used, source-document dependencies, outcome, and audit metadata.
- `document.family_code` is the stable registry-driven identifier for logical document families.
- `document_source_dependency` stores copy-forward provenance from source documents or source versions used during generation.
- `document_version` may carry an exact storage locator (`storage_root`, `storage_relative_path`, optional original filename) when the concrete binary is known.
- `storage_binding` remains folder-level binding and must not be treated as exact file identity.

## Certificate linkage note
- Blank `db.cc.ID DOT KTRA` is not automatically a data error.
- If `db.cc.ID Co so` resolves but `ID DOT KTRA` is blank, migration may still import the certificate as a valid non-case-backed certificate.
- If `db.cc.ID DOT KTRA` is non-blank but unresolved, that remains a migration anomaly.
