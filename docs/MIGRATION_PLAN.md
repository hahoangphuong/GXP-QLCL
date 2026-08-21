# Migration Plan

## Phase 0 - Reverse engineering
Deliver workbook/named-range inventory, VBA/UserForm/event inventory, dependency graph, data read/write map, filesystem map, Word automation map, workflow model, document registry draft and legacy validator.

Completed artifacts include:
- `docs/LEGACY_SYSTEM_MAP.md`
- `docs/VBA_FUNCTION_MAP.md`
- `docs/DATA_DICTIONARY_LEGACY.md`
- `docs/WORKFLOW_MODEL.md`
- `docs/LEGACY_RECONCILIATION_REPORT.md`
- `tools/legacy_audit.py`

## Phase 1 - Target model
Define PostgreSQL schema, legacy ID mapping, constraints/indexes, workflow/event model, document model, RBAC and audit.

Current baseline artifacts:
- `backend/app/db/models/phase1.py`
- `backend/app/db/schema.py`
- `alembic.ini`
- `migrations/env.py`
- `migrations/script.py.mako`
- `migrations/versions/7ad763833b09_initial_schema_runtime.py`
- `docs/TARGET_DATA_MODEL.md`
- `docs/PHASE1_SCHEMA_BASELINE.md`
- `artifacts/phase1/schema.sql`

Current Phase 1 execution note:
- schema evolution is now represented by Alembic revisions instead of documentation-only placeholders;
- runtime/test bootstrap should validate `alembic upgrade head` rather than rely on `Base.metadata.create_all()` outside isolated tests/tools.

## Phase 2 - Read-only prototype
Import into staging PostgreSQL, reconcile counts/IDs/FKs, report anomalies, do not modify Synology files, build read-only web/search.

## Phase 3 - Structured-data migration
Move companies, sites, cases, inspections, certificates and history incrementally.

Current implementation is split into:
- Phase 3a: normalized export + anomaly summarization artifacts.
- Phase 3b: persisted remediation queue (`migration_anomaly`) plus deterministic override-driven reimport.

Current Phase 3b artifacts:
- `backend/app/domain/phase2_import.py`
- `tools/generate_phase3b_remediation_template.py`
- `tools/run_phase3b_reimport.py`
- `docs/PHASE3B_REMEDIATION.md`
- `artifacts/phase3b/remediation_overrides.template.json`
- `artifacts/phase3b/remediation_candidates.json`
- `artifacts/phase3b/reconciliation.json`

Current Phase 3c artifacts:
- `tools/export_legacy_snapshot.py`
- `tools/phase3c_remediation.py`
- `tools/analyze_phase3c_remediation.py`
- `tools/run_phase3c_auto_reimport.py`
- `docs/PHASE3C_REMEDIATION_PASS.md`
- `artifacts/phase3c/legacy_snapshot.json`
- `artifacts/phase3c/remediation_analysis.json`
- `artifacts/phase3c/remediation_overrides.auto.json`
- `artifacts/phase3c/reconciliation_auto.json`

Current Phase 3d artifacts:
- `tools/phase3d_manual_evidence.py`
- `tools/analyze_phase3d_manual_evidence.py`
- `tools/run_phase3d_high_confidence_reimport.py`
- `docs/PHASE3D_MANUAL_EVIDENCE_PASS.md`
- `artifacts/phase3d/manual_evidence_analysis.json`
- `artifacts/phase3d/high_confidence_overrides.json`
- `artifacts/phase3d/manual_review_queue.json`
- `artifacts/phase3d/reconciliation_high_confidence.json`

Current Phase 3e artifacts:
- `tools/phase3e_curated_review.py`
- `tools/analyze_phase3e_curated_review.py`
- `tools/run_phase3e_merged_reimport.py`
- `docs/PHASE3E_CURATED_REVIEW_PASS.md`
- `artifacts/phase3e/curated_review_analysis.json`
- `artifacts/phase3e/curated_overrides.json`
- `artifacts/phase3e/merged_overrides.json`
- `artifacts/phase3e/reconciliation_merged.json`

Current Phase 3f artifacts:
- `tools/phase3f_final_adjudication.py`
- `tools/analyze_phase3f_final_adjudication.py`
- `tools/run_phase3f_final_reimport.py`
- `docs/PHASE3F_FINAL_ADJUDICATION_PASS.md`
- `artifacts/phase3f/final_adjudication_analysis.json`
- `artifacts/phase3f/adjudicated_overrides.json`
- `artifacts/phase3f/final_merged_overrides.json`
- `artifacts/phase3f/reconciliation_final.json`

Current Phase 3g artifacts:
- `tools/phase3g_closeout.py`
- `tools/analyze_phase3g_closeout.py`
- `docs/PHASE3G_CLOSEOUT.md`
- `artifacts/phase3g/accepted_overrides_baseline.json`
- `artifacts/phase3g/unresolved_review_pack.json`
- `artifacts/phase3g/closeout_summary.json`
- `artifacts/phase3g/closeout_summary.md`

