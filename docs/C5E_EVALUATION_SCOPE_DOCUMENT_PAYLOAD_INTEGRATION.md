# C.5e Evaluation Scope → Document Payload Integration

## Decision

The branch-aware scalar projection from C.5e is now integrated at the document payload boundary. The generic Phase 5 payload registry remains an inventory/validator for non-scope fields; it is **not** the semantic owner for evaluation-scope bookmark values.

Production integration owner:

`backend/app/document/evaluation_scope_payload.py`

## Runtime flow

For a C.5e document family, `build_document_payload_result` performs the following order:

1. reject caller-provided scope bookmark aliases so no manual payload can override canonical scope;
2. validate/build non-scope values through the existing generic payload registry;
3. for branches with active scalar scope writes, load `CaseEvaluationScope`, its blocks/selections, and the exact persisted taxonomy version for the case GxP family;
4. resolve each selected key from current `taxonomy_node_id` rather than the historical `node_key_snapshot`;
5. project the family-specific fields through `project_vba_document_scope_fields`;
6. append those fields to the payload envelope with C.5e provenance;
7. remove generic-registry scope-field false positives from `missing_registry_fields`.

The adapter does not query or consume `CaseEvaluationScopeUnkeyedEntry`. It does not read `rendered_prose` or workspace `summary_text`.

## Fail-closed conditions

A family that actively writes scalar scope fields requires `case_id`, `STRUCTURED_VALID` canonical scope, a persisted taxonomy version, taxonomy rows for the case GxP family, and every selection to resolve inside that exact taxonomy family/version. Missing or orphaned data blocks generation instead of falling back to prose or caller payload.

Families/branches with no active scalar scope write (`INSPECTION_QD_KT`, `CERTIFICATE_DECISION`, and `INSPECTION_PT_CT` when `copy_pt=true`) do not require scope projection input.

## `CopyPT`

`INSPECTION_PT_CT` exposes `copy_pt` as an explicit boolean request condition. When true, the VBA branch that writes the scalar scope bookmarks is bypassed, so C.5e emits no scalar scope fields for that branch.

## Still separate

`Input_DC_to_CC` remains intentionally outside this integration. It is a structured certificate-detail/bookmark-row path, not a scalar payload projection. Compact `summary_text` and scalar C.5e projection are not authorized substitutes.