Current Phase 3h artifacts:
- `tools/phase3h_external_evidence.py`
- `tools/analyze_phase3h_external_evidence.py`
- `docs/PHASE3H_EXTERNAL_EVIDENCE_ADJUDICATION.md`
- `artifacts/phase3h/external_evidence_queue.json`
- `artifacts/phase3h/external_evidence_queue.csv`
- `artifacts/phase3h/external_evidence_decisions.template.json`
- `artifacts/phase3h/external_evidence_summary.json`
- `artifacts/phase3h/external_evidence_summary.md`
- `artifacts/phase3h/adjudicated_overrides.external.json`
- `artifacts/phase3h/merged_overrides.external.json`

Current Phase 3i artifacts:
- `tools/phase3i_external_reimport.py`
- `tools/run_phase3i_external_reimport.py`
- `tools/analyze_phase3i_external_reimport.py`
- `docs/PHASE3I_EXTERNAL_REIMPORT.md`
- `artifacts/phase3i/staging_external.db`
- `artifacts/phase3i/reconciliation_external.json`
- `artifacts/phase3i/reconciliation_external.md`
- `artifacts/phase3i/external_reimport_summary.json`
- `artifacts/phase3i/external_reimport_summary.md`

Current Phase 3j artifacts:
- `tools/phase3j_decision_quality_gate.py`
- `tools/analyze_phase3j_decision_quality_gate.py`
- `docs/PHASE3J_DECISION_QUALITY_GATE.md`
- `artifacts/phase3j/decision_quality_gate.json`
- `artifacts/phase3j/decision_quality_gate.md`

Current Phase 3k artifacts:
- `tools/phase3k_review_handoff.py`
- `tools/analyze_phase3k_review_handoff.py`
- `docs/PHASE3K_REVIEW_HANDOFF.md`
- `artifacts/phase3k/review_handoff_summary.json`
- `artifacts/phase3k/review_handoff_summary.md`
- `artifacts/phase3k/prioritized_review_queue.json`
- `artifacts/phase3k/prioritized_review_queue.csv`
- `artifacts/phase3k/reviewer_guide.md`

Current Phase 3l artifacts:
- `tools/phase3l_review_assignment.py`
- `tools/analyze_phase3l_review_assignment.py`
- `docs/PHASE3L_REVIEW_ASSIGNMENT.md`
- `artifacts/phase3l/review_assignment_summary.json`
- `artifacts/phase3l/review_assignment_summary.md`
- `artifacts/phase3l/review_lane_assignments.json`
- `artifacts/phase3l/review_lane_assignments.csv`
- `artifacts/phase3l/review_progress_tracker.template.json`
- `artifacts/phase3l/review_progress_tracker.template.csv`

Current Phase 3m artifacts:
- `tools/phase3m_review_progress_monitor.py`
- `tools/analyze_phase3m_review_progress_monitor.py`
- `docs/PHASE3M_REVIEW_PROGRESS_MONITOR.md`
- `artifacts/phase3m/review_progress_summary.json`
- `artifacts/phase3m/review_progress_summary.md`
- `artifacts/phase3m/review_progress_snapshot.csv`

Current Phase 3n artifacts:
- `tools/phase3n_review_starter_pack.py`
- `tools/analyze_phase3n_review_starter_pack.py`
- `docs/PHASE3N_REVIEW_STARTER_PACK.md`
- `artifacts/phase3n/review_starter_pack_summary.json`
- `artifacts/phase3n/review_starter_pack_summary.md`
- `artifacts/phase3n/submission_checklist.json`
- `artifacts/phase3n/review_quickstart.md`
- `artifacts/phase3l/review_progress_tracker.json`

Current Phase 3o artifacts:
- `tools/phase3o_adjudication_cycle_simulator.py`
- `tools/analyze_phase3o_adjudication_cycle_simulator.py`
- `docs/PHASE3O_ADJUDICATION_CYCLE_SIMULATOR.md`
- `artifacts/phase3o/simulation_summary.json`
- `artifacts/phase3o/simulation_summary.md`
- `artifacts/phase3o/simulated_external_evidence_decisions.json`
- `artifacts/phase3o/simulated_review_progress_tracker.json`
- `artifacts/phase3o/staging_simulated.db`
- `artifacts/phase3o/reconciliation_simulated.json`
- `artifacts/phase3o/reconciliation_simulated.md`

Current Phase 3p artifacts:
- `tools/build_phase3p_current_projection_conflicts.py`
- `docs/PHASE3P_CURRENT_PROJECTION_CONFLICT_CONTRACT.md`
- `artifacts/phase3p/current_projection_conflicts.json`
- `artifacts/phase3p/current_projection_conflicts.md`

Current Phase 3s artifacts:
- `tools/build_phase3s_projection_conflict_decision_template.py`
- `tools/validate_phase3s_projection_conflict_decisions.py`
- `docs/PHASE3S_CURRENT_PROJECTION_CONFLICT_ADJUDICATION.md`
- `artifacts/phase3s/current_projection_conflict_decisions.template.json`
- `artifacts/phase3s/current_projection_conflict_decisions.template.md`
- `artifacts/phase3s/current_projection_conflict_decisions.summary.json`
- `artifacts/phase3s/current_projection_conflict_decisions.summary.md`

Current Phase 3s effect:
- the `14` current-projection conflicts now have an explicit adjudication file format and validator;
- the repository can distinguish `missing decision framework` from `business decision still pending`;
- cutover should treat unresolved Phase 3s decisions as a blocking operational gate until each row is marked `winner`, `no_winner`, or intentionally `defer` under approved policy.

Current Phase 3t artifacts:
- `tools/build_phase3t_projection_conflict_review_pack.py`
- `docs/PHASE3T_CURRENT_PROJECTION_REVIEW_PACK.md`
- `artifacts/phase3t/current_projection_conflict_review_pack.json`
- `artifacts/phase3t/current_projection_conflict_review_pack.csv`
- `artifacts/phase3t/current_projection_conflict_review_pack.md`

Current Phase 3t effect:
- the `14` unresolved current-projection conflicts now have a reviewer-friendly pack with candidate-level evidence;
- business review can now happen from one consolidated CSV/Markdown surface instead of tracing multiple legacy-analysis artifacts by hand.

Current Phase 6b artifacts:
- `tools/build_phase6b_operator_pack.py`
- `docs/PHASE6B_OPERATOR_PACK.md`
- `artifacts/phase6b/desktop_operator_pack.json`
- `artifacts/phase6b/desktop_operator_pack.csv`
- `artifacts/phase6b/desktop_operator_pack.md`

Current Phase 6b effect:
- the remaining Phase 6 blocker is now packaged as an operator-facing execution and evidence handoff;
- remaining work is explicitly operational on a live private-share machine, not missing repository analysis or tooling.

Current Phase 3q artifacts:
- `tools/build_phase3q_confirmed_blanked_rows.py`
- `docs/PHASE3Q_CONFIRMED_BLANKED_ROWS.md`
- `artifacts/phase3q/confirmed_blanked_rows.json`
- `artifacts/phase3q/confirmed_blanked_rows.md`

Current Phase 3q effect on baseline:
- the `151` rows from `artifacts/phase3_review/anomaly_review_report.*` are now treated as confirmed blanked legacy rows;
- Phase 2 / Phase 3 anomaly baseline now records them as `excluded_confirmed_blanked`;
- current effective mismatch count after exclusion is `0`.

Current Phase 3r artifacts:
- `tools/build_phase3r_final_closeout.py`
- `docs/PHASE3R_FINAL_CLOSEOUT.md`
- `artifacts/phase3r/phase3_final_closeout.json`
- `artifacts/phase3r/phase3_final_closeout.md`

Current Phase 3r effect:
- Phase 3 is now considered closed under the corrected migration interpretation.
- Remaining work has moved to:
  - Phase 4 storage integration
  - Phase 5 document fidelity
  - follow-on current-projection conflict adjudication tracked in Phase 3s

## Phase 4 - Synology integration
Implement `StorageService`; preserve legacy layout; test with fake/local backend and dedicated non-production NAS share.

Current Phase 4 baseline artifacts:
- `backend/app/storage/types.py`
- `backend/app/storage/local.py`
- `backend/app/storage/filesystem.py`
- `backend/app/storage/factory.py`
- `backend/app/storage/binding_lookup.py`
- `backend/app/main.py`
- `backend/app/read_models.py`
- `tools/probe_phase4_storage_nonprod.py`
- `docs/PHASE4_STORAGE_SERVICE.md`
- `docs/PHASE4A_STORAGE_BINDING.md`
- `docs/PHASE4B_STORAGE_LOOKUP.md`
- `docs/PHASE4C_STORAGE_APP_INTEGRATION.md`
- `docs/PHASE4D_NONPROD_PRIVATE_SHARE_RUNBOOK.md`
- `docs/PHASE4E_PROBE_CLI.md`
- `docs/PHASE4F_DKKD_STORAGE_CONTRACT.md`
- `docs/PHASE4G_FINAL_CLOSEOUT.md`
- `docs/ADR/0032-dkkd-site-folder-token-contract.md`
- `artifacts/phase4/probe_triplets.template.json`
- `artifacts/phase4/probe_dkkd_sites.template.json`
- `artifacts/phase4/phase4_final_closeout.json`
- `artifacts/phase4/phase4_final_closeout.md`

Current Phase 4 effect:
- inspection-folder resolution is binding-first with fail-closed live fallback;
- DDKD site-folder resolution is standardized on the durable `(<site_id>)` token rather than full folder display names;
- read-only probe endpoints and CLI exist for both inspection and DDKD storage flows;
- private-share execution remains configuration-driven and transport-agnostic behind `StorageService`;
- Phase 4 is considered closed as a contract-and-tooling baseline, while real non-production NAS execution evidence remains an operational follow-up.

## Phase 5 - Document generation
Reverse-engineer Word templates/bookmarks/automation; replace COM automation with deterministic server-side generation where practical.

Current Phase 5 baseline artifacts:
- `backend/app/document/types.py`
- `backend/app/document/registry.py`
- `backend/app/document/service_contract.py`
- `backend/app/document/seed_contract.py`
- `backend/app/document/seed_runtime.py`
- `backend/app/document/payload_builders.py`
- `backend/app/document/source_resolver_contract.py`
- `backend/app/document/source_resolver_db.py`
- `backend/app/document/source_binary_contract.py`
- `backend/app/document/source_binary_access.py`
- `backend/app/document/version_locator.py`
- `backend/app/document/output_version.py`
- `backend/app/document/docx_render.py`
- `backend/app/document/template_binary.py`
- `backend/app/document/docx_template_render.py`
- `backend/app/document/template_contract_runtime.py`
- `backend/app/document/service.py`
- `backend/app/document/persistence.py`
- `tools/extract_phase5_document_contract.py`
- `tools/build_phase5_template_registry.py`
- `tools/build_phase5_document_seed_artifacts.py`
- `tools/seed_phase5_template_metadata.py`
- `tools/audit_phase5_real_templates.py`
- `tools/build_phase5_template_contract_reconciliation.py`
- `tools/build_phase5_dkkd_variant_contracts.py`
- `tools/build_phase5_bbtd_variant_contracts.py`
- `tools/build_phase5_ddkd_appendix_field_adjudication.py`
- `tools/smoke_phase5_document_pipeline.py`
- `tools/smoke_phase5_pre_render_orchestration.py`
- `tools/smoke_phase5_source_binary_access.py`
- `tools/smoke_phase5_output_allocation.py`
- `tools/smoke_phase5_output_write.py`
- `tools/smoke_phase5_docx_render_baseline.py`
- `tools/smoke_phase5_template_ingestion.py`
- `tools/smoke_phase5_template_bookmark_render.py`
- `tools/smoke_phase5_table_region_render.py`
- `tools/smoke_phase5_header_footer_render.py`
- `tools/smoke_phase5_runtime_template_contract.py`
- `tools/smoke_phase5_dkkd_variant_guard.py`
- `tools/smoke_phase5_dkkd_certificate_render.py`
- `tools/smoke_phase5_bbtd_variant_guard.py`
- `tools/smoke_phase5_bbtd_variant_render.py`
- `tools/smoke_phase5_ddkd_appendix_decision_selection.py`
- `tools/build_phase5_final_closeout.py`
- `docs/PHASE5_DOCUMENT_CONTRACT_BASELINE.md`
- `docs/DOCUMENT_TEMPLATE_REGISTRY.md`
- `docs/DOCUMENT_SERVICE_CONTRACT.md`
- `docs/DOCUMENT_SOURCE_RESOLVER.md`
- `docs/DOCUMENT_GENERATION_PERSISTENCE.md`
- `docs/TEMPLATE_METADATA_SEED_BASELINE.md`
- `docs/DOCUMENT_PAYLOAD_BUILDERS.md`
- `docs/PHASE5_DOCUMENT_SERVICE_BASELINE.md`
- `docs/PHASE5_PAYLOAD_AND_SOURCE_BASELINE.md`
- `docs/PHASE5_PERSISTENCE_BASELINE.md`
- `docs/PHASE5_SEED_AND_DB_SOURCE_BASELINE.md`
- `docs/PHASE5_PRE_RENDER_ORCHESTRATION.md`
- `docs/PHASE5_SOURCE_BINARY_LOCATOR.md`
- `docs/PHASE5_OUTPUT_ALLOCATION_AND_WRITE.md`
- `docs/PHASE5_DOCX_RENDER_BASELINE.md`
- `docs/PHASE5_TEMPLATE_INGESTION_BASELINE.md`
- `docs/PHASE5_TEMPLATE_BOOKMARK_RENDER_BASELINE.md`
- `docs/PHASE5_TABLE_REGION_RENDER_BASELINE.md`
- `docs/PHASE5_HEADER_FOOTER_RENDER_BASELINE.md`
- `docs/PHASE5_REAL_TEMPLATE_AUDIT.md`
- `docs/PHASE5_TEMPLATE_CONTRACT_RECONCILIATION.md`
- `docs/PHASE5_RUNTIME_TEMPLATE_CONTRACT_BASELINE.md`
- `docs/PHASE5_DDKD_OUTPUT_BASELINE.md`
- `docs/PHASE5_BBTD_VARIANT_CONTRACT_BASELINE.md`
- `docs/PHASE5_DDKD_APPENDIX_DECISION_SELECTION_BASELINE.md`
- `docs/PHASE5_FINAL_CLOSEOUT.md`
- `docs/ADR/0011-document-contract-registry-first.md`
- `docs/ADR/0012-document-family-binding-and-generation-run.md`
- `docs/ADR/0013-document-service-selection-and-payload-contract.md`
- `docs/ADR/0014-registry-seeded-template-metadata-and-payload-builders.md`
- `docs/ADR/0015-payload-builder-runtime-and-source-resolver-boundary.md`
- `docs/ADR/0016-document-generation-persistence-before-render.md`
- `docs/ADR/0017-seeded-template-metadata-and-db-source-resolution.md`
- `docs/ADR/0018-pre-render-document-orchestration-and-source-binary-boundary.md`
- `docs/ADR/0019-document-version-exact-binary-locator.md`
- `docs/ADR/0020-output-document-version-allocation-and-write-contract.md`
- `docs/ADR/0021-synthetic-docx-render-baseline-before-template-ingestion.md`
- `docs/ADR/0022-template-binary-locator-and-template-aware-readiness.md`
- `docs/ADR/0023-template-aware-scalar-bookmark-docx-baseline.md`
- `docs/ADR/0024-table-region-row-repeat-docx-baseline.md`
- `docs/ADR/0025-header-footer-bookmark-docx-baseline.md`
- `docs/ADR/0026-runtime-template-contract-gate.md`
- `docs/ADR/0027-dkkd-output-exact-locator-without-inspection-binding.md`
- `docs/ADR/0028-dkkd-template-variant-contract-detection.md`
- `docs/ADR/0029-bbtd-concrete-template-slot-mapping.md`
- `docs/ADR/0030-ddkd-appendix-decision-selection-split.md`
- `artifacts/phase5/document_contract.json`
- `artifacts/phase5/document_contract.md`
- `artifacts/phase5/template_registry.curated.json`
- `artifacts/phase5/template_registry.curated.md`
- `artifacts/phase5/template_seed.curated.json`
- `artifacts/phase5/template_seed.curated.md`
- `artifacts/phase5/payload_builder_registry.json`
- `artifacts/phase5/payload_builder_registry.md`
- `artifacts/phase5/template_compatibility_audit.json`
- `artifacts/phase5/template_compatibility_audit.md`
- `artifacts/phase5/template_contract_reconciled.json`
- `artifacts/phase5/template_contract_reconciled.md`
- `artifacts/phase5/dkkd_template_variants.json`
- `artifacts/phase5/dkkd_template_variants.md`
- `artifacts/phase5/bbtd_template_variants.json`
- `artifacts/phase5/bbtd_template_variants.md`
- `artifacts/phase5/ddkd_appendix_field_adjudication.json`
- `artifacts/phase5/ddkd_appendix_field_adjudication.md`
- `artifacts/phase5/phase5_final_closeout.json`
- `artifacts/phase5/phase5_final_closeout.md`

Current Phase 5 effect:
- document generation is now closed as a contract/runtime baseline rather than as full legacy-faithful parity for every family;
- exact-safe runtime scalar replacement exists for `INSPECTION_CAPA_LAN_1` and `INSPECTION_CAPA_LAN_2`;
- concrete-template variant-exact rendering exists for `DDKD_CERTIFICATE` and `INSPECTION_BBTD_HOSO_DK`;
- `DDKD_APPENDIX_OR_DECISION` is selection-safe but still blocked from render-safe promotion on unresolved missing-bookmark policy;
- unresolved or copy-forward-heavy families remain fail-closed on explicit `payload_passthrough` baseline rather than guessed promotion;
- PowerPoint-backed legacy output remains out of scope.

## Phase 6 - Inspector desktop PoC
Tailscale + private NAS access + Explorer + Word.
Test office Wi-Fi, hotspot/mobile, intermittent network, locks, two users, save during disconnect/reconnect.

Current Phase 6 baseline artifacts:
- `tools/build_phase6_environment_probe.py`
- `tools/run_phase6_word_desktop_harness.py`
- `tools/validate_phase6_desktop_evidence.py`
- `tools/build_phase6_final_closeout.py`
- `docs/PHASE6_DESKTOP_EVIDENCE_BASELINE.md`
- `docs/PHASE6_FINAL_CLOSEOUT.md`
- `docs/ADR/0033-phase6-desktop-evidence-gate.md`
- `artifacts/phase6/desktop_validation_matrix.template.json`
- `artifacts/phase6/environment_probe.json`
- `artifacts/phase6/environment_probe.md`
- `artifacts/phase6/word_desktop_harness.json`
- `artifacts/phase6/word_desktop_harness.md`
- `artifacts/phase6/desktop_validation_summary.json`
- `artifacts/phase6/desktop_validation_summary.md`
- `artifacts/phase6/phase6_final_closeout.json`
- `artifacts/phase6/phase6_final_closeout.md`

Current Phase 6 effect:
- desktop evidence tooling is now complete and fail-closed;
- local Microsoft Word desktop create/open/edit/save behavior is proven on the current machine;
- the current machine shows a disconnected SMB mapping to Synology, with no active private-share path available;
- therefore Phase 6 is currently `blocked` on operational evidence rather than on missing code or missing validation tooling.

## Phase 7 - Cutover
Freeze legacy writes, final migration, reconciliation, web authoritative, Excel read-only/archive, rollback window.

Current Phase 7 baseline artifacts:
- `tools/build_phase7_cutover_readiness.py`
- `tools/validate_phase7_cutover_checklist.py`
- `tools/build_phase7_final_closeout.py`
- `docs/PHASE7_CUTOVER_BASELINE.md`
- `docs/PHASE7_CUTOVER_RUNBOOK.md`
- `docs/PHASE7_FINAL_CLOSEOUT.md`
- `docs/ADR/0034-cutover-readiness-is-gated-by-operational-evidence.md`
- `artifacts/phase7/cutover_execution_checklist.template.json`
- `artifacts/phase7/cutover_readiness.json`
- `artifacts/phase7/cutover_readiness.md`
- `artifacts/phase7/cutover_checklist_summary.json`
- `artifacts/phase7/cutover_checklist_summary.md`
- `artifacts/phase7/phase7_final_closeout.json`
- `artifacts/phase7/phase7_final_closeout.md`

Current Phase 7 effect:
- cutover readiness is now explicit and evidence-gated instead of assumed from prior technical baselines;
- the current cutover status is `blocked`;
- the current blocked gates are:
  - Phase 6 desktop/private-share validation
- operational cutover items such as legacy write freeze, final reconciliation sign-off, rollback contacts, and Excel archive mode remain pending.

Current Phase 7b artifacts:
- `tools/build_phase7b_operational_pack.py`
- `docs/PHASE7B_OPERATIONAL_PACK.md`
- `artifacts/phase7b/cutover_operational_pack.json`
- `artifacts/phase7b/cutover_operational_pack.csv`
- `artifacts/phase7b/cutover_operational_pack.md`

Current Phase 7b effect:
- the remaining non-code cutover items are now packaged into an operator-facing execution/evidence handoff;
- cutover preparation can continue even while Phase 6 office/private-share validation is deferred.

## Phase 8 - Application foundation
Promote the backend from a compact read-only prototype into a modular application baseline aligned to Google Cloud deployment.

Current Phase 8 artifacts:
- `backend/app/config.py`
- `backend/app/status.py`
- `backend/app/api/__init__.py`
- `backend/app/api/routers/__init__.py`
- `backend/app/api/routers/health.py`
- `backend/app/api/routers/status.py`
- `backend/app/api/routers/catalog.py`
- `backend/app/api/routers/storage.py`
- `backend/app/main.py`
- `docs/PHASE8_APPLICATION_FOUNDATION.md`
- `docs/IMPLEMENTATION_BACKLOG.md`
- `docs/ADR/0035-application-foundation-stays-cloud-run-api-first.md`

Current Phase 8 effect:
- the backend application surface is now modular instead of being concentrated in a single entrypoint;
- the app now exposes deployment-aware status for migration/cutover visibility;
- the implementation path is explicitly aligned to Google Cloud Run before broader business API and frontend work.

## Phase 9 - Authenticated read models
Add a provisional auth boundary plus entity-detail read APIs before workflow mutation endpoints.

Current Phase 9 artifacts:
- `backend/app/auth.py`
- `backend/app/services/__init__.py`
- `backend/app/services/catalog.py`
- `backend/app/read_models.py`
- `docs/PHASE9_AUTHENTICATED_READ_MODELS.md`
- `docs/ADR/0036-phase9-authenticated-read-models-before-mutations.md`

Current Phase 9 effect:
- anonymous backend reads are no longer the intended baseline;
- the application now has a replaceable auth boundary plus detail endpoints for `company`, `site`, and `case`;
- the next phase can safely move toward role-aware business APIs instead of adding mutations directly on top of anonymous reads.

## Phase 10 - Workflow mutation APIs
Start business writes with a narrow, audited case-transition API rather than broad free-form mutation.

Current Phase 10 artifacts:
- `backend/app/services/workflow.py`
- `backend/app/api/routers/workflow.py`
- `backend/app/read_models.py`
- `docs/PHASE10_WORKFLOW_MUTATION_BASELINE.md`
- `docs/ADR/0037-phase10-case-mutations-start-with-audited-state-transitions.md`
- `docs/ADR/0038-phase10-certificate-and-dkkd-mutations-keep-issue-separate-from-current-promotion.md`

Current Phase 10 effect:
- the backend now has its first explicit business mutation route;
- case lifecycle mutation is role-gated, transition-validated, and audit-first;
- stage-record mutation for `case_application`, `case_assessment`, `inspection_plan`, and `inspection_outcome` now has a controlled upsert baseline;
- inspection team mutation now has an explicit upsert baseline with atomic member-list replacement;
- certificate issuance/update/promotion now has an explicit audited baseline for both GPs certificates and DDKD;
- newly issued certificate/DDKD records remain not-current until an explicit promotion mutation is executed;
- broader change-request/document/storage writes remain intentionally deferred to later phases.

## Phase 11 - Document workflow integration
Connect document selection/generation contracts into authenticated APIs without bypassing fail-closed document safety gates.

Current Phase 11 artifacts:
- `backend/app/services/document_api.py`
- `backend/app/api/routers/document.py`
- `backend/app/read_models.py`
- `docs/PHASE11_DOCUMENT_WORKFLOW_INTEGRATION.md`
- `docs/ADR/0039-phase11-document-workflow-api-stays-run-first-and-fail-closed.md`

Current Phase 11 effect:
- the backend now exposes authenticated document workflow APIs for prepare, render, generation-run status, and logical-document detail;
- document workflow is now run-first, so `document_generation_run` persists before render and remains inspectable when a family is blocked;
- unresolved families remain fail-closed at API level instead of flowing through guessed bookmark mutation;
- the current render-safe API baseline is still intentionally narrow and evidence-based, with `DDKD_CERTIFICATE` proven on the backend path while unresolved families remain blocked.

## Phase 12 - Frontend operator shell
Build the first frontend shell on top of the API-first backend without moving workflow or storage logic into the browser.

Current Phase 12 artifacts:
- `frontend/package.json`
- `frontend/pnpm-lock.yaml`
- `frontend/tsconfig.json`
- `frontend/tsconfig.app.json`
- `frontend/tsconfig.node.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/types.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/storage.ts`
- `frontend/src/vite-env.d.ts`
- `docs/PHASE12_FRONTEND_OPERATOR_SHELL.md`
- `docs/ADR/0040-phase12-frontend-uses-vite-react-router-client-shell.md`

Current Phase 12 effect:
- the repository now has a real React + TypeScript operator shell instead of an empty `frontend/` placeholder;
- operators can inspect application status, search cases, open case detail, and drive document prepare/render/status flows from the browser shell;
- frontend document interactions stay thin and backend-owned, with blocked reasons surfaced explicitly rather than guessed around in the UI;
- local development can talk to the backend through the Vite proxy without introducing frontend-side NAS or workflow ownership.

## Phase 13 - Cloud auth productionization
Replace the provisional local-only header trust path with a Google Cloud compatible identity boundary while preserving a deliberate local/dev escape hatch.

Current Phase 13 artifacts:
- `backend/app/auth.py`
- `backend/app/config.py`
- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`
- `tests/test_phase9_authenticated_read_models.py`
- `docs/PHASE13_CLOUD_AUTH_PRODUCTIONIZATION.md`
- `docs/ADR/0041-phase13-google-cloud-auth-uses-iap-jwt-first.md`

Current Phase 13 effect:
- the backend now has a production-oriented `google_iap_jwt` auth mode that expects a signed Google Cloud IAP assertion instead of trusting browser-supplied identity/role headers;
- server-owned role mapping now sits behind configuration, so the browser no longer authors production roles;
- frontend requests now adapt to backend-reported `auth_mode`, sending stub headers only when the backend explicitly runs in `header_stub`;
- production auth now fails closed on missing audience, missing assertion, invalid domain, or missing verifier dependency instead of silently downgrading trust.

## Phase 14 - Cloud Run deployment baseline
Convert the approved Google Cloud target into an explicit runtime/deployment contract with repository-owned validation artifacts.

Current Phase 14 artifacts:
- `backend/requirements.runtime.txt`
- `backend/Dockerfile`
- `backend/.dockerignore`
- `backend/.env.cloudrun.example`
- `backend/app/config.py`
- `backend/app/main.py`
- `tools/validate_phase14_cloud_run_contract.py`
- `tests/test_phase14_cloud_run_contract.py`
- `docs/PHASE14_CLOUD_RUN_DEPLOYMENT_BASELINE.md`
- `docs/ADR/0042-phase14-cloud-run-deployment-contract-stays-explicit.md`

Current Phase 14 effect:
- the repository now contains a concrete Linux/Cloud Run backend runtime baseline rather than only architecture text;
- backend config can now compose a PostgreSQL SQLAlchemy URL from Cloud SQL-oriented env components when a full `DATABASE_URL` is not injected;
- deployment preflight can now validate auth, database, and Synology-backed storage prerequisites before rollout;
- the project is now closer to production-shaped deployment without yet locking into full IaC or CI/CD tooling.

## Phase 15 - Cloud Run service bootstrap
Turn the deployment baseline into an operator-usable service bootstrap path with explicit rollout inputs, command generation, and storage-mode gating.

Current Phase 15 artifacts:
- `infra/cloudrun/service_bootstrap.example.json`
- `infra/cloudrun/secret_bindings.example.json`
- `infra/cloudrun/deploy_backend.ps1`
- `tools/validate_phase15_service_bootstrap.py`
- `tests/test_phase15_service_bootstrap.py`
- `docs/CLOUD_RUN_OPERATIONS_RUNBOOK.md`
- `docs/PHASE15_CLOUD_RUN_SERVICE_BOOTSTRAP.md`
- `docs/ADR/0043-phase15-cloud-run-bootstrap-rejects-in-container-smb-mounts.md`

Current Phase 15 effect:
- the repository now contains a validated Cloud Run service bootstrap contract instead of ad-hoc deploy notes;
- operators can now dry-run and preview the exact `gcloud run deploy` shape before rollout;
- Secret Manager bindings and Cloud SQL linkage are now part of a checked bootstrap path rather than manual memory;
- the project now explicitly rejects unsupported in-container SMB/Tailscale mount assumptions for Cloud Run and narrows direct-storage deployment to NFS volume mounts or an external bridge path.

## Phase 16 - Storage strategy decision pack
Convert the Cloud Run storage fork into an explicit planning recommendation so later phases do not drift into a storage topology by accident.

Current Phase 16 artifacts:
- `tools/build_phase16_storage_strategy_report.py`
- `tests/test_phase16_storage_strategy_report.py`
- `docs/STORAGE_DEPLOYMENT_OPTIONS.md`
- `docs/STORAGE_BRIDGE_CONTRACT.md`
- `infra/cloudrun/service_bootstrap.external_bridge.example.json`
- `docs/PHASE16_STORAGE_STRATEGY_DECISION_PACK.md`
- `docs/ADR/0044-phase16-planning-assumption-prefers-external-bridge.md`

Current Phase 16 effect:
- the repo now distinguishes between experimental transport options and the business-visible `StorageService` contract;
- the project now has an explicit bridge contract so future storage-adapter implementation can proceed without leaking transport concerns into business services;
- the Phase 15 bootstrap validator now recognizes multiple storage connectivity modes without forcing any one of them to become the production semantic owner;
- the storage decision is now documented as an evidence-backed sequencing rule:
  - PoC A first via Cloud Run + application-level transport over Tailscale
  - PoC B only if PoC A fails
  - NFS remains experimental only

## Phase 17 - External bridge runtime baseline
Make the preferred storage strategy executable by introducing a runnable bridge client/server baseline and bridge-mode environment contract.

Current Phase 17 artifacts:
- `backend/app/storage/external_bridge.py`
- `backend/storage_bridge_main.py`
- `backend/Dockerfile.storage_bridge`
- `backend/.env.cloudrun.external_bridge.example`
- `docs/STORAGE_BRIDGE_DEPLOYMENT_RUNBOOK.md`
- `docs/PHASE17_EXTERNAL_BRIDGE_RUNTIME_BASELINE.md`
- `docs/ADR/0045-phase17-external-bridge-runtime-baseline.md`

Current Phase 17 effect:
- the main application can now construct a storage adapter for `external_bridge_http` instead of assuming only filesystem-local storage adapters;
- the repository now contains a standalone bridge HTTP runtime surface backed by the existing filesystem storage adapter;
- the external-bridge path is now represented in both deployment validation and bootstrap examples, rather than remaining documentation-only;
- the bridge runtime remains an infrastructure fallback path rather than the next mandatory deployment step.

## Phase 18 - Storage bridge non-production deployment pack
Prepare a validated, operator-usable deployment pack for a first non-production bridge rollout.

Current Phase 18 artifacts:
- `backend/.env.storage_bridge.cloudrun.example`
- `infra/cloudrun/storage_bridge_bootstrap.example.json`
- `tools/validate_phase18_storage_bridge_bootstrap.py`
- `infra/cloudrun/deploy_storage_bridge.ps1`
- `tests/test_phase18_storage_bridge_bootstrap.py`
- `docs/PHASE18_STORAGE_BRIDGE_NONPROD_DEPLOYMENT_PACK.md`
- `docs/ADR/0046-phase18-nonprod-bridge-deployment-pack.md`

Current Phase 18 effect:
- the bridge service now has its own deployment bootstrap path instead of borrowing the main app bootstrap;
- the repo can now generate both the bridge deploy command and the required `roles/run.invoker` binding command for the main app caller identity;
- the bridge env contract is now separated from the main app env contract and explicitly rejects accidental `external_bridge_http` self-loop configuration;
- the bridge deployment pack is now available if PoC A fails, but it is not the default next step.

## Phase 18a - Stabilization and hardening
Freeze new feature work temporarily and harden runtime/bootstrap/storage boundaries before Synology PoC or non-production rollout.

Current stabilization focus:
- production bootstrap fail-closed on DB/auth/storage invariants
- repository hygiene guard for private/generated content
- storage binding ownership above adapter layer
- authenticated bridge boundary plus streaming-safe IO
- Windows-only legacy tooling isolation from backend runtime imports
- compiled dependency locks and CI-backed migration/test/frontend gates
- fresh-checkout backend tests independent of production `legacy/` and `artifacts` through committed sanitized fixtures
- Python 3.12 as the single backend runtime and lock-generation baseline
- CAPA mutation/service/API baseline with single-owner certificate eligibility, authenticated assessor identity, and exact CAPA document linkage
- end-to-end optimistic-concurrency tests for `case`, `certificate`, and `capa_cycle`
- request-boundary commit semantics validated before success responses are emitted

## Quality gates
For each entity report source count, target count, dedup/excluded count, ID mapping, orphans, exceptions.

Known cleanup:
- `db.dkkd ID=385` exact duplicate -> keep one and report one dedup.
