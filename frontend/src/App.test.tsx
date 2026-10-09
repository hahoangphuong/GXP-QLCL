import "@testing-library/jest-dom/vitest";
import { useLayoutEffect } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const apiMocks = vi.hoisted(() => ({
  assessCapaCycle: vi.fn(),
  createCapaCycle: vi.fn(),
  createInspectionCase: vi.fn(),
  createChangeRequest: vi.fn(),
  createChangeRequestDetail: vi.fn(),
  issueChangeRequestBusinessEligibilitySuccessor: vi.fn(),
  issueChangeRequestCertificateSuccessor: vi.fn(),
  updateChangeRequest: vi.fn(),
  updateChangeRequestDetail: vi.fn(),
  upsertChangeApproval: vi.fn(),
  transitionChangeRequest: vi.fn(),
  getAppStatus: vi.fn(),
  getCurrentIdentity: vi.fn(),
  getAdminSystemStatus: vi.fn(),
  getDashboardSummary: vi.fn().mockResolvedValue({
    total_facilities: 18,
    total_cases: 42,
    active_cases: 12,
    waiting_inspection: 4,
    waiting_certificate_decision: 3,
    active_certificates: 9,
    expiring_certificates_90_days: 2,
    incomplete_changes: 1,
    queue: [],
  }),
  searchFacilities: vi.fn().mockResolvedValue({ items: [], total_count: 0, offset: 0, limit: 100 }),
  getFacilityWorkspace: vi.fn().mockResolvedValue(null),
  getCaseDetail: vi.fn().mockResolvedValue(null),
  getCaseWorkspace: vi.fn().mockResolvedValue(null),
  getChangeRequestWorkspace: vi.fn().mockResolvedValue(null),
  upsertCaseApplication: vi.fn(),
  upsertCaseAssessment: vi.fn(),
  upsertEvaluationScope: vi.fn(),
  upsertInspectionPlan: vi.fn(),
  upsertInspectionOutcome: vi.fn(),
  upsertInspectionPeriodSegments: vi.fn(),
  createInspectionApprovalSubmission: vi.fn(),
  completeInspectionApprovalSubmission: vi.fn(),
  transitionCase: vi.fn(),
  listSiteGxpCertificates: vi.fn().mockResolvedValue({ items: [] }),
  getGxpCertificateDetail: vi.fn().mockResolvedValue(null),
  promoteGxpCertificateCurrent: vi.fn(),
  upsertGxpCertificateLatestVersion: vi.fn(),
  issueGxpCertificate: vi.fn(),
  listSiteBusinessEligibilityCertificates: vi.fn().mockResolvedValue({ items: [], issue_readiness: null }),
  getBusinessEligibilityDetail: vi.fn().mockResolvedValue(null),
  issueBusinessEligibility: vi.fn(),
  upsertBusinessEligibilityLatestVersion: vi.fn(),
  promoteBusinessEligibilityCurrent: vi.fn(),
  getDocumentDetail: vi.fn().mockResolvedValue(null),
  openCaseDocumentCurrentContent: vi.fn().mockResolvedValue({
    blob: new Blob(["doc"]),
    contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    filename: "document.docx",
  }),
  openCapaCycleDocumentCurrentContent: vi.fn().mockResolvedValue({
    blob: new Blob(["doc"]),
    contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    filename: "document.docx",
  }),
  getGenerationRun: vi.fn().mockResolvedValue(null),
  listCases: vi.fn().mockResolvedValue([]),
  listCompanies: vi.fn().mockResolvedValue([]),
  listSites: vi.fn().mockResolvedValue([]),
  prepareDocument: vi.fn(),
  renderTemplateDocx: vi.fn(),
  submitCapaCycle: vi.fn(),
  updateCapaCycle: vi.fn(),
}));

const oidcMocks = vi.hoisted(() => ({
  loadGoogleIdentityScript: vi.fn().mockResolvedValue(undefined),
  decodeOidcCredential: vi.fn(),
  isOidcSessionValid: vi.fn(() => false),
}));

// Observe the committed DOM before SearchPage's passive request effects run.
const contextCommit = vi.hoisted(() => ({ observe: vi.fn() }));
vi.mock("./features/search/FacilityTable", async (importOriginal) => {
  const original = await importOriginal<typeof import("./features/search/FacilityTable")>();
  const { useLayoutEffect, createElement } = await import("react");
  return {
    FacilityTable: (props: Parameters<typeof original.FacilityTable>[0]) => {
      useLayoutEffect(() => { contextCommit.observe(props.selectedResultKey); });
      return createElement(original.FacilityTable, props);
    },
  };
});

vi.mock("./lib/api", () => apiMocks);
vi.mock("./lib/oidc", () => oidcMocks);
vi.mock("./lib/storage", () => ({
  loadAuthState: vi.fn(() => ({ username: "operator.local", role: "inspector" })),
  loadOidcSession: vi.fn(() => null),
  saveAuthState: vi.fn(),
  saveOidcSession: vi.fn(),
  clearOidcSession: vi.fn(),
}));

function resetApiMocks() {
  apiMocks.getAppStatus.mockReset();
  apiMocks.getCurrentIdentity.mockReset();
  apiMocks.getAdminSystemStatus.mockReset();
  apiMocks.assessCapaCycle.mockReset();
  apiMocks.createCapaCycle.mockReset();
  apiMocks.createInspectionCase.mockReset();
  apiMocks.createChangeRequest.mockReset();
  apiMocks.createChangeRequestDetail.mockReset();
  apiMocks.issueChangeRequestBusinessEligibilitySuccessor.mockReset();
  apiMocks.issueChangeRequestCertificateSuccessor.mockReset();
  apiMocks.updateChangeRequest.mockReset();
  apiMocks.updateChangeRequestDetail.mockReset();
  apiMocks.upsertChangeApproval.mockReset();
  apiMocks.transitionChangeRequest.mockReset();
  apiMocks.getDashboardSummary.mockReset();
  apiMocks.searchFacilities.mockReset();
  apiMocks.getFacilityWorkspace.mockReset();
  apiMocks.getCaseDetail.mockReset();
  apiMocks.getCaseWorkspace.mockReset();
  apiMocks.getChangeRequestWorkspace.mockReset();
  apiMocks.upsertCaseApplication.mockReset();
  apiMocks.upsertCaseAssessment.mockReset();
  apiMocks.upsertEvaluationScope.mockReset();
  apiMocks.upsertInspectionPlan.mockReset();
  apiMocks.upsertInspectionOutcome.mockReset();
  apiMocks.upsertInspectionPeriodSegments.mockReset();
  apiMocks.createInspectionApprovalSubmission.mockReset();
  apiMocks.completeInspectionApprovalSubmission.mockReset();
  apiMocks.transitionCase.mockReset();
  apiMocks.listSiteGxpCertificates.mockReset();
  apiMocks.getGxpCertificateDetail.mockReset();
  apiMocks.promoteGxpCertificateCurrent.mockReset();
  apiMocks.upsertGxpCertificateLatestVersion.mockReset();
  apiMocks.issueGxpCertificate.mockReset();
  apiMocks.listSiteBusinessEligibilityCertificates.mockReset();
  apiMocks.getBusinessEligibilityDetail.mockReset();
  apiMocks.issueBusinessEligibility.mockReset();
  apiMocks.upsertBusinessEligibilityLatestVersion.mockReset();
  apiMocks.promoteBusinessEligibilityCurrent.mockReset();
  apiMocks.getDocumentDetail.mockReset();
  apiMocks.openCaseDocumentCurrentContent.mockReset();
  apiMocks.openCapaCycleDocumentCurrentContent.mockReset();
  apiMocks.getGenerationRun.mockReset();
  apiMocks.listCases.mockReset();
  apiMocks.listCompanies.mockReset();
  apiMocks.listSites.mockReset();
  apiMocks.prepareDocument.mockReset();
  apiMocks.renderTemplateDocx.mockReset();
  apiMocks.submitCapaCycle.mockReset();
  apiMocks.updateCapaCycle.mockReset();

  apiMocks.getDashboardSummary.mockResolvedValue({
    total_facilities: 18,
    total_cases: 42,
    active_cases: 12,
    waiting_inspection: 4,
    waiting_certificate_decision: 3,
    active_certificates: 9,
    expiring_certificates_90_days: 2,
    incomplete_changes: 1,
    queue: [],
  });
  apiMocks.searchFacilities.mockResolvedValue({ items: [], total_count: 0, offset: 0, limit: 100 });
  apiMocks.getCurrentIdentity.mockResolvedValue({
    username: "operator.local",
    email: null,
    subject: null,
    role_codes: ["inspector"],
    permissions: ["case.view", "case.edit"],
  });
  apiMocks.getAdminSystemStatus.mockResolvedValue(buildStatus("header_stub", null));
  apiMocks.assessCapaCycle.mockResolvedValue(null);
  apiMocks.createCapaCycle.mockResolvedValue(null);
  apiMocks.createInspectionCase.mockResolvedValue(null);
  apiMocks.createChangeRequest.mockResolvedValue(null);
  apiMocks.createChangeRequestDetail.mockResolvedValue(null);
  apiMocks.updateChangeRequest.mockResolvedValue(null);
  apiMocks.updateChangeRequestDetail.mockResolvedValue(null);
  apiMocks.upsertChangeApproval.mockResolvedValue(null);
  apiMocks.transitionChangeRequest.mockResolvedValue(null);
  apiMocks.getFacilityWorkspace.mockResolvedValue(null);
  apiMocks.getCaseDetail.mockResolvedValue(null);
  apiMocks.getCaseWorkspace.mockResolvedValue(null);
  apiMocks.getChangeRequestWorkspace.mockResolvedValue(null);
  apiMocks.upsertCaseApplication.mockResolvedValue(null);
  apiMocks.upsertCaseAssessment.mockResolvedValue(null);
  apiMocks.upsertEvaluationScope.mockResolvedValue(null);
  apiMocks.upsertInspectionPlan.mockResolvedValue(null);
  apiMocks.upsertInspectionOutcome.mockResolvedValue(null);
  apiMocks.upsertInspectionPeriodSegments.mockResolvedValue(null);
  apiMocks.createInspectionApprovalSubmission.mockResolvedValue(null);
  apiMocks.completeInspectionApprovalSubmission.mockResolvedValue(null);
  apiMocks.transitionCase.mockResolvedValue(null);
  apiMocks.listSiteGxpCertificates.mockResolvedValue({ items: [] });
  apiMocks.getGxpCertificateDetail.mockResolvedValue(null);
  apiMocks.promoteGxpCertificateCurrent.mockResolvedValue(null);
  apiMocks.upsertGxpCertificateLatestVersion.mockResolvedValue(null);
  apiMocks.issueGxpCertificate.mockResolvedValue(null);
  apiMocks.listSiteBusinessEligibilityCertificates.mockResolvedValue({ items: [], issue_readiness: null });
  apiMocks.getBusinessEligibilityDetail.mockResolvedValue(null);
  apiMocks.issueBusinessEligibility.mockResolvedValue(null);
  apiMocks.upsertBusinessEligibilityLatestVersion.mockResolvedValue(null);
  apiMocks.promoteBusinessEligibilityCurrent.mockResolvedValue(null);
  apiMocks.getDocumentDetail.mockResolvedValue(null);
  apiMocks.openCaseDocumentCurrentContent.mockResolvedValue({
    blob: new Blob(["doc"]),
    contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    filename: "document.docx",
  });
  apiMocks.openCapaCycleDocumentCurrentContent.mockResolvedValue({
    blob: new Blob(["doc"]),
    contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    filename: "document.docx",
  });
  apiMocks.getGenerationRun.mockResolvedValue(null);
  apiMocks.listCases.mockResolvedValue([]);
  apiMocks.listCompanies.mockResolvedValue([]);
  apiMocks.listSites.mockResolvedValue([]);
  apiMocks.submitCapaCycle.mockResolvedValue(null);
  apiMocks.updateCapaCycle.mockResolvedValue(null);
}

function resetOidcMocks() {
  oidcMocks.loadGoogleIdentityScript.mockReset();
  oidcMocks.decodeOidcCredential.mockReset();
  oidcMocks.isOidcSessionValid.mockReset();

  oidcMocks.loadGoogleIdentityScript.mockResolvedValue(undefined);
  oidcMocks.isOidcSessionValid.mockImplementation(() => false);
}

function buildStatus(authMode: "header_stub" | "google_oidc", oidcClientId: string | null) {
  return {
    auth_mode: authMode,
    auth: {
      mode: authMode,
      oidc_client_id: oidcClientId,
      allowed_email_domain: "qlcl-dav.cc",
    },
    deployment_platform: "compute_engine_vm",
    frontend_topology: "nginx_static_proxy",
    deployment: {
      git_sha: "abc123",
      git_short_sha: "abc123",
      branch: "main",
      image_uri: null,
      deployed_at_utc: null,
      cloud_run_service_name: null,
      db_name: "gxp_qlcl",
      db_user: "gxp_app",
    },
    phases: {
      phase3_status: "ready",
      phase4_status: "ready",
      phase5_status: "ready",
      phase6_status: "ready",
      phase7_status: "ready",
      current_projection_conflicts_status: "ready",
      current_projection_conflicts_unresolved_count: 0,
    },
  };
}

function buildSearchResult(overrides: Record<string, unknown> = {}) {
  return {
    result_key: "site-1:GMP:A",
    site_id: "site-1",
    legacy_site_id: 101,
    facility_code: "1.1",
    context_code: "1.1A",
    result_grain: "production_line",
    gxp_type: "GMP",
    line_code: "A",
    production_line_id: "line-uuid-1",
    production_line_code: "A",
    production_line_identity_state: "canonical",
    facility_name: "Công ty cổ phần dược phẩm Trung ương I",
    company_name: "Công ty A",
    gxp_types: ["GMP"],
    certificate_scope_summary: "Dây chuyền viên nén A",
    province_name: "Hà Nội",
    last_inspection_on: "2026-08-01",
    current_state: "awaiting_certificate_decision",
    current_certificate_number: "GCN-001",
    current_certificate_expiry: "2026-12-31",
    ...overrides,
  };
}

function buildWorkspace(overrides: Record<string, unknown> = {}) {
  return {
    summary: {
      context_key: "site-1:GMP:A",
      site_id: "site-1",
      legacy_site_id: 101,
      facility_code: "1.1",
      context_code: "1.1A",
      context_grain: "production_line",
      selected_line_code: "A",
      selected_production_line_id: "line-uuid-1",
      selected_production_line_code: "A",
      production_line_identity_state: "canonical",
      facility_name: "Nhà máy A",
      company_name: "Công ty A",
      company_legal_address: "123 Trụ sở chính",
      company_leader: "Rajesh Kamat, Tổng Giám đốc",
      company_foreign_investment: "Nhật Bản",
      assigned_specialist: "Hà Hoàng Phương",
      address: "KCN A",
      contact_information: "QA: 0903 000 000",
      professional_responsible_person: "Dược sĩ A",
      quality_assurance_person: "QA Lead B",
      facility_current_status: "Cơ sở dừng hoạt động từ 31/12/2020",
      province_name: "Hà Nội",
      gxp_types: ["GMP"],
      selected_gxp_type: "GMP",
      current_state: "awaiting_certificate_decision",
      primary_standard: "WHO-GMP",
      current_certificate_number: "GCN-001",
      current_certificate_issue_date: "2026-06-01",
      current_certificate_expiry: "2026-12-31",
      current_certificate_standard: "WHO-GMP",
      current_certificate_status: "active",
      certificate_scope_summary: "Dây chuyền viên nén A",
    },
    history: [
      {
        id: "case-1",
        source_type: "case",
        reference_code: "KT-2026-GMP-A",
        event_type: "Định kỳ",
        gxp_type: "GMP",
        standard: "WHO-GMP",
        occurred_on: "2026-08-05",
        state: "awaiting_certificate_decision",
      },
      {
        id: "change-1",
        source_type: "change_request",
        reference_code: "TD-01",
        event_type: "Thay đổi cơ sở",
        gxp_type: null,
        standard: "Đổi địa chỉ",
        occurred_on: "2026-08-06",
        state: "under_review",
      },
    ],
    action_readiness: [
      {
        action_key: "create_company",
        label: "Công ty mới",
        readiness_status: "missing_contract",
        detail: "Chưa có canonical backend write contract để tạo công ty mới.",
        required_permissions: [],
      },
      {
        action_key: "create_site",
        label: "Cơ sở mới",
        readiness_status: "missing_contract",
        detail: "Chưa có canonical backend write contract để tạo cơ sở mới.",
        required_permissions: [],
      },
      {
        action_key: "create_production_line",
        label: "Dây chuyền mới",
        readiness_status: "missing_contract",
        detail: "Chưa có canonical backend write contract để tạo dây chuyền sản xuất mới.",
        required_permissions: [],
      },
      {
        action_key: "create_reassessment_case",
        label: "Tái đánh giá",
        readiness_status: "missing_contract",
        detail: "Chưa có create contract owner-safe để tạo hồ sơ tái đánh giá mới cho ngữ cảnh GMP.",
        required_permissions: [],
      },
      {
        action_key: "create_change_request",
        label: "Thay đổi",
        readiness_status: "missing_contract",
        detail: "Change request hiện mới có canonical read model; chưa có authenticated write contract để tạo mới.",
        required_permissions: [],
      },
    ],
    ...overrides,
  };
}

function buildCaseWorkspace(overrides: Record<string, unknown> = {}) {
  return {
    case_summary: {
      id: "case-1",
      row_version: 8,
      legacy_inspection_id: 1,
      legacy_inspection_code: "KT-2026-GMP-A",
      site_id: "site-1",
      facility_name: "Nhà máy A",
      company_name: "Công ty A",
      gxp_type: "GMP",
      scope_code: "A",
      applicable_standard: "WHO-GMP",
      inspection_type: "Tái",
      state: "awaiting_certificate_decision",
      opened_year: 2026,
    },
    application: {
      row_version: 4,
      submitted_on: "2026-01-15T00:00:00Z",
      dossier_code: "HS-001",
      dossier_reference: "QĐ-TN-01",
      applicant_name: "Nguyễn Văn A",
      assigned_specialist: "Hà Hoàng Phương",
      assigned_specialist_source: "company_master",
    },
    inspection: {
      plan_row_version: 3,
      plan_decision_reference: "QĐ-KT-01",
      plan_decision_date: "2026-08-01",
      decision_document_hint: null,
      plan_start_on: null,
      plan_end_on: null,
      planning_sheet_name: null,
      outcome_row_version: 6,
      inspected_on: "2026-08-05",
      inspected_to_on: "2026-08-06",
      inspection_period_state: "KNOWN",
      inspection_period_segments: [],
      inspection_period_edit_readiness: { action_key: "edit_inspection_period", label: "Sửa các đợt kiểm tra", available: true, reason_code: null, required_permissions: ["inspection.edit"], expected_version: 6, mode: "replace" },
      executed_on: "2026-08-06T09:30:00Z",
      outcome_decision_reference_compatibility: "QĐ-KT-01",
      bbkt_reference: "BBKT-01",
      outcome_result: "Đạt WHO-GMP dây chuyền A",
      team_display_text: null,
    },
    remediation: {
      cycles: [],
    },
    processing: {
      row_version: 2,
      assessed_on: "2026-08-08T00:00:00Z",
      assessor_name: "Chuyên viên B",
      assessment_result: "Đề xuất cấp chứng nhận",
      notes: null,
      events: [
        {
          event_type: "application_submitted",
          occurred_at: "2026-01-15T00:00:00Z",
          payload: "HS-001",
        },
        {
          event_type: "inspection_executed",
          occurred_at: "2026-08-06T09:30:00Z",
          payload: "QĐ-KT-01",
        },
      ],
    },
    documents: {
      items: [
        {
          checklist_key: "case:case-1:INSPECTION_QD_KT",
          label: "Quyết định kiểm tra",
          family_code: "INSPECTION_QD_KT",
          parent_scope: "case",
          parent_id: "case-1",
          status: "missing",
          document_id: null,
          document_type_code: null,
          title: null,
          original_filename: null,
          issued_on: null,
          available_variant_types: [],
          detail_available: false,
        },
        {
          checklist_key: "case:case-1:CERTIFICATE_DECISION",
          label: "Quyết định cấp CC",
          family_code: "CERTIFICATE_DECISION",
          parent_scope: "case",
          parent_id: "case-1",
          status: "available",
          document_id: "doc-cert-decision",
          document_type_code: "CERTIFICATE_DECISION",
          title: "Certificate Decision",
          original_filename: "8 qd cap cc GMP.docx",
          issued_on: "2026-08-09T00:00:00Z",
          available_variant_types: ["editable_docx"],
          detail_available: true,
        },
      ],
    },
    contextual_document_actions: [
      {
        checklist_key: "case:case-1:INSPECTION_QD_KT",
        label: "Quyết định kiểm tra",
        family_code: "INSPECTION_QD_KT",
        workflow_step: "Kiểm tra",
        parent_scope: "case",
        parent_id: "case-1",
        status: "missing",
        document_id: null,
        document_type_code: null,
        title: null,
        original_filename: null,
        issued_on: null,
        available_variant_types: [],
        detail_available: false,
        actions: [
          { action_key: "open", label: "Mở", available: false, disabled_reason: "Chưa có tài liệu để mở.", required_permissions: ["document.read"] },
          { action_key: "create", label: "Tạo", available: false, disabled_reason: "Thiếu contract input nghiệp vụ typed theo ngữ cảnh; không hiển thị thao tác tạo generic.", required_permissions: ["document.write"] },
          { action_key: "history", label: "Lịch sử", available: false, disabled_reason: "Chưa có lịch sử tài liệu để xem.", required_permissions: ["document.read"] },
        ],
      },
      {
        checklist_key: "case:case-1:CERTIFICATE_DECISION",
        label: "Quyết định cấp CC",
        family_code: "CERTIFICATE_DECISION",
        workflow_step: "Xử lý",
        parent_scope: "case",
        parent_id: "case-1",
        status: "available",
        document_id: "doc-cert-decision",
        document_type_code: "CERTIFICATE_DECISION",
        title: "Certificate Decision",
        original_filename: "8 qd cap cc GMP.docx",
        issued_on: "2026-08-09T00:00:00Z",
        available_variant_types: ["editable_docx"],
        detail_available: true,
        actions: [
          { action_key: "open", label: "Mở", available: true, disabled_reason: null, required_permissions: ["document.read"] },
          { action_key: "create", label: "Tạo", available: false, disabled_reason: "Thiếu contract input nghiệp vụ typed theo ngữ cảnh; không hiển thị thao tác tạo generic.", required_permissions: ["document.write"] },
          { action_key: "history", label: "Lịch sử", available: true, disabled_reason: null, required_permissions: ["document.read"] },
        ],
      },
    ],
    linked_gxp_certificates: [
      {
        certificate_id: "cert-a-new",
        site_id: "site-1",
        case_id: "case-1",
        certificate_type: "GMP",
        line_code: "A",
        issuance_basis: "inspection_case",
        latest_flag: true,
        certificate_number: "195/GCN-QLD",
        issue_date: "2025-04-17",
        expiry_date: "2027-04-17",
        applicable_standard: "WHO-GMP",
        issuing_authority: "Cục Quản lý Dược Việt Nam",
        status: "active",
        facility_name: "Nhà máy A",
        address: "KCN A",
        company_name: "Công ty A",
        company_legal_address: "123 Trụ sở chính",
        scope_summary: "Thuốc không vô trùng",
        limitation_text: null,
        source_description: "Đợt kiểm tra GMP ngày 10-01-2025",
      },
    ],
    linked_business_eligibility_certificates: [],
    ...overrides,
  };
}

function buildRemediationCycle(overrides: Record<string, unknown> = {}) {
  return {
    capa_cycle_id: "capa-1",
    row_version: 1,
    round_no: 1,
    requested_on: "2026-08-07",
    submitted_on: null,
    assessed_on: null,
    assessor_name: null,
    result: null,
    status: "requested",
    notes: "Thiếu bằng chứng vệ sinh",
    ...overrides,
  };
}

function buildCapaAction(
  action_key: string,
  available: boolean,
  options: { expected_version?: number | null; reason_code?: string | null; required_permissions?: string[] } = {},
) {
  return {
    action_key,
    label: action_key,
    available,
    reason_code: available ? null : options.reason_code ?? "missing_permission",
    required_permissions: options.required_permissions ?? [action_key === "assess_capa_cycle" ? "capa.assess" : "capa.edit"],
    expected_version: options.expected_version ?? null,
  };
}

function buildCapaActions(...actions: ReturnType<typeof buildCapaAction>[]) {
  return actions;
}

function buildChangeRequestWorkspace(overrides: Record<string, unknown> = {}) {
  return {
    id: "change-1",
    row_version: 4,
    legacy_change_request_id: 1,
    site_id: "site-1",
    facility_name: "Nhà máy A",
    company_name: "Công ty A",
    scope_label: "Đổi địa chỉ",
    description: "Điều chỉnh địa chỉ kho bảo quản",
    submitted_on: "2026-08-06",
    requester_name: "Phòng QA",
    state: "under_review",
    handled_on: "2026-08-07",
    handled_by_name: "Hà Hoàng Phương",
    result_label: "Đang thẩm tra hồ sơ thay đổi",
    effective_on: null,
    approval_reference: null,
    affected_artifacts: [
      {
        link_id: "affected-cert-1",
        artifact_kind: "certificate",
        artifact_id: "cert-current-1",
        source_affected_artifact_id: null,
      },
      {
        link_id: "affected-dkkd-1",
        artifact_kind: "business_eligibility_certificate",
        artifact_id: "dkkd-current-1",
        source_affected_artifact_id: null,
      },
    ],
    issued_artifacts: [
      {
        link_id: "issued-cert-1",
        artifact_kind: "certificate",
        artifact_id: "cert-successor-1",
        source_affected_artifact_id: "affected-cert-1",
      },
      {
        link_id: "issued-dkkd-1",
        artifact_kind: "business_eligibility_certificate",
        artifact_id: "dkkd-successor-1",
        source_affected_artifact_id: "affected-dkkd-1",
      },
    ],
    documents: {
      items: [
        {
          checklist_key: "change_request:change-1:NAME_ADDRESS_CHANGE_LETTER",
          label: "Đổi tên, địa chỉ",
          family_code: "NAME_ADDRESS_CHANGE_LETTER",
          parent_scope: "change_request",
          parent_id: "change-1",
          status: "available",
          document_id: "doc-change-1",
          document_type_code: "NAME_ADDRESS_CHANGE_LETTER",
          title: "Đổi tên, địa chỉ",
          original_filename: "doi-ten-dia-chi.docx",
          issued_on: "2026-08-08T00:00:00Z",
          available_variant_types: ["editable_docx"],
          detail_available: true,
        },
        {
          checklist_key: "change_request:change-1:CONSENT_CHANGE_LETTER",
          label: "CV đồng ý thay đổi",
          family_code: "CONSENT_CHANGE_LETTER",
          parent_scope: "change_request",
          parent_id: "change-1",
          status: "missing",
          document_id: null,
          document_type_code: null,
          title: null,
          original_filename: null,
          issued_on: null,
          available_variant_types: [],
          detail_available: false,
        },
      ],
    },
    details: [
      {
        change_detail_id: "change-detail-1",
        legacy_change_detail_id: 101,
        classification_id: 1,
        classification_label: "Đổi địa chỉ",
        approval_status: null,
        old_value: "Địa chỉ cũ",
        new_value: "Địa chỉ mới",
        note: null,
      },
    ],
    action_readiness: [
      { action_key: "edit_change_request", label: "Sửa đề nghị", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 4, target_state: null },
      { action_key: "add_change_detail", label: "Thêm chi tiết", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 4, target_state: null },
      { action_key: "edit_change_detail", label: "Sửa chi tiết", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 4, target_state: null },
      { action_key: "edit_change_approval", label: "Cập nhật xử lý", available: true, reason_code: null, required_permissions: ["change_request.approve"], expected_version: 4, target_state: null },
      { action_key: "issue_certificate_successor:affected-cert-1", label: "Tạo GCN điều chỉnh", available: true, reason_code: null, required_permissions: ["change_request.edit", "certificate.issue"], expected_version: 4, target_state: null, source_affected_artifact_id: "affected-cert-1" },
      { action_key: "issue_business_eligibility_successor:affected-dkkd-1", label: "Tạo GCN ĐĐK điều chỉnh", available: true, reason_code: null, required_permissions: ["change_request.edit", "certificate.issue"], expected_version: 4, target_state: null, source_affected_artifact_id: "affected-dkkd-1" },
      { action_key: "edit_issued_certificate:issued-cert-1", label: "Cập nhật chứng nhận", available: true, reason_code: null, required_permissions: ["certificate.edit"], expected_version: 11, target_state: null, source_affected_artifact_id: "affected-cert-1", issued_artifact_link_id: "issued-cert-1", target_artifact_kind: "certificate", target_artifact_id: "cert-successor-1" },
      { action_key: "promote_issued_certificate:issued-cert-1", label: "Đặt làm chứng nhận hiện hành", available: true, reason_code: null, required_permissions: ["certificate.approve"], expected_version: 11, target_state: null, source_affected_artifact_id: "affected-cert-1", issued_artifact_link_id: "issued-cert-1", target_artifact_kind: "certificate", target_artifact_id: "cert-successor-1" },
      { action_key: "edit_issued_business_eligibility:issued-dkkd-1", label: "Cập nhật GCN đủ điều kiện", available: true, reason_code: null, required_permissions: ["certificate.edit"], expected_version: 13, target_state: null, source_affected_artifact_id: "affected-dkkd-1", issued_artifact_link_id: "issued-dkkd-1", target_artifact_kind: "business_eligibility_certificate", target_artifact_id: "dkkd-successor-1" },
      { action_key: "promote_issued_business_eligibility:issued-dkkd-1", label: "Đặt làm GCN đủ điều kiện hiện hành", available: true, reason_code: null, required_permissions: ["certificate.approve"], expected_version: 13, target_state: null, source_affected_artifact_id: "affected-dkkd-1", issued_artifact_link_id: "issued-dkkd-1", target_artifact_kind: "business_eligibility_certificate", target_artifact_id: "dkkd-successor-1" },
      { action_key: "transition_change_request:accepted", label: "Chấp nhận", available: true, reason_code: null, required_permissions: ["change_request.approve"], expected_version: 4, target_state: "accepted" },
      { action_key: "transition_change_request:rejected", label: "Từ chối", available: true, reason_code: null, required_permissions: ["change_request.approve"], expected_version: 4, target_state: "rejected" },
    ],
    ...overrides,
  };
}

function buildApiError(message: string, status: number) {
  const error = new Error(message) as Error & { status: number };
  error.status = status;
  return error;
}

function renderApp(initialEntries: string[] = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <App />
    </MemoryRouter>,
  );
}

function SearchRouteNavigator({ to }: { to: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  return <>
    <button onClick={() => navigate(to)} type="button">Đi tới ngữ cảnh khác</button>
    <button onClick={() => navigate(-1)} type="button">Quay lại ngữ cảnh trước</button>
    <button onClick={() => navigate(1)} type="button">Tới ngữ cảnh tiếp theo</button>
    <output data-testid="route-location">{location.search}</output>
  </>;
}

function NavigateOnInitialHistoryCommit({ to }: { to: string }) {
  const navigate = useNavigate();
  useLayoutEffect(() => {
    let navigated = false;
    contextCommit.observe.mockImplementation(() => {
      if (!navigated && document.querySelector(".history-table")) {
        navigated = true;
        navigate(to);
      }
    });
    return () => { contextCommit.observe.mockReset(); };
  }, [navigate, to]);
  return null;
}

describe("App Slice A.4 search workspace", () => {
  beforeEach(() => {
    contextCommit.observe.mockReset();
    resetApiMocks();
    resetOidcMocks();
    window.google = {
      accounts: {
        id: {
          initialize: vi.fn(),
          renderButton: vi.fn(),
          prompt: vi.fn(),
          disableAutoSelect: vi.fn(),
        },
      },
    };
    URL.createObjectURL = vi.fn(() => "blob:document-preview");
    URL.revokeObjectURL = vi.fn();
    window.open = vi.fn();
  });

  it("renders the compact authenticated logo header without public legal chrome", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    const { container } = renderApp();

    expect(await screen.findByRole("img", { name: "GXP QLCL" })).toHaveAttribute("src", "/gxp-qlcl-logo.png");
    expect(screen.queryByText("GxP QLCL")).not.toBeInTheDocument();
    expect(screen.queryByText("Tra cứu và điều phối nghiệp vụ")).not.toBeInTheDocument();
    expect(screen.getByText("operator.local (inspector)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đăng xuất" })).toBeInTheDocument();
    expect(screen.getByText("Quản lý GxP")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở sản xuất, kinh doanh dược phẩm")).toBeInTheDocument();
    expect(container.querySelector(".header-brand-group")).not.toBeNull();
    expect(container.querySelector(".header-identity-group")).not.toBeNull();
    expect(container.querySelector(".primary-nav")).not.toBeNull();
    expect(container.querySelector(".topbar > .header-brand-group")).not.toBeNull();
    expect(container.querySelector(".topbar > .primary-nav")).not.toBeNull();
    expect(container.querySelector(".topbar > .header-identity-group")).not.toBeNull();
    await waitFor(() => expect(screen.queryByRole("navigation", { name: "Liên kết pháp lý công khai" })).not.toBeInTheDocument());
  });

  it("uses backend identity permissions, not local role state, for admin navigation", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.getCurrentIdentity.mockResolvedValue({
      username: "manager.local",
      email: null,
      subject: null,
      role_codes: ["manager"],
      permissions: ["case.view", "certificate.approve"],
    });

    renderApp();

    await waitFor(() => expect(apiMocks.getCurrentIdentity).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: "Quản trị" })).not.toBeInTheDocument();
  });

  it("does not advertise global workflow, document, or report screens without an owner-backed contract", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    renderApp();

    await waitFor(() => expect(apiMocks.getCurrentIdentity).toHaveBeenCalled());

    const navigation = screen.getByRole("navigation", { name: "Điều hướng chính" });
    expect(within(navigation).getByRole("link", { name: "Tổng quan" })).toHaveAttribute("href", "/");
    expect(within(navigation).getByRole("link", { name: "Tra cứu" })).toHaveAttribute("href", "/search");
    expect(within(navigation).queryByRole("link", { name: "Nghiệp vụ" })).not.toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: "Tài liệu" })).not.toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: "Báo cáo" })).not.toBeInTheDocument();
  });

  it("shows protected system status only after backend confirms the admin permission", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.getCurrentIdentity.mockResolvedValue({
      username: "admin.local",
      email: null,
      subject: null,
      role_codes: ["admin"],
      permissions: ["admin.users", "admin.roles"],
    });

    renderApp(["/admin/system-status"]);

    expect(await screen.findByRole("link", { name: "Quản trị" })).toHaveAttribute("href", "/admin/system-status");
    expect(await screen.findByRole("heading", { name: "Trạng thái hệ thống" })).toBeInTheDocument();
    expect(apiMocks.getAdminSystemStatus).toHaveBeenCalled();
  });

  it("renders the privacy page publicly without login and keeps legal navigation available", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("google_oidc", "client-id.apps.googleusercontent.com"));

    const { container } = renderApp(["/privacy"]);

    expect(await screen.findByRole("heading", { name: "GXP QLCL Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText("Chính sách bảo mật GXP QLCL")).toBeInTheDocument();
    expect(screen.getAllByText("30 August 2026 / 30/08/2026").length).toBeGreaterThan(0);
    const legalFooterNav = screen.getByRole("navigation", { name: "Legal page navigation" });
    expect(within(legalFooterNav).getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(within(legalFooterNav).getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
    expect(within(legalFooterNav).getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms");
    expect(container.querySelector(".legal-page-scroll")).not.toBeNull();
    expect(apiMocks.getDashboardSummary).not.toHaveBeenCalled();
    expect(apiMocks.searchFacilities).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(document.title).toContain("GXP QLCL Privacy Policy");
    });
  });

  it("renders the terms page publicly without login and sets the legal title", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("google_oidc", "client-id.apps.googleusercontent.com"));

    renderApp(["/terms"]);

    expect(await screen.findByRole("heading", { name: "GXP QLCL Terms of Service" })).toBeInTheDocument();
    expect(screen.getByText("Điều khoản sử dụng GXP QLCL")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Legal page navigation" })).toBeInTheDocument();
    expect(apiMocks.getDashboardSummary).not.toHaveBeenCalled();
    expect(apiMocks.searchFacilities).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(document.title).toContain("GXP QLCL Terms of Service");
    });
  });

  it("still renders privacy publicly when getAppStatus rejects", async () => {
    apiMocks.getAppStatus.mockRejectedValue(new Error("status unavailable"));

    renderApp(["/privacy"]);

    expect(await screen.findByRole("heading", { name: "GXP QLCL Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText("Chính sách bảo mật GXP QLCL")).toBeInTheDocument();
    expect(screen.queryByText("status unavailable")).not.toBeInTheDocument();
  });

  it("still renders terms publicly when getAppStatus rejects", async () => {
    apiMocks.getAppStatus.mockRejectedValue(new Error("status unavailable"));

    renderApp(["/terms"]);

    expect(await screen.findByRole("heading", { name: "GXP QLCL Terms of Service" })).toBeInTheDocument();
    expect(screen.getByText("Điều khoản sử dụng GXP QLCL")).toBeInTheDocument();
    expect(screen.queryByText("status unavailable")).not.toBeInTheDocument();
  });

  it("restores the previous document title when leaving a legal page", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp(["/privacy"]);

    const legalFooterNav = await screen.findByRole("navigation", { name: "Legal page navigation" });
    await waitFor(() => {
      expect(document.title).toContain("GXP QLCL Privacy Policy");
    });

    fireEvent.click(within(legalFooterNav).getByRole("link", { name: "Home" }));

    expect(await screen.findByText("Bảng điều phối nghiệp vụ")).toBeInTheDocument();
    await waitFor(() => {
      expect(document.title).toBe("GxP Web Operator Shell");
    });
  });

  it("prompts sign-in instead of loading search data in google_oidc mode without session", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("google_oidc", null));

    renderApp(["/search"]);

    expect(await screen.findByText("Cần đăng nhập")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).not.toHaveBeenCalled();
  });

  it("renders the compact result workspace with only three direct filters and a dedicated action card", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult({ result_key: "site-1:GMP:canonical:line-p2", production_line_id: "line-uuid-2", production_line_code: "A", line_code: "A" })], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [{ id: "case-2", source_type: "case", title: "Case two", occurred_on: "2026-01-02", state: "planned" }] }));
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    expect((await screen.findAllByText("1.1A")).length).toBeGreaterThan(0);
    expect(screen.getByRole("textbox", { name: "Tên cơ sở" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Phạm vi" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Trạng thái hồ sơ" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Tỉnh/thành" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Chứng nhận" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Xử lý" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Cơ sở/dây chuyền" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xóa lọc" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Đã tải \d+ \/ \d+/)).not.toBeInTheDocument();
    const tableHead = container.querySelector(".facility-table thead") as HTMLElement;
    expect(container.querySelector(".search-page-header")).toBeNull();
    expect(screen.getByRole("navigation", { name: "Điều hướng chính" })).toBeInTheDocument();
    const gxpRail = container.querySelector(".facility-gxp-rail") as HTMLElement;
    expect(within(gxpRail).getAllByRole("tab").map((item) => item.textContent)).toEqual(["GMP", "GLP", "GMPbb"]);
    expect(within(gxpRail).queryByRole("tab", { name: "Tất cả" })).not.toBeInTheDocument();
    expect(within(gxpRail).getByRole("tab", { name: "GMP" })).toHaveAttribute("aria-selected", "true");
    expect(within(tableHead).getByRole("textbox", { name: "Tên cơ sở" })).toBeInTheDocument();
    expect(within(tableHead).getByRole("textbox", { name: "Phạm vi" })).toBeInTheDocument();
    expect(within(tableHead).queryByRole("combobox", { name: "Trạng thái hồ sơ" })).not.toBeInTheDocument();
    expect(within(tableHead).getByRole("columnheader", { name: "Trạng thái gần nhất" })).toBeInTheDocument();
    expect(tableHead.querySelectorAll("tr")).toHaveLength(1);
    expect(await screen.findByRole("button", { name: "Công ty mới" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hồ sơ kiểm tra" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dây chuyền mới" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "D.chuyền mới" })).not.toBeInTheDocument();
    for (const label of ["Công ty mới", "Cơ sở mới", "Dây chuyền mới", "Tái đánh giá", "Thay đổi"]) {
      expect(screen.getByRole("button", { name: label })).toBeDisabled();
    }
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toHaveAttribute(
        "title",
        "Chưa có create contract owner-safe để tạo hồ sơ tái đánh giá mới cho ngữ cảnh GMP.",
      );
    });
    expect(screen.queryByText(/^Prev$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Next$/)).not.toBeInTheDocument();
    expect(container.querySelector(".search-toolbar")).toBeNull();
    expect(container.querySelector(".search-master-history > .history-panel")).not.toBeNull();
    expect(container.querySelector(".facility-workspace-panel .history-panel")).toBeNull();
    expect(container.querySelectorAll(".history-table")).toHaveLength(1);
    expect(container.querySelector(".event-workspace > .panel-header")).toBeNull();
    expect(container.querySelectorAll(".facility-context-facts .status-badge")).toHaveLength(1);
    expect(container.querySelector(".facility-context-code")).not.toBeNull();
  }, 10000);

  it("keeps the inspection and certificate scopes as one permanent sibling context for every case step", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        evaluation_scope: {
          id: "scope-1",
          row_version: 1,
          source_classification: "STRUCTURED_VALID",
          rendered_prose: null,
          summary_text: "Phạm vi đánh giá canonical của đợt kiểm tra A",
          summary_source: "canonical_projection",
          limitation_text: null,
          editable: false,
          read_only_reason: null,
          taxonomy_version_id: "taxonomy-1",
          gxp_type: "GMP",
          blocks: [],
          taxonomy_nodes: [],
        },
      }),
    );

    const { container } = renderApp(["/search"]);

    expect(await screen.findByRole("heading", { name: "Phạm vi đánh giá" })).toBeInTheDocument();
    expect(screen.getByText("Phạm vi đánh giá canonical của đợt kiểm tra A")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Phạm vi chứng nhận GPs" })).toBeInTheDocument();
    expect(screen.getByText("Thuốc không vô trùng")).toBeInTheDocument();
    expect(container.querySelector(".event-scope-context .scope-information-grid")).not.toBeNull();
    expect(container.querySelector(".inspection-workspace .scope-information-grid")).toBeNull();
    expect(container.querySelector(".event-workspace-body.has-scope-context > .event-step-content + .event-scope-context")).not.toBeNull();
    expect(container.querySelectorAll(".workflow-stepper")).toHaveLength(1);

    for (const step of ["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Chứng nhận GxP", "Chứng nhận ĐĐK"]) {
      fireEvent.click(screen.getByRole("button", { name: step }));
      expect(screen.getByRole("button", { name: step })).toHaveClass("active");
      expect(screen.getAllByRole("heading", { name: "Phạm vi đánh giá" })).toHaveLength(1);
      expect(screen.getAllByRole("heading", { name: "Phạm vi chứng nhận GPs" })).toHaveLength(1);
    }

    fireEvent.click(screen.getByRole("button", { name: "Kiểm tra" }));
    expect(container.querySelector(".inspection-workspace .inspection-detail-grid")).not.toBeNull();
  });

  it("keeps unavailable evaluation and certificate scopes empty instead of copying either value", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        evaluation_scope: {
          id: null,
          row_version: null,
          source_classification: null,
          rendered_prose: null,
          summary_text: null,
          summary_source: null,
          limitation_text: null,
          editable: false,
          read_only_reason: "Chưa có phạm vi đánh giá canonical cho hồ sơ này.",
          taxonomy_version_id: null,
          gxp_type: "GMP",
          blocks: [],
          taxonomy_nodes: [],
        },
        linked_gxp_certificates: [{ ...buildCaseWorkspace().linked_gxp_certificates[0], scope_summary: null }],
      }),
    );

    renderApp(["/search"]);

    await screen.findByRole("button", { name: "Kiểm tra" });
    fireEvent.click(screen.getByRole("button", { name: "Kiểm tra" }));

    expect(await screen.findByText("Chưa có nội dung phạm vi đánh giá để hiển thị.")).toBeInTheDocument();
    expect(screen.getByText("Chưa có phạm vi chứng nhận GPs canonical liên kết trực tiếp với hồ sơ này.")).toBeInTheDocument();
  });

  it("enables only Tái đánh giá when backend readiness says available and keeps other actions disabled", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(
      buildWorkspace({
        action_readiness: buildWorkspace().action_readiness.map((item) =>
          item.action_key === "create_reassessment_case"
            ? {
                ...item,
                readiness_status: "available",
                detail: "Có thể tạo hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
                required_permissions: ["case.edit"],
              }
            : item,
        ),
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    renderApp(["/search"]);

    expect((await screen.findAllByText("1.1A")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    expect(screen.getByRole("button", { name: "Công ty mới" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cơ sở mới" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Dây chuyền mới" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Thay đổi" })).toBeDisabled();
  });

  it("opens the reassessment dialog with selected context, closes on cancel, and keeps the action rail button-only", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(
      buildWorkspace({
        action_readiness: buildWorkspace().action_readiness.map((item) =>
          item.action_key === "create_reassessment_case"
              ? {
                  ...item,
                  readiness_status: "available",
                  detail: "Có thể tạo hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
                  required_permissions: ["case.edit"],
                }
              : item,
        ),
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    expect((await screen.findAllByText("1.1A")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));

    const dialog = await screen.findByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" });
    expect(within(dialog).getByText("Công ty cổ phần dược phẩm Trung ương I")).toBeInTheDocument();
    expect(within(dialog).getByText("GMP")).toBeInTheDocument();
    expect(within(dialog).getByText("A")).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "Tiêu chuẩn áp dụng" })).toHaveFocus();
    expect(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Hủy" })).toBeInTheDocument();
    expect(container.querySelector(".search-context-actions .create-inspection-case-panel")).toBeNull();

    fireEvent.click(within(dialog).getByRole("button", { name: "Hủy" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Tái đánh giá" })).toHaveFocus();
  });

  it("creates a reassessment case without refetching search and refreshes workspace/history to the new case", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult({ result_key: "site-1:GMP:canonical:line-p2", production_line_id: "line-uuid-2", production_line_code: "A", line_code: "A" })], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace
      .mockResolvedValueOnce(
        buildWorkspace({
          action_readiness: buildWorkspace().action_readiness.map((item) =>
            item.action_key === "create_reassessment_case"
              ? {
                  ...item,
                  readiness_status: "available",
                  detail: "Có thể tạo hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
                  required_permissions: ["case.edit"],
                }
              : item,
          ),
        }),
      )
      .mockResolvedValueOnce(
        buildWorkspace({
          history: [
            {
                id: "case-new",
                source_type: "case",
                reference_code: null,
                event_type: "Tái",
                gxp_type: "GMP",
                standard: "WHO-GMP",
                occurred_on: null,
              state: "draft",
            },
            ...buildWorkspace().history,
          ],
          action_readiness: buildWorkspace().action_readiness.map((item) =>
            item.action_key === "create_reassessment_case"
              ? {
                  ...item,
                  readiness_status: "conflict",
                  detail: "Đã có một hồ sơ tái đánh giá chưa kết thúc cho đúng cơ sở/GxP/dây chuyền này.",
                  required_permissions: ["case.edit"],
                }
              : item,
          ),
        }),
      );
    apiMocks.createInspectionCase.mockResolvedValue({
      case_id: "case-new",
      site_id: "site-1",
      gxp_type: "GMP",
      line_code: "A",
      inspection_type: "Tái",
      applicable_standard: "WHO-GMP",
      state: "draft",
      row_version: 1,
      legacy_inspection_id: null,
      legacy_inspection_code: null,
      audit_event_id: "audit-1",
    });
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(buildCaseWorkspace())
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          case_summary: {
            ...buildCaseWorkspace().case_summary,
            id: "case-new",
            legacy_inspection_id: null,
            legacy_inspection_code: null,
            state: "draft",
          },
          application: {
            ...buildCaseWorkspace().application,
            dossier_code: null,
          },
        }),
      );

    const { container } = renderApp(["/search"]);

    expect((await screen.findAllByText("1.1A")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    const createAction = screen.getByRole("button", { name: "Tái đánh giá" });
    fireEvent.click(createAction);

    const dialog = await screen.findByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Tiêu chuẩn áp dụng" }), { target: { value: "WHO-GMP" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" }));

    await waitFor(() => {
      expect(apiMocks.createInspectionCase).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.createInspectionCase).toHaveBeenCalledWith(
      "site-1",
      {
        gxp_type: "GMP",
        line_code: "A",
        production_line_id: "line-uuid-2",
        applicable_standard: "WHO-GMP",
        source_case_id: "case-1",
      },
      expect.objectContaining({
        username: "operator.local",
        role: "inspector",
      }),
      true,
      null,
    );
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-uuid-2");
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" })).not.toBeInTheDocument();
    });
    expect(await screen.findByRole("heading", { name: "Thông tin hồ sơ" })).toBeInTheDocument();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("keeps the reassessment dialog open while submit is pending and allows escape close when idle", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult({ result_key: "site-1:GMP:canonical:line-p2", production_line_id: "line-uuid-2", production_line_code: "A", line_code: "A" })], total_count: 1, offset: 0, limit: 100 });
    const reassessmentReadyWorkspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "create_reassessment_case"
          ? {
              ...item,
              readiness_status: "available",
              detail: "Có thể tạo hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
              required_permissions: ["case.edit"],
            }
          : item,
      ),
    });
    apiMocks.getFacilityWorkspace
      .mockResolvedValueOnce(reassessmentReadyWorkspace)
      .mockResolvedValueOnce(reassessmentReadyWorkspace);
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    let releaseCreate: () => void = () => {};
    apiMocks.createInspectionCase.mockImplementation(
      () =>
        new Promise((resolve) => {
          releaseCreate = () =>
            resolve({
              case_id: "case-pending",
              site_id: "site-1",
              gxp_type: "GMP",
              line_code: "A",
              inspection_type: "Tái",
              applicable_standard: null,
              state: "draft",
              row_version: 1,
              legacy_inspection_id: null,
              legacy_inspection_code: null,
              audit_event_id: "audit-pending",
            });
        }),
    );

    renderApp(["/search"]);

    expect((await screen.findAllByText("1.1A")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));
    let dialog = await screen.findByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" }));

    await waitFor(() => {
      expect(within(screen.getByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" })).getByRole("button", { name: "Đang tạo..." })).toBeDisabled();
    });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" })).toBeInTheDocument();

     releaseCreate();
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" })).not.toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));
    dialog = await screen.findByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" });
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Tái đánh giá" })).toHaveFocus();
  });

  it("shows backend 409 conflict for reassessment create clearly and keeps selected facility intact", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(
      buildWorkspace({
        action_readiness: buildWorkspace().action_readiness.map((item) =>
          item.action_key === "create_reassessment_case"
            ? {
                ...item,
                readiness_status: "available",
                detail: "Có thể tạo hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
                required_permissions: ["case.edit"],
              }
            : item,
        ),
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.createInspectionCase.mockRejectedValue(new Error("An open inspection case already exists for the selected facility/GxP/line context."));

    renderApp(["/search"]);

    expect((await screen.findAllByText("1.1A")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));
    const dialog = await screen.findByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "An open inspection case already exists for the selected facility/GxP/line context.",
    );
    expect(screen.getByRole("dialog", { name: "Tạo hồ sơ tái đánh giá" })).toBeInTheDocument();
    expect(screen.getAllByText("1.1A").length).toBeGreaterThan(0);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("uses the canonical GMPbb value in the vertical result rail", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({
      items: [
        buildSearchResult({
          result_key: "site-gmpbb:GMPbb:",
          gxp_type: "GMPbb",
          context_code: "88.1",
          facility_name: "Nhà máy GMPbb",
          certificate_scope_summary: "Bao bì vô trùng",
        }),
      ],
      total_count: 1,
      offset: 0,
      limit: 100,
    });
    apiMocks.getFacilityWorkspace.mockResolvedValue(
      buildWorkspace({
        summary: {
          ...buildWorkspace().summary,
          selected_gxp_type: "GMPbb",
        },
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(null);

    renderApp(["/search?gxp_type=GMPbb"]);

    expect(await screen.findByText("Nhà máy GMPbb")).toBeInTheDocument();
    expect(apiMocks.searchFacilities.mock.calls[0][0].gxp_type).toBe("GMPbb");
    expect(screen.getByRole("tab", { name: "GMPbb" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("columnheader", { name: "GxP" })).not.toBeInTheDocument();
  });

  it("keeps the default GMP result rail while hiding the redundant GxP column", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);

    renderApp(["/search"]);

    expect(await screen.findByRole("tab", { name: "GMP" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("columnheader", { name: "GxP" })).not.toBeInTheDocument();
  });

  it("formats result and history dates as dd-mm-yyyy and keeps selected rows highlighted in the workspace", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(
      buildWorkspace({
        history: [
          {
            ...buildWorkspace().history[0],
            state: "inspection_completed",
          },
          { ...buildWorkspace().history[1], event_type: "Tái + Mới" },
        ],
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("01-08-2026")).toBeInTheDocument();
    await screen.findByRole("table", { name: "Lịch sử kiểm tra & thay đổi" });
    const historyTable = container.querySelector(".history-table");
    expect(screen.getByText("05-08-2026")).toBeInTheDocument();
    expect(within(historyTable as HTMLElement).getByRole("columnheader", { name: "Loại" })).toBeInTheDocument();
    expect(within(historyTable as HTMLElement).getByText("Tái + Mới")).toBeInTheDocument();
    expect(within(historyTable as HTMLElement).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Loại",
      "Tiêu chuẩn",
      "Ngày",
      "Trạng thái",
    ]);
    expect(within(historyTable as HTMLElement).getByText("Đã hoàn tất kiểm tra")).toBeInTheDocument();
    expect(historyTable?.querySelector("tbody tr")?.querySelectorAll("td")).toHaveLength(4);
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Thông tin chung" }));
    expect(await screen.findByText("01-06-2026")).toBeInTheDocument();
    expect(screen.getByText("31-12-2026")).toBeInTheDocument();
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
  });

  it("renders three grouped sections in Thông tin chung with imported general info values from canonical owner fields", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(
      buildWorkspace({
        summary: {
          ...buildWorkspace().summary,
          company_legal_address: "456 Trụ sở công ty",
          current_certificate_number: "GCN-789",
          current_certificate_issue_date: "2026-03-15",
          current_certificate_expiry: "2027-03-15",
          current_certificate_standard: "PIC/S-GMP",
          current_certificate_status: "active",
          certificate_scope_summary: "Dây chuyền thuốc nước",
        },
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(null);

    renderApp(["/search?facility_tab=Thông%20tin%20chung"]);

    expect(await screen.findByRole("heading", { name: "Thông tin về công ty" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thông tin về cơ sở" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thông tin về GxP" })).toBeInTheDocument();
    expect(screen.getByText("Công ty A")).toBeInTheDocument();
    expect(screen.getByText("456 Trụ sở công ty")).toBeInTheDocument();
    expect(screen.getByText("Rajesh Kamat, Tổng Giám đốc")).toBeInTheDocument();
    expect(screen.getByText("Nhật Bản")).toBeInTheDocument();
    expect(screen.getByText("Hà Hoàng Phương")).toBeInTheDocument();
    expect(screen.getAllByText("Nhà máy A").length).toBeGreaterThan(0);
    expect(screen.getAllByText("KCN A").length).toBeGreaterThan(0);
    expect(screen.getByText("QA: 0903 000 000")).toBeInTheDocument();
    expect(screen.getByText("Dược sĩ A")).toBeInTheDocument();
    expect(screen.getByText("QA Lead B")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở dừng hoạt động từ 31/12/2020")).toBeInTheDocument();
    expect(screen.getByText("GCN-789")).toBeInTheDocument();
    expect(screen.getByText("15-03-2026")).toBeInTheDocument();
    expect(screen.getByText("15-03-2027")).toBeInTheDocument();
    expect(screen.getByText("PIC/S-GMP")).toBeInTheDocument();
    expect(screen.getByText("Dây chuyền thuốc nước")).toBeInTheDocument();
    expect(screen.getByText("Còn hiệu lực")).toBeInTheDocument();
  });

  it("keeps facility-name abbreviations presentation-only inside the result grid", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({
      items: [
        buildSearchResult({
          facility_name: "Công ty cổ phần dược phẩm và trang thiết bị y tế",
        }),
      ],
      total_count: 1,
      offset: 0,
      limit: 100,
    });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);

    renderApp(["/search"]);

    expect(await screen.findByText("Cty CP DP và TTBYT")).toBeInTheDocument();
  });

  it("appends additional server pages without Prev/Next controls and keeps selection stable", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities
      .mockResolvedValueOnce({
        items: [
          buildSearchResult({ result_key: "site-1:GMP:canonical:line-p1", context_code: "1.1A", production_line_id: "line-p1", production_line_code: "A", line_code: "A" }),
          buildSearchResult({ result_key: "site-1:GMP:canonical:line-p2", context_code: "1.1B", production_line_id: "line-p2", production_line_code: "A", line_code: "A" }),
        ],
        total_count: 3,
        offset: 0,
        limit: 100,
      })
      .mockResolvedValueOnce({
        items: [buildSearchResult({ result_key: "site-1:GMP:C", context_code: "1.1C", line_code: "C" })],
        total_count: 3,
        offset: 2,
        limit: 100,
      });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);

    renderApp(["/search"]);

    expect((await screen.findAllByText("1.1A")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Đã tải 2 / 3")).not.toBeInTheDocument();
    const scrollRegion = screen.getByTestId("facility-table-scroll");
    Object.defineProperty(scrollRegion, "scrollTop", { configurable: true, value: 260 });
    Object.defineProperty(scrollRegion, "clientHeight", { configurable: true, value: 200 });
    Object.defineProperty(scrollRegion, "scrollHeight", { configurable: true, value: 400 });

    fireEvent.scroll(scrollRegion);

    await waitFor(() => {
      expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText("1.1C")).toBeInTheDocument();
    expect(screen.queryByText("3 dòng")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Prev$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Next$/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("1.1B"));

    await waitFor(() => {
      const lastCall = apiMocks.getFacilityWorkspace.mock.calls.at(-1);
      expect(lastCall?.[0]).toBe("site-1");
       expect(lastCall?.[3]).toBe("GMP");
       expect(lastCall?.[4]).toBe("A");
       expect(lastCall?.[6]).toBe("line-p2");
    });
    fireEvent.click(screen.getByRole("tab", { name: "Giấy chứng nhận GxP" }));
    await waitFor(() => {
      const lastCall = apiMocks.listSiteGxpCertificates.mock.calls.at(-1);
      expect(lastCall?.[6]).toBe("line-p2");
    });
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2);
  });

  it("does not synthesize ProductionLine UUIDs for legacy-unlinked or facility-wide UI selections", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({
      items: [
        buildSearchResult({ result_key: "site-1:GMP:legacy:A", context_code: "legacy-A", production_line_id: null, production_line_code: "A", production_line_identity_state: "legacy_unlinked", line_code: "A" }),
        buildSearchResult({ result_key: "site-1:GMP:facility", context_code: "facility", production_line_id: null, production_line_code: null, production_line_identity_state: "facility_wide", line_code: null }),
      ], total_count: 2, offset: 0, limit: 100,
    });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);
    renderApp(["/search"]);
    expect(await screen.findByText("legacy-A")).toBeInTheDocument();
    fireEvent.click(screen.getByText("legacy-A"));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBeNull());
    fireEvent.click(screen.getByRole("tab", { name: "Giấy chứng nhận GxP" }));
    await waitFor(() => expect(apiMocks.listSiteGxpCertificates.mock.calls.at(-1)?.[6]).toBeNull());
    fireEvent.click(screen.getByText("facility"));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBeNull());
    fireEvent.click(screen.getByRole("tab", { name: "Giấy chứng nhận GxP" }));
    await waitFor(() => expect(apiMocks.listSiteGxpCertificates.mock.calls.at(-1)?.[6]).toBeNull());
  });

  it("renders history beside master results and keeps event workflow inside its facility tab", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    const workspacePanel = await screen.findByRole("tab", { name: "Các đợt kiểm tra & thay đổi" });
    expect(workspacePanel).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("navigation", { name: "Quy trình xử lý sự kiện" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Thông tin hồ sơ" })).toBeInTheDocument();
    expect(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Hồ sơ" })).not.toBeInTheDocument();
    expect(container.querySelector(".workspace-context-strip")).toBeNull();
    expect(container.querySelector(".search-master-history > .results-panel")).not.toBeNull();
    expect(container.querySelector(".search-master-history > .history-panel")).not.toBeNull();
    expect(container.querySelector(".facility-workspace-panel .history-panel")).toBeNull();
    expect(container.querySelectorAll(".history-table")).toHaveLength(1);
    expect(container.querySelector(".event-workspace-detail-pane.detail-pane .event-workspace")).not.toBeNull();
  });

  it("keeps one history pane available across facility tabs and opens event detail on explicit selection", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    const { container } = renderApp(["/search?event_tab=Ki%E1%BB%83m+tra"]);
    await screen.findByRole("heading", { name: "Kế hoạch kiểm tra" });
    const history = container.querySelector(".history-table");
    for (const tab of ["Thông tin chung", "Giấy chứng nhận GxP", "Giấy chứng nhận đủ điều kiện"]) {
      fireEvent.click(screen.getByRole("tab", { name: tab }));
      expect(container.querySelector(".history-table")).toBe(history);
      expect(container.querySelectorAll(".history-table")).toHaveLength(1);
      expect(history?.querySelector("tr.selected")).toHaveAttribute("aria-selected", "true");
      expect(container.querySelector(".facility-table tr.selected")).not.toBeNull();
    }
    fireEvent.click(within(history as HTMLElement).getByText("Thay đổi"));
    await screen.findByText("Điều chỉnh địa chỉ kho bảo quản");
    expect(screen.getByRole("tab", { name: "Các đợt kiểm tra & thay đổi" })).toHaveAttribute("aria-selected", "true");
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(1);
  });

  it("manually activates facility tabs while focus navigation preserves exact context and makes no requests", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    const { container } = render(<MemoryRouter initialEntries={["/search?gxp_type=GMP&result_key=site-1%3AGMP%3AA&production_line_id=line-uuid-1&history_id=case-1&event_tab=Kiểm+tra"]}>
      <SearchRouteNavigator to="/search" /><App />
    </MemoryRouter>);
    await screen.findByRole("table", { name: "Lịch sử kiểm tra & thay đổi" });
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    await act(async () => { await apiMocks.getCaseWorkspace.mock.results[0].value; });
    await screen.findByRole("heading", { name: "Kế hoạch kiểm tra" });
    const tablist = screen.getByRole("tablist", { name: "Tab nghiệp vụ cơ sở" });
    const tabs = within(tablist).getAllByRole("tab");
    const master = container.querySelector(".facility-table");
    const history = container.querySelector(".history-table");
    act(() => tabs[1].focus());
    for (const key of ["ArrowRight", "End", "Home"]) fireEvent.keyDown(document.activeElement!, { key });
    expect(tabs[0]).toHaveFocus();
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(apiMocks.listSiteGxpCertificates).not.toHaveBeenCalled();
    expect(apiMocks.listSiteBusinessEligibilityCertificates).not.toHaveBeenCalled();
    fireEvent.keyDown(tabs[0], { key: "Enter" });
    expect(screen.getByRole("tabpanel", { name: "Thông tin chung" })).toBeInTheDocument();
    fireEvent.keyDown(tabs[0], { key: "ArrowLeft" });
    expect(tabs[3]).toHaveFocus();
    fireEvent.keyDown(tabs[3], { key: " " });
    await waitFor(() => expect(apiMocks.listSiteBusinessEligibilityCertificates).toHaveBeenCalledTimes(1));
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    expect(tabs.filter((tab) => tab.tabIndex === 0)).toEqual([tabs[3]]);
    fireEvent.click(tabs[1]);
    await screen.findByRole("heading", { name: "Kế hoạch kiểm tra" });
    // Keys on a real nested workflow control must not reach the facility owner.
    fireEvent.keyDown(screen.getByRole("button", { name: "Kiểm tra" }), { key: "ArrowRight" });
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("route-location")).toHaveTextContent("history_id=case-1");
    expect(screen.getByTestId("route-location")).toHaveTextContent("production_line_id=line-uuid-1");
    expect(container.querySelector(".facility-table")).toBe(master);
    expect(container.querySelector(".history-table")).toBe(history);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    fireEvent.click(tabs[0]);
    const changeRow = within(history as HTMLElement).getByText("Thay đổi").closest("tr")!;
    act(() => changeRow.focus());
    fireEvent.keyDown(changeRow, { key: "Enter" });
    await screen.findByText("Điều chỉnh địa chỉ kho bảo quản");
    expect(tabs[1]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("tabindex", "0");
    expect(changeRow).toHaveFocus();
    expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(1);
  });

  it("updates history for the exact new physical line while retaining master rows and hiding stale history during loading", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult(), buildSearchResult({ result_key: "site-1:GMP:canonical:line-2", context_code: "1.1A-2", production_line_id: "line-2" })], total_count: 2, offset: 0, limit: 100 });
    const nextWorkspace = buildWorkspace({ summary: { ...buildWorkspace().summary, context_code: "1.1A-2", selected_production_line_id: "line-2" }, history: [{ ...buildWorkspace().history[0], id: "case-line-2", standard: "Tiêu chuẩn dây chuyền thứ hai" }] });
    let resolveWorkspace!: (value: ReturnType<typeof buildWorkspace>) => void;
    apiMocks.getFacilityWorkspace.mockResolvedValueOnce(buildWorkspace()).mockImplementationOnce(() => new Promise((resolve) => { resolveWorkspace = resolve; }));
    apiMocks.getCaseWorkspace.mockImplementation((id: string) => Promise.resolve(buildCaseWorkspace({ case_summary: { ...buildCaseWorkspace().case_summary, id } })));
    const { container } = renderApp(["/search"]);
    const initialHistory = await screen.findByRole("table", { name: "Lịch sử kiểm tra & thay đổi" });
    fireEvent.click(within(initialHistory).getByText("Định kỳ"));
    await screen.findByRole("heading", { name: "Thông tin hồ sơ" });
    const master = container.querySelector(".facility-table");
    fireEvent.click(within(master as HTMLElement).getByText("1.1A-2"));
    expect(await screen.findByText("Đang tải lịch sử của ngữ cảnh đang chọn...")).toBeInTheDocument();
    expect(container.querySelector(".history-table")).toBeNull();
    expect(container.querySelector(".facility-table")).toBe(master);
    expect(within(master as HTMLElement).getByText("1.1A-2")).toBeInTheDocument();
    expect(screen.queryByText("Đang tải danh sách cơ sở...")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeDisabled();
    await act(async () => { resolveWorkspace(nextWorkspace); });
    const nextEvent = await screen.findByText("Tiêu chuẩn dây chuyền thứ hai");
    fireEvent.click(nextEvent);
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenLastCalledWith("case-line-2", expect.anything(), true, null));
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-2");
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[4]).toBe("A");
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(within(container.querySelector(".history-table") as HTMLElement).queryByText("Đổi địa chỉ")).not.toBeInTheDocument();
  });

  it.each([
    { name: "canonical same-code UUID", production_line_id: "line-2", line_code: "A", production_line_identity_state: "canonical", result_grain: "production_line" },
    { name: "legacy-unlinked", production_line_id: null, line_code: "A", production_line_identity_state: "legacy_unlinked", result_grain: "production_line" },
    { name: "facility-wide", production_line_id: null, line_code: null, production_line_identity_state: "facility_wide", result_grain: "facility" },
  ])("hides every old business surface at the first commit when selecting $name", async (identity) => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    const target = buildSearchResult({ ...identity, result_key: `target-${identity.name}`, context_code: "target-B" });
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult(), target], total_count: 2, offset: 0, limit: 100 });
    const previous = buildWorkspace();
    previous.action_readiness[3] = { ...previous.action_readiness[3], readiness_status: "available" };
    apiMocks.getFacilityWorkspace.mockResolvedValueOnce(previous).mockImplementationOnce(() => new Promise(() => {}));
    const { container } = renderApp(["/search?facility_tab=Thông+tin+chung"]);
    await screen.findByRole("table", { name: "Lịch sử kiểm tra & thay đổi" });
    const snapshots: { history: boolean; detail: boolean; action: boolean }[] = [];
    contextCommit.observe.mockImplementation((key: string) => {
      if (key === target.result_key) snapshots.push({
        history: Boolean(container.querySelector(".history-table")),
        detail: Boolean(container.querySelector(".facility-context-bar")),
        action: !(screen.getByRole("button", { name: "Tái đánh giá" }) as HTMLButtonElement).disabled,
      });
    });
    const row = within(container.querySelector(".facility-table") as HTMLElement).getByText("target-B").closest("tr")!;
    fireEvent.keyDown(row, { key: "Enter" });
    expect(snapshots.length).toBeGreaterThan(0);
    expect(snapshots[0]).toEqual({ history: false, detail: false, action: false });
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe(identity.production_line_id);
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[4]).toBe(identity.line_code);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
  });

  it("does not carry an old workspace error into the first committed render of B", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult(), buildSearchResult({ result_key: "B", context_code: "target-B", production_line_id: "line-2" })], total_count: 2, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockRejectedValueOnce(new Error("Error owned by A")).mockImplementationOnce(() => new Promise(() => {}));
    const { container } = renderApp(["/search"]);
    await screen.findByText("Error owned by A");
    const snapshots: boolean[] = [];
    contextCommit.observe.mockImplementation((key: string) => { if (key === "B") snapshots.push(Boolean(screen.queryByText("Error owned by A"))); });
    fireEvent.click(within(container.querySelector(".facility-table") as HTMLElement).getByText("target-B"));
    expect(snapshots[0]).toBe(false);
  });

  it("keeps B when the cancelled request A completes after B", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult(), buildSearchResult({ result_key: "B", context_code: "target-B", production_line_id: "line-2" })], total_count: 2, offset: 0, limit: 100 });
    let finishA!: (value: ReturnType<typeof buildWorkspace>) => void;
    let finishB!: (value: ReturnType<typeof buildWorkspace>) => void;
    apiMocks.getFacilityWorkspace.mockImplementationOnce(() => new Promise((resolve) => { finishA = resolve; })).mockImplementationOnce(() => new Promise((resolve) => { finishB = resolve; }));
    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1));
    const master = container.querySelector(".facility-table");
    fireEvent.click(within(master as HTMLElement).getByText("target-B"));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    await act(async () => { finishB(buildWorkspace({ history: [{ ...buildWorkspace().history[0], id: "case-B", standard: "History B" }] })); });
    await screen.findByText("History B");
    await act(async () => { finishA(buildWorkspace()); });
    expect(screen.getByText("History B")).toBeInTheDocument();
    expect(screen.queryByText("Đổi địa chỉ")).not.toBeInTheDocument();
    expect(container.querySelector(".facility-table")).toBe(master);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
  });

  it("does not publish a confirmed mutation's late refresh over the newly selected line", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult(), buildSearchResult({ result_key: "B", context_code: "target-B", production_line_id: "line-2" })], total_count: 2, offset: 0, limit: 100 });
    const previous = buildWorkspace();
    previous.action_readiness[3] = { ...previous.action_readiness[3], readiness_status: "available" };
    let finishRefresh!: (value: ReturnType<typeof buildWorkspace>) => void;
    apiMocks.getFacilityWorkspace.mockResolvedValueOnce(previous).mockImplementationOnce(() => new Promise((resolve) => { finishRefresh = resolve; })).mockResolvedValueOnce(buildWorkspace({ history: [] }));
    apiMocks.createInspectionCase.mockResolvedValue({ case_id: "confirmed-case-A" });
    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" }));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    fireEvent.click(within(container.querySelector(".facility-table") as HTMLElement).getByText("target-B"));
    await screen.findByText(/Chưa có lịch sử kiểm tra hoặc thay đổi/);
    await act(async () => { finishRefresh(buildWorkspace({ history: [{ ...previous.history[0], id: "confirmed-case-A", standard: "Confirmed A" }] })); });
    expect(screen.queryByText("Confirmed A")).not.toBeInTheDocument();
    expect(screen.getByText(/Chưa có lịch sử kiểm tra hoặc thay đổi/)).toBeInTheDocument();
    expect(apiMocks.createInspectionCase).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(3);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("hides certificate data at the first B commit and throughout B loading and error", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult(), buildSearchResult({ result_key: "B", context_code: "target-B", production_line_id: "line-2" })], total_count: 2, offset: 0, limit: 100 });
    let failB!: (error: Error) => void;
    apiMocks.getFacilityWorkspace.mockResolvedValueOnce(buildWorkspace()).mockImplementationOnce(() => new Promise((_resolve, reject) => { failB = reject; }));
    const certificate = { certificate_id: "cert-A", site_id: "site-1", case_id: "case-1", certificate_type: "GMP", line_code: "A", context_match_kind: "exact_line", latest_flag: true, certificate_number: "CERTIFICATE-A", issue_date: null, expiry_date: null, applicable_standard: "WHO-GMP", issuing_authority: null, status: "active" };
    apiMocks.listSiteGxpCertificates.mockResolvedValueOnce({ items: [certificate] }).mockResolvedValueOnce({ items: [] });
    apiMocks.getGxpCertificateDetail.mockResolvedValue({ ...certificate, facility_name: "Nhà máy A", scope_summary: "Certificate details A", action_readiness: [] });
    const { container } = renderApp(["/search?facility_tab=Giấy+chứng+nhận+GxP"]);
    await screen.findByText("Certificate details A");
    const snapshots: boolean[] = [];
    contextCommit.observe.mockImplementation((key: string) => { if (key === "B") snapshots.push(Boolean(screen.queryByText("Certificate details A") || screen.queryByText("CERTIFICATE-A"))); });
    fireEvent.click(within(container.querySelector(".facility-table") as HTMLElement).getByText("target-B"));
    expect(snapshots[0]).toBe(false);
    expect(screen.queryByText("Certificate details A")).not.toBeInTheDocument();
    await act(async () => { failB(new Error("Workspace B unavailable")); });
    await screen.findByText("Workspace B unavailable");
    expect(screen.queryByText("CERTIFICATE-A")).not.toBeInTheDocument();
    expect(container.querySelector(".history-table")).toBeNull();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
  });

  it.each([
    { parameter: "&facility_tab=wrong-tab", selected: "Các đợt kiểm tra & thay đổi" },
    { parameter: "&facility_tab=", selected: "Các đợt kiểm tra & thay đổi" },
    { parameter: "", selected: "Các đợt kiểm tra & thay đổi" },
    { parameter: "&facility_tab=Thông+tin+chung", selected: "Thông tin chung" },
  ])("normalizes initial facility tab input $parameter without losing tab semantics", async ({ parameter, selected }) => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [] }));
    render(<MemoryRouter initialEntries={[`/search?gxp_type=GMP${parameter}`]}><SearchRouteNavigator to="/search" /><App /></MemoryRouter>);
    await screen.findByRole("tabpanel", { name: selected });
    const tabs = within(screen.getByRole("tablist", { name: "Tab nghiệp vụ cơ sở" })).getAllByRole("tab");
    expect(tabs.filter((tab) => tab.getAttribute("aria-selected") === "true")).toHaveLength(1);
    expect(tabs.filter((tab) => tab.tabIndex === 0)).toHaveLength(1);
    await waitFor(() => expect(new URLSearchParams(screen.getByTestId("route-location").textContent ?? "").get("facility_tab")).toBe(selected === "Thông tin chung" ? selected : null));
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
  });

  it.each(["&facility_tab=wrong-tab", "&facility_tab=", "", "&facility_tab=Giấy+chứng+nhận+GxP"])("handles external tab input %s through Back and Forward without normalization loops", async (parameter) => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [] }));
    render(<MemoryRouter initialEntries={["/search?gxp_type=GMP&facility_tab=Thông+tin+chung"]}>
      <SearchRouteNavigator to={`/search?gxp_type=GMP${parameter}`} /><App />
    </MemoryRouter>);
    await screen.findByRole("tabpanel", { name: "Thông tin chung" });
    await waitFor(() => expect(screen.getByTestId("route-location")).toHaveTextContent("result_key="));
    const selected = parameter.includes("GxP") ? "Giấy chứng nhận GxP" : "Các đợt kiểm tra & thay đổi";
    for (const [button, tab] of [["Đi tới ngữ cảnh khác", selected], ["Quay lại ngữ cảnh trước", "Thông tin chung"], ["Tới ngữ cảnh tiếp theo", selected]]) {
      fireEvent.click(screen.getByRole("button", { name: button }));
      await screen.findByRole("tabpanel", { name: tab });
      expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
      expect(screen.getByRole("tab", { name: tab })).toHaveAttribute("tabindex", "0");
      await waitFor(() => expect(new URLSearchParams(screen.getByTestId("route-location").textContent ?? "").get("facility_tab")).toBe(tab === "Các đợt kiểm tra & thay đổi" ? null : tab));
    }
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(4);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(4);
  });

  it("external navigation wins over an initial A normalization in the same layout commit", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockImplementation((query: { gxp_type: string }) => Promise.resolve({ items: [buildSearchResult(query.gxp_type === "GLP" ? { result_key: "B", gxp_type: "GLP", production_line_id: "line-2" } : {})], total_count: 1, offset: 0, limit: 100 }));
    apiMocks.getFacilityWorkspace.mockImplementation((_site, _auth, _stub, _gxp, _line, _token, uuid) => Promise.resolve(buildWorkspace(uuid === "line-2" ? { history: [{ ...buildWorkspace().history[0], id: "case-B" }] } : {})));
    const destination = "/search?gxp_type=GLP&result_key=B&production_line_id=line-2&history_id=missing-B";
    render(<MemoryRouter initialEntries={["/search?gxp_type=GMP"]}>
      <SearchRouteNavigator to={destination} />
      <NavigateOnInitialHistoryCommit to={destination} />
      <App />
    </MemoryRouter>);
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-2"));
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("route-location")).toHaveTextContent("gxp_type=GLP");
    expect(screen.getByTestId("route-location")).toHaveTextContent("history_id=missing-B");
    await screen.findByText(/Không tìm thấy hồ sơ được liên kết/);
    expect(apiMocks.getCaseWorkspace.mock.calls.some((call) => call[0] === "case-B" || call[0] === "missing-B")).toBe(false);
  });

  it.each(["case-B", "stale-explicit-history"])("keeps exact external B identity and explicit history %s during navigation", async (historyId) => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    const first = buildSearchResult();
    const second = buildSearchResult({ result_key: "B", context_code: "target-B", gxp_type: "GLP", production_line_id: "line-2" });
    apiMocks.searchFacilities.mockImplementation((query: { gxp_type: string }) => Promise.resolve({ items: [query.gxp_type === "GLP" ? second : first], total_count: 1, offset: 0, limit: 100 }));
    let finishB!: (value: ReturnType<typeof buildWorkspace>) => void;
    apiMocks.getFacilityWorkspace.mockResolvedValueOnce(buildWorkspace()).mockImplementationOnce(() => new Promise((resolve) => { finishB = resolve; }));
    const { container } = render(<MemoryRouter initialEntries={["/search?gxp_type=GMP"]}>
      <SearchRouteNavigator to={`/search?gxp_type=GLP&result_key=B&production_line_id=line-2&history_id=${historyId}&facility_tab=Thông+tin+chung&event_tab=Kiểm+tra`} />
      <App />
    </MemoryRouter>);
    await screen.findByRole("table", { name: "Lịch sử kiểm tra & thay đổi" });
    // This user-click test starts from a settled route; the preceding test
    // deliberately exercises navigation before initial normalization settles.
    await waitFor(() => expect(screen.getByTestId("route-location")).toHaveTextContent("history_id=case-1"));
    const snapshots: boolean[] = [];
    contextCommit.observe.mockImplementation((key: string) => { if (key === "B") snapshots.push(Boolean(container.querySelector(".history-table") || container.querySelector(".facility-context-bar"))); });
    fireEvent.click(screen.getByRole("button", { name: "Đi tới ngữ cảnh khác" }));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(snapshots[0]).toBe(false);
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-2");
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[3]).toBe("GLP");
    const history = { ...buildWorkspace().history[0], id: "case-B", standard: "Only B history" };
    await act(async () => { finishB(buildWorkspace({ history: [history] })); });
    if (historyId === "case-B") {
      await screen.findByText("Only B history");
      expect(container.querySelector(".history-table tr.selected")).not.toBeNull();
      expect(screen.getByRole("tab", { name: "Thông tin chung" })).toHaveAttribute("aria-selected", "true");
    } else {
      await screen.findByText(/Không tìm thấy hồ sơ được liên kết/);
      expect(container.querySelector(".history-table")).toBeNull();
      expect(apiMocks.getCaseWorkspace.mock.calls.some((call) => call[0] === "case-B")).toBe(false);
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeDisabled();
    }
    expect(screen.getByTestId("route-location")).toHaveTextContent(`history_id=${historyId}`);
    expect(screen.getByTestId("route-location")).toHaveTextContent("production_line_id=line-2");
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2);
  });

  it("shows workspace errors in the history pane once and retains selectable master results", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockRejectedValue(new Error("Không thể tải lịch sử cơ sở"));
    const { container } = renderApp(["/search"]);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tải lịch sử cơ sở");
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(container.querySelector(".search-master-history .history-table")).toBeNull();
    expect(container.querySelector(".facility-table tr.selected")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeDisabled();
    expect(apiMocks.getCaseWorkspace).not.toHaveBeenCalled();
  });

  it("replaces the previous context error with loading and recovers history when selecting another facility", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult(), buildSearchResult({ result_key: "site-2:GMP:canonical:line-2", site_id: "site-2", context_code: "2.1A", production_line_id: "line-2" })], total_count: 2, offset: 0, limit: 100 });
    let resolveWorkspace!: (value: ReturnType<typeof buildWorkspace>) => void;
    apiMocks.getFacilityWorkspace.mockRejectedValueOnce(new Error("Lỗi cơ sở trước")).mockImplementationOnce(() => new Promise((resolve) => { resolveWorkspace = resolve; }));
    const { container } = renderApp(["/search"]);
    await screen.findByRole("alert");
    fireEvent.click(within(container.querySelector(".facility-table") as HTMLElement).getByText("2.1A"));
    expect(await screen.findByText("Đang tải lịch sử của ngữ cảnh đang chọn...")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Đang tải workspace" })).toBeInTheDocument();
    await act(async () => { resolveWorkspace(buildWorkspace({ history: [] })); });
    expect(await screen.findByText(/Chưa có lịch sử kiểm tra hoặc thay đổi/)).toBeInTheDocument();
    expect(screen.queryByText("Lỗi cơ sở trước")).not.toBeInTheDocument();
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[0]).toBe("site-2");
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-2");
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("renders genuine empty history beside master without requesting event detail", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [] }));
    const { container } = renderApp(["/search"]);
    expect(await screen.findByText(/Chưa có lịch sử kiểm tra hoặc thay đổi/)).toBeInTheDocument();
    expect(container.querySelector(".search-master-history .history-table")).not.toBeNull();
    expect(container.querySelector(".facility-table tr.selected")).not.toBeNull();
    expect(apiMocks.getCaseWorkspace).not.toHaveBeenCalled();
    expect(apiMocks.getChangeRequestWorkspace).not.toHaveBeenCalled();
  });

  it("selects history by keyboard without refetching master results or losing facility context across tabs", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    const { container } = renderApp(["/search"]);
    await screen.findByRole("heading", { name: "Thông tin hồ sơ" });
    const historyRows = within(container.querySelector(".history-table") as HTMLElement).getAllByRole("row").slice(1);
    const facilityRow = container.querySelector(".facility-table tbody tr.selected");
    historyRows[0].focus();
    fireEvent.keyDown(historyRows[0], { key: "ArrowDown" });
    expect(historyRows[1]).toHaveFocus();
    expect(historyRows[0]).toHaveAttribute("aria-selected", "true");
    expect(apiMocks.getChangeRequestWorkspace).not.toHaveBeenCalled();
    fireEvent.keyDown(historyRows[1], { key: "Enter" });
    await screen.findByText("Điều chỉnh địa chỉ kho bảo quản");
    expect(historyRows[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Thông tin chung" }));
    fireEvent.click(screen.getByRole("tab", { name: "Các đợt kiểm tra & thay đổi" }));
    expect(container.querySelector(".history-table tbody tr.selected")).toHaveAttribute("aria-label", historyRows[1].getAttribute("aria-label"));
    expect(container.querySelector(".facility-table tbody tr.selected")).toBe(facilityRow);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(1);
  });

  it("updates only the right event pane when history selection changes and keeps ActionCard free of duplicated facility context", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());

    const { container } = renderApp(["/search"]);

    expect(await screen.findByRole("button", { name: "Công ty mới" })).toBeInTheDocument();
    const actionPanel = container.querySelector(".action-panel");
    expect(actionPanel).not.toBeNull();
    expect(actionPanel?.textContent ?? "").not.toContain("1.1A");
    expect(actionPanel?.textContent ?? "").not.toContain("Nhà máy A");
    expect(actionPanel?.textContent ?? "").not.toContain("Công ty cổ phần dược phẩm Trung ương I");

    await waitFor(() => {
      expect(container.querySelector(".history-table")).not.toBeNull();
    });
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));

    await waitFor(() => expect(screen.getByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument());
    expect(screen.queryByRole("heading", { name: "TD-01" })).not.toBeInTheDocument();
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đề nghị" })).toBeInTheDocument();
    expect(within(container.querySelector(".event-workspace") as HTMLElement).getByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("switches between case and change-request workspaces without stale detail or master-search refetch", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(buildCaseWorkspace())
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          application: {
            ...buildCaseWorkspace().application,
            dossier_code: "HS-001-RETURN",
          },
        }),
      );
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(
      buildChangeRequestWorkspace({
        legacy_change_request_id: 189,
        scope_label: null,
        requester_name: null,
        handled_on: null,
        handled_by_name: null,
        result_label: null,
        approval_reference: null,
        details: [
          {
            change_detail_id: "change-detail-189",
            legacy_change_detail_id: 157,
            classification_id: null,
            classification_label: "Điều chỉnh cách ghi địa chỉ",
            approval_status: null,
            old_value: "No cu",
            new_value: "No moi",
            note: null,
          },
        ],
      }),
    );

    const { container } = renderApp(["/search"]);

    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("heading", { name: "KT-2026-GMP-A" })).not.toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);

    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));

    expect(screen.queryByRole("heading", { name: "TD-01" })).not.toBeInTheDocument();
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Thông tin hồ sơ" })).not.toBeInTheDocument();
    expect(screen.queryByText("Không tải được workspace thay đổi")).not.toBeInTheDocument();

    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Định kỳ"));

    expect(await screen.findByText("HS-001-RETURN")).toBeInTheDocument();
    expect(screen.queryByText("Điều chỉnh địa chỉ kho bảo quản")).not.toBeInTheDocument();
    expect(screen.queryByText("Không tải được workspace hồ sơ")).not.toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(1);
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("surfaces the backend change-request error message instead of a generic hidden failure", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockRejectedValue(new Error("404 Change request not found."));

    const { container } = renderApp(["/search"]);

    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("heading", { name: "KT-2026-GMP-A" })).not.toBeInTheDocument();
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));

    expect(await screen.findByText("Không tải được workspace thay đổi")).toBeInTheDocument();
    expect(screen.getByText("404 Change request not found.")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("renders case-linked workflow steps without refetching master search or changing selected rows", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        remediation: {
          cycles: [buildRemediationCycle({ submitted_on: "2026-08-09", assessed_on: "2026-08-12", assessor_name: "Chuyên viên B", result: "Đạt", status: "accepted", notes: "Đã hoàn tất" })],
        },
      }),
    );

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Kiểm tra/ }));
    expect((await screen.findAllByText("QĐ-KT-01")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Khắc phục/ }));
    expect(await screen.findByText("Lịch sử khắc phục")).toBeInTheDocument();
    expect(screen.getByText("Đạt")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Xử lý/ }));
    expect(await screen.findByText("Đề xuất cấp chứng nhận")).toBeInTheDocument();
    expect(screen.getByText("Tiếp nhận hồ sơ")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tài liệu" })).not.toBeInTheDocument();
    expect(screen.getByText("Tài liệu liên quan")).toBeInTheDocument();
    expect(await screen.findByText("Quyết định cấp CC")).toBeInTheDocument();
    expect(screen.getByText("8 qd cap cc GMP.docx")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mở Quyết định cấp CC" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Lịch sử Quyết định cấp CC" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Tạo Quyết định cấp CC" })).not.toBeInTheDocument();
    expect(screen.getByText("Thiếu contract input nghiệp vụ typed theo ngữ cảnh; không hiển thị thao tác tạo generic.")).toBeInTheDocument();

    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getChangeRequestWorkspace).not.toHaveBeenCalled();
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  }, 10000);

  it("renders contextual documents from backend workflow_step without local family mapping", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        contextual_document_actions: [
          {
            checklist_key: "case:case-1:CUSTOM_OWNER_DOC",
            label: "Tài liệu owner test",
            family_code: "CUSTOM_OWNER_DOC",
            workflow_step: "Xử lý",
            parent_scope: "case",
            parent_id: "case-1",
            status: "available",
            document_id: "doc-owner-test",
            document_type_code: "CUSTOM_OWNER_DOC",
            title: "Owner test",
            original_filename: "owner-test.docx",
            issued_on: "2026-08-09T00:00:00Z",
            available_variant_types: ["editable_docx"],
            detail_available: true,
            actions: [
              { action_key: "open", label: "Mở", available: true, disabled_reason: null, required_permissions: ["document.read"] },
              { action_key: "create", label: "Tạo", available: false, disabled_reason: "not-ready", required_permissions: ["document.write"] },
              { action_key: "history", label: "Lịch sử", available: true, disabled_reason: null, required_permissions: ["document.read"] },
            ],
          },
        ],
      }),
    );

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    expect(screen.queryByText("Tài liệu owner test")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Xử lý/ }));
    expect(await screen.findByText("Tài liệu owner test")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Kiểm tra/ }));
    expect(screen.queryByText("Tài liệu owner test")).not.toBeInTheDocument();
  });

  it("shows document action errors locally and keeps the selected workspace context", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.openCaseDocumentCurrentContent.mockRejectedValue(buildApiError("403 User is missing required permission.", 403));

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Xử lý/ }));
    fireEvent.click(screen.getByRole("button", { name: "Mở Quyết định cấp CC" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("403 User is missing required permission.");
    expect(screen.getByRole("button", { name: /Xử lý/ })).toHaveAttribute("aria-current", "step");
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getDocumentDetail).not.toHaveBeenCalled();
  });

  it("opens current document binary for Mở and keeps metadata loading on Lịch sử", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getDocumentDetail.mockResolvedValue({
      document_id: "doc-cert-decision",
      family_code: "CERTIFICATE_DECISION",
      document_type_code: "CERTIFICATE_DECISION",
      title: "Quyết định cấp CC",
      legacy_entity_type: "inspection",
      case_id: "case-1",
      capa_cycle_id: null,
      certificate_id: null,
      business_eligibility_certificate_id: null,
      change_request_id: null,
      variants: [],
      generation_runs: [],
    });

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Xử lý/ }));
    fireEvent.click(screen.getByRole("button", { name: "Mở Quyết định cấp CC" }));

    await waitFor(() => {
      expect(apiMocks.openCaseDocumentCurrentContent).toHaveBeenCalledWith(
        "case-1",
        "doc-cert-decision",
        expect.objectContaining({ username: "operator.local", role: "inspector" }),
        true,
        null,
      );
    });
    expect(window.open).toHaveBeenCalledWith("blob:document-preview", "_blank", "noopener");
    expect(apiMocks.getDocumentDetail).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Lịch sử Quyết định cấp CC" }));
    expect(await screen.findByText("Lịch sử tài liệu")).toBeInTheDocument();
    expect(apiMocks.getDocumentDetail).toHaveBeenCalledWith(
      "doc-cert-decision",
      expect.objectContaining({ username: "operator.local", role: "inspector" }),
      true,
      null,
    );
  });

  it("renders inspection owners and keeps team editing blocked when structured read data is unavailable", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        inspection: {
          ...buildCaseWorkspace().inspection,
          plan_start_on: "2026-08-04",
          plan_end_on: "2026-08-05",
          planning_sheet_name: "KHKT-01",
          decision_document_hint: "QĐ-KT dự thảo",
          team_display_text: "Trưởng đoàn A; Thành viên B",
        },
      }),
    );

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Kiểm tra/ }));

    expect(await screen.findByText("Kế hoạch kiểm tra")).toBeInTheDocument();
    expect(screen.getByText("Thực hiện & kết quả")).toBeInTheDocument();
    expect(screen.getByText("Đoàn kiểm tra")).toBeInTheDocument();
    expect(container.querySelectorAll(".inspection-workspace .detail-form-matrix")).toHaveLength(3);
    for (const field of ["Từ ngày", "Đến ngày", "Số/Tham chiếu QĐKT", "Biên bản legacy (chỉ đọc)", "Tiêu chuẩn áp dụng", "Kết quả kiểm tra"]) {
      expect(screen.getAllByText(field).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" })).toBeDisabled();
    expect(screen.getByText(/structured_read_unavailable/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Chỉnh sửa" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa Từ ngày kế hoạch" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa Đến ngày kế hoạch" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa các đợt kiểm tra" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa Kết quả kiểm tra" })).toBeInTheDocument();
  });

  it("lets the operator edit only CaseApplication owner fields and cancel back to authoritative values", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    expect(container.querySelector(".case-application-grid.detail-form-matrix")).not.toBeNull();
    for (const field of ["Ngày nộp", "Mã hồ sơ", "Loại kiểm tra", "GxP", "Dây chuyền", "Tiêu chuẩn áp dụng", "Năm mở hồ sơ", "Trạng thái hồ sơ"]) {
      expect(screen.getAllByText(field).length).toBeGreaterThan(0);
    }
    expect(screen.queryByRole("button", { name: "Chỉnh sửa" })).not.toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Mã hồ sơ" }));

    expect(screen.queryByLabelText("Ngày nộp")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Mã hồ sơ")).toHaveValue("HS-001");
    expect(screen.queryByLabelText("Tham chiếu hồ sơ")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Người nộp hồ sơ")).not.toBeInTheDocument();
    const dossierCodeInput = screen.getByLabelText("Mã hồ sơ");
    const inlineField = dossierCodeInput.closest(".editable-detail-value");
    expect(inlineField?.querySelector(".detail-value-slot .editable-detail-actions")).not.toBeNull();
    expect(inlineField?.querySelector(":scope > .editable-detail-actions")).toBeNull();
    fireEvent.change(dossierCodeInput, { target: { value: "HS-EDIT-DRAFT" } });
    fireEvent.keyDown(dossierCodeInput, { key: "Escape" });

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    expect(screen.queryByLabelText("Mã hồ sơ")).not.toBeInTheDocument();
    expect(apiMocks.upsertCaseApplication).not.toHaveBeenCalled();
  });

  it("supports keyboard-first field activation with Enter without exposing section-wide edit mode", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    const activator = screen.getByRole("button", { name: "Sửa Mã hồ sơ" });
    activator.focus();
    fireEvent.keyDown(activator, { key: "Enter" });

    expect(screen.getByLabelText("Mã hồ sơ")).toHaveValue("HS-001");
    expect(screen.queryByRole("button", { name: "Chỉnh sửa" })).not.toBeInTheDocument();
  });

  it("creates a new CAPA cycle from the Khắc phục tab, refreshes only case workspace, and selects the created round", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          case_summary: {
            ...buildCaseWorkspace().case_summary,
            row_version: 8,
            state: "inspection_completed",
          },
          remediation: {
            cycles: [],
            actions: buildCapaActions(buildCapaAction("create_capa_cycle", true, { expected_version: 8 })),
          },
        }),
      )
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          case_summary: {
            ...buildCaseWorkspace().case_summary,
            row_version: 8,
            state: "inspection_completed",
          },
          remediation: {
            cycles: [buildRemediationCycle({ capa_cycle_id: "capa-2", row_version: 1, round_no: 1, requested_on: "2026-09-02", notes: "Yêu cầu vòng 1" })],
            actions: buildCapaActions(
              buildCapaAction("create_capa_cycle", false, { reason_code: "latest_cycle_not_rejected" }),
              buildCapaAction("submit_capa_cycle:capa-2", true, { expected_version: 1 }),
              buildCapaAction("update_capa_cycle:capa-2", true, { expected_version: 1 }),
            ),
          },
        }),
      );
    apiMocks.createCapaCycle.mockResolvedValue({
      capa_cycle_id: "capa-2",
      case_id: "case-1",
      row_version: 1,
      round_no: 1,
      requested_on: "2026-09-02",
      submitted_on: null,
      assessed_on: null,
      assessor_user_id: null,
      assessor_name: null,
      result: null,
      status: "requested",
      notes: "Yêu cầu vòng 1",
      audit_event_id: "audit-capa-1",
    });

    const { container } = renderApp(["/search?event_tab=Kh%E1%BA%AFc+ph%E1%BB%A5c"]);

    expect(await screen.findByText("Lịch sử khắc phục")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Thêm vòng khắc phục" }));
    fireEvent.change(screen.getByLabelText("Ngày yêu cầu"), { target: { value: "2026-09-02" } });
    fireEvent.change(screen.getByLabelText("Ghi chú"), { target: { value: "Yêu cầu vòng 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo vòng khắc phục" }));

    await waitFor(() => {
      expect(apiMocks.createCapaCycle).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.createCapaCycle).toHaveBeenCalledWith(
      "case-1",
      {
        expected_case_version: 8,
        incoming_reference: null,
        requested_on: "2026-09-02",
        notes: "Yêu cầu vòng 1",
      },
      expect.objectContaining({ username: "operator.local", role: "inspector" }),
      true,
      null,
    );
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Chi tiết vòng khắc phục 1")).toBeInTheDocument();
    expect(screen.getAllByText("Yêu cầu vòng 1").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Ghi nhận tiếp nhận" })).toBeInTheDocument();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("updates a requested CAPA cycle with cycle row_version and preserves unsaved draft on 409 conflict", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        case_summary: {
          ...buildCaseWorkspace().case_summary,
          state: "inspection_completed",
        },
        remediation: {
          cycles: [buildRemediationCycle({ capa_cycle_id: "capa-1", row_version: 4, notes: "Bản nháp cũ" })],
          actions: buildCapaActions(buildCapaAction("update_capa_cycle:capa-1", true, { expected_version: 4 })),
        },
      }),
    );
    apiMocks.updateCapaCycle.mockRejectedValue(
      buildApiError("Stale CAPA cycle update. Expected version 4, current version is 5.", 409),
    );

    renderApp(["/search?event_tab=Kh%E1%BA%AFc+ph%E1%BB%A5c"]);

    expect(await screen.findByText("Chi tiết vòng khắc phục 1")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Ghi chú" }));
    fireEvent.change(screen.getByLabelText("Ghi chú khắc phục"), { target: { value: "Bản nháp mới" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Ghi chú" }));

    await waitFor(() => {
      expect(apiMocks.updateCapaCycle).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.updateCapaCycle).toHaveBeenCalledWith(
      "capa-1",
      {
        expected_version: 4,
        incoming_reference: null,
        requested_on: "2026-08-07",
        notes: "Bản nháp mới",
      },
      expect.objectContaining({ username: "operator.local", role: "inspector" }),
      true,
      null,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Không thể lưu vì vòng khắc phục đã bị thay đổi hoặc hồ sơ đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.",
    );
    expect(screen.getByLabelText("Ghi chú khắc phục")).toHaveValue("Bản nháp mới");
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("submits a requested CAPA cycle without refetching master search and keeps the Khắc phục tab active", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          case_summary: {
            ...buildCaseWorkspace().case_summary,
            state: "inspection_completed",
          },
          remediation: {
            cycles: [buildRemediationCycle({ capa_cycle_id: "capa-1", row_version: 2 })],
            actions: buildCapaActions(buildCapaAction("submit_capa_cycle:capa-1", true, { expected_version: 2 })),
          },
        }),
      )
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          case_summary: {
            ...buildCaseWorkspace().case_summary,
            state: "inspection_completed",
          },
          remediation: {
            cycles: [buildRemediationCycle({ capa_cycle_id: "capa-1", row_version: 3, submitted_on: "2026-09-05", status: "submitted", notes: "Đã nhận hồ sơ" })],
            actions: buildCapaActions(buildCapaAction("assess_capa_cycle:capa-1", true, { expected_version: 3 })),
          },
        }),
      );
    apiMocks.submitCapaCycle.mockResolvedValue({
      capa_cycle_id: "capa-1",
      case_id: "case-1",
      row_version: 3,
      round_no: 1,
      requested_on: "2026-08-07",
      submitted_on: "2026-09-05",
      assessed_on: null,
      assessor_user_id: null,
      assessor_name: null,
      result: null,
      status: "submitted",
      notes: "Đã nhận hồ sơ",
      audit_event_id: "audit-capa-submit",
    });

    renderApp(["/search?event_tab=Kh%E1%BA%AFc+ph%E1%BB%A5c"]);

    expect(await screen.findByText("Chi tiết vòng khắc phục 1")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ngày ghi nhận tiếp nhận"), { target: { value: "2026-09-05" } });
    fireEvent.change(screen.getByLabelText("Ghi chú thao tác khắc phục"), { target: { value: "Đã nhận hồ sơ" } });
    const submitButton = screen.getByRole("button", { name: "Ghi nhận tiếp nhận" });
    expect(screen.getByLabelText("Ngày ghi nhận tiếp nhận")).toHaveValue("2026-09-05");
    expect(submitButton).toBeEnabled();
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(apiMocks.submitCapaCycle).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.submitCapaCycle).toHaveBeenCalledWith(
      "capa-1",
      {
        expected_version: 2,
        submitted_on: "2026-09-05",
        notes: "Đã nhận hồ sơ",
      },
      expect.objectContaining({ username: "operator.local", role: "inspector" }),
      true,
      null,
    );
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText("Đã tiếp nhận khắc phục").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Khắc phục/ })).toHaveAttribute("aria-current", "step");
  });

  it("surfaces assess permission errors clearly and sends only the canonical assess payload", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        case_summary: {
          ...buildCaseWorkspace().case_summary,
          state: "inspection_completed",
        },
        remediation: {
          cycles: [buildRemediationCycle({ capa_cycle_id: "capa-1", row_version: 3, submitted_on: "2026-09-05", status: "submitted", notes: "Đã nhận hồ sơ" })],
          // The projection was fresh when the command was rendered; the mocked
          // 403 proves mutation enforcement remains authoritative after that.
          actions: buildCapaActions(buildCapaAction("assess_capa_cycle:capa-1", true, { expected_version: 3 })),
        },
      }),
    );
    apiMocks.assessCapaCycle.mockRejectedValue(buildApiError("User is missing required permission: capa.assess", 403));

    renderApp(["/search?event_tab=Kh%E1%BA%AFc+ph%E1%BB%A5c"]);

    expect(await screen.findByText("Chi tiết vòng khắc phục 1")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ngày đánh giá khắc phục"), { target: { value: "2026-09-06" } });
    fireEvent.change(screen.getByLabelText("Kết quả đánh giá khắc phục"), { target: { value: "accepted" } });
    fireEvent.change(screen.getByLabelText("Ghi chú thao tác khắc phục"), { target: { value: "Đạt yêu cầu" } });
    const assessButton = screen.getByRole("button", { name: "Đánh giá" });
    expect(screen.getByLabelText("Ngày đánh giá khắc phục")).toHaveValue("2026-09-06");
    expect(screen.getByLabelText("Kết quả đánh giá khắc phục")).toHaveValue("accepted");
    expect(assessButton).toBeEnabled();
    fireEvent.click(assessButton);

    await waitFor(() => {
      expect(apiMocks.assessCapaCycle).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.assessCapaCycle).toHaveBeenCalledWith(
      "capa-1",
      {
        expected_version: 3,
        assessed_on: "2026-09-06",
        result: "accepted",
        notes: "Đạt yêu cầu",
      },
      expect.objectContaining({ username: "operator.local", role: "inspector" }),
      true,
      null,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Bạn không có quyền thực hiện thao tác này.");
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
  });

  it("saves inspection plan with plan row_version, refreshes only selected case workspace, and preserves Kiểm tra context", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          inspection: {
            ...buildCaseWorkspace().inspection,
            plan_row_version: 3,
            plan_start_on: "2026-08-04",
            plan_end_on: "2026-08-05",
            planning_sheet_name: "KHKT-OLD",
          },
        }),
      )
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          inspection: {
            ...buildCaseWorkspace().inspection,
            plan_row_version: 4,
            plan_start_on: "2026-09-01",
            plan_end_on: "2026-09-02",
            planning_sheet_name: "KHKT-NEW",
            decision_document_hint: "QĐ-KT-NEW",
          },
        }),
      );
    apiMocks.upsertInspectionPlan.mockResolvedValue({
      case_id: "case-1",
      row_version: 4,
      plan_start_on: "2026-09-01",
      plan_end_on: "2026-09-02",
      planning_sheet_name: "KHKT-NEW",
      decision_document_hint: "QĐ-KT-NEW",
      audit_event_id: "audit-plan-1",
      inspection_event_id: "event-plan-1",
    });

    const { container } = renderApp(["/search?event_tab=Ki%E1%BB%83m+tra"]);

    expect(await screen.findByText("Kế hoạch kiểm tra")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kiểm tra" })).toHaveAttribute("aria-current", "step");
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Từ ngày kế hoạch" }));
    fireEvent.change(screen.getByLabelText("Từ ngày kế hoạch"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Từ ngày" }));

    await waitFor(() => {
      expect(apiMocks.upsertInspectionPlan).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.upsertInspectionPlan).toHaveBeenCalledWith(
      "case-1",
      {
        expected_version: 3,
        plan_start_on: "2026-09-01",
      },
      expect.objectContaining({
        username: "operator.local",
        role: "inspector",
      }),
      true,
      null,
    );
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("01-09-2026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Kiểm tra" })).toHaveAttribute("aria-current", "step");
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it.each([
    ["canonical P2", buildSearchResult({ result_key: "site-1:GMP:canonical:line-p2", production_line_id: "line-uuid-2", production_line_code: "A", line_code: "A" }), "line-uuid-2", "A"],
    ["legacy-unlinked", buildSearchResult({ result_key: "site-1:GMP:legacy:A", production_line_id: null, production_line_code: "A", production_line_identity_state: "legacy_unlinked", line_code: "A" }), null, "A"],
    ["facility-wide", buildSearchResult({ result_key: "site-1:GMP:facility", production_line_id: null, production_line_code: null, production_line_identity_state: "facility_wide", line_code: null }), null, null],
  ])("saves case application for %s and preserves the selected workspace identity", async (_label, result, expectedProductionLineId, expectedLineCode) => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [result], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace
      .mockResolvedValueOnce(buildWorkspace())
      .mockResolvedValueOnce(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(buildCaseWorkspace())
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          application: {
            ...buildCaseWorkspace().application,
            row_version: 5,
            submitted_on: "2026-08-31T00:00:00Z",
            dossier_code: "HS-2026-31",
            dossier_reference: "CV-31",
            applicant_name: "Công ty A",
          },
        }),
      );
    apiMocks.upsertCaseApplication.mockResolvedValue({
      case_id: "case-1",
      row_version: 5,
      submitted_on: "2026-08-31T00:00:00Z",
      dossier_code: "HS-2026-31",
      dossier_reference: "CV-31",
      applicant_name: "Công ty A",
      audit_event_id: "audit-application-1",
      inspection_event_id: "event-application-1",
    });

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Mã hồ sơ" }));
    expect(screen.queryByLabelText("Ngày nộp")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Mã hồ sơ"), { target: { value: "HS-2026-31" } });
    fireEvent.keyDown(screen.getByLabelText("Mã hồ sơ"), { key: "Enter" });

    await waitFor(() => {
      expect(apiMocks.upsertCaseApplication).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.upsertCaseApplication).toHaveBeenCalledWith(
      "case-1",
      {
        expected_version: 4,
        dossier_code: "HS-2026-31",
      },
      expect.objectContaining({
        username: "operator.local",
        role: "inspector",
      }),
      true,
      null,
    );
    await waitFor(() => {
      expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[4]).toBe(expectedLineCode);
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe(expectedProductionLineId);
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("HS-2026-31")).toBeInTheDocument();
    expect(screen.getByText("31-08-2026")).toBeInTheDocument();
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("refreshes the selected case and facility exactly once after a transition 409 without retrying", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    const transitionWorkspace = buildCaseWorkspace({
      transition_actions: [{
        action_key: "transition:certified",
        label: "Cấp chứng nhận",
        target_state: "certified",
        available: true,
        expected_version: 8,
        reason_code: null,
        required_permissions: ["case.edit"],
      }],
    });
    apiMocks.getFacilityWorkspace
      .mockResolvedValueOnce(buildWorkspace())
      .mockResolvedValueOnce(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(transitionWorkspace)
      .mockResolvedValueOnce(transitionWorkspace);
    apiMocks.transitionCase.mockRejectedValue(buildApiError("Stale case transition.", 409));

    const { container } = renderApp(["/search"]);

    fireEvent.click(await screen.findByRole("button", { name: "Kiểm tra" }));
    expect(await screen.findByRole("button", { name: "Cấp chứng nhận" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Stale case transition.");
    await waitFor(() => {
      expect(apiMocks.transitionCase).toHaveBeenCalledTimes(1);
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
      expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("keeps unsaved inspection outcome draft on 409 conflict and does not refetch master search", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.upsertInspectionOutcome.mockRejectedValue(
      buildApiError("Stale inspection_outcome update. Expected version 6, current version is 7.", 409),
    );

    renderApp(["/search?event_tab=Ki%E1%BB%83m+tra"]);

    expect(await screen.findByText("Thực hiện & kết quả")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Kết quả kiểm tra" }));
    fireEvent.change(screen.getByLabelText("Kết quả kiểm tra"), { target: { value: "Kết quả draft mới" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Kết quả kiểm tra" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Không thể lưu kết quả kiểm tra vì hồ sơ đã bị thay đổi hoặc đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.",
    );
    expect(screen.getByLabelText("Kết quả kiểm tra")).toHaveValue("Kết quả draft mới");
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
  });

  it("saves canonical inspection periods with outcome row_version and refreshes facility history plus selected case only", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace
      .mockResolvedValueOnce(buildWorkspace())
      .mockResolvedValueOnce(
        buildWorkspace({
          history: [
            {
              ...buildWorkspace().history[0],
              occurred_on: "2026-09-04",
            },
            ...buildWorkspace().history.slice(1),
          ],
        }),
      );
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(buildCaseWorkspace())
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          inspection: {
            ...buildCaseWorkspace().inspection,
            outcome_row_version: 7,
            inspection_period_state: "KNOWN",
            inspection_period_segments: [{ id: "period-1", ordinal: 1, started_on: "2026-09-03", ended_on: "2026-09-04" }],
            outcome_decision_reference_compatibility: "QĐ-KT-UPDATED",
            bbkt_reference: "BBKT-UPDATED",
            outcome_result: "Đạt sau cập nhật",
          },
        }),
      );
    apiMocks.upsertInspectionPeriodSegments.mockResolvedValue({
      case_id: "case-1",
      row_version: 7,
      outcome_decision_reference_compatibility: "QĐ-KT-UPDATED",
      bbkt_reference: "BBKT-UPDATED",
      outcome_result: "Đạt sau cập nhật",
      audit_event_id: "audit-outcome-1",
      inspection_event_id: "event-outcome-1",
    });

    const { container } = renderApp(["/search?event_tab=Ki%E1%BB%83m+tra"]);

    expect(await screen.findByText("Thực hiện & kết quả")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sửa các đợt kiểm tra" }));
    fireEvent.click(screen.getByRole("button", { name: "Thêm lần kiểm tra" }));
    fireEvent.change(screen.getByLabelText("Từ ngày lần 1"), { target: { value: "2026-09-03" } });
    fireEvent.change(screen.getByLabelText("Đến ngày lần 1"), { target: { value: "2026-09-04" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu các đợt kiểm tra" }));

    await waitFor(() => {
      expect(apiMocks.upsertInspectionPeriodSegments).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.upsertInspectionPeriodSegments).toHaveBeenCalledWith(
      "case-1",
      {
        expected_version: 6,
        segments: [{ ordinal: 1, started_on: "2026-09-03", ended_on: "2026-09-04" }],
      },
      expect.objectContaining({
        username: "operator.local",
        role: "inspector",
      }),
      true,
      null,
    );
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Đạt sau cập nhật")).toBeInTheDocument();
    expect(within(container.querySelector(".history-panel") as HTMLElement).getByText("04-09-2026")).toBeInTheDocument();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("shows a clear Vietnamese conflict message and preserves unsaved values on stale case application save", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.upsertCaseApplication.mockRejectedValue(
      buildApiError("Stale case_application update. Expected version 4, current version is 5.", 409),
    );

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Mã hồ sơ" }));
    fireEvent.change(screen.getByLabelText("Mã hồ sơ"), { target: { value: "HS-CONFLICT" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Mã hồ sơ" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Không thể lưu vì hồ sơ đã bị thay đổi hoặc đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.",
    );
    expect(screen.getByLabelText("Mã hồ sơ")).toHaveValue("HS-CONFLICT");
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
  });

  it("surfaces backend 403 and 422 validation errors clearly in the case application form", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.upsertCaseApplication
      .mockRejectedValueOnce(buildApiError("User is missing required permission: case.edit", 403))
      .mockRejectedValueOnce(buildApiError("Input should be a valid datetime", 422));

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Mã hồ sơ" }));
    fireEvent.click(screen.getByRole("button", { name: "Lưu Mã hồ sơ" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bạn không có quyền cập nhật hồ sơ này.");

    fireEvent.click(screen.getByRole("button", { name: "Lưu Mã hồ sơ" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Dữ liệu hồ sơ chưa hợp lệ.");
  });

  it("prevents double-submit while case application save is pending", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace
      .mockResolvedValueOnce(buildWorkspace())
      .mockResolvedValueOnce(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(buildCaseWorkspace())
      .mockResolvedValueOnce(buildCaseWorkspace());
    let releaseSave: () => void = () => {};
    apiMocks.upsertCaseApplication.mockImplementation(
      () =>
        new Promise((resolve) => {
          releaseSave = () =>
            resolve({
              case_id: "case-1",
              row_version: 5,
              submitted_on: "2026-01-15T00:00:00Z",
              dossier_code: "HS-001",
              dossier_reference: "QĐ-TN-01",
              applicant_name: "Nguyễn Văn A",
              audit_event_id: "audit-pending",
              inspection_event_id: null,
            });
        }),
    );

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Mã hồ sơ" }));
    const submitButton = screen.getByRole("button", { name: "Lưu Mã hồ sơ" });
    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Lưu Mã hồ sơ" })).toBeDisabled();
    });
    expect(apiMocks.upsertCaseApplication).toHaveBeenCalledTimes(1);

    releaseSave();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sửa Mã hồ sơ" })).toBeInTheDocument();
    });
  });

  it("saves case assessment with assessment row_version, keeps timeline read-only, and refreshes only selected case workspace", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(buildCaseWorkspace())
      .mockResolvedValueOnce(
        buildCaseWorkspace({
          processing: {
            ...buildCaseWorkspace().processing,
            row_version: 3,
            assessor_name: "Chuyên viên C",
          },
        }),
      );
    apiMocks.upsertCaseAssessment.mockResolvedValue({
      case_id: "case-1",
      row_version: 3,
      assessed_on: "2026-08-08T00:00:00Z",
      assessor_name: "Chuyên viên C",
      assessment_result: "Đề xuất cấp chứng nhận",
      notes: null,
      audit_event_id: "audit-assessment-1",
      inspection_event_id: null,
    });

    renderApp(["/search?event_tab=X%E1%BB%AD+l%C3%BD"]);

    expect(await screen.findByText("Thông tin xử lý")).toBeInTheDocument();
    expect(screen.getByText("Các mốc xử lý hành chính")).toBeInTheDocument();
    expect(screen.queryByLabelText("Ghi chú")).not.toBeInTheDocument();

    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Người thẩm định" }));
    expect(screen.queryByLabelText("Ngày thẩm định")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Người thẩm định")).toHaveValue("Chuyên viên B");
    fireEvent.change(screen.getByLabelText("Người thẩm định"), { target: { value: "Chuyên viên C" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Người thẩm định" }));

    await waitFor(() => {
      expect(apiMocks.upsertCaseAssessment).toHaveBeenCalledTimes(1);
    });
    expect(apiMocks.upsertCaseAssessment).toHaveBeenCalledWith(
      "case-1",
      {
        expected_version: 2,
        assessed_on: "2026-08-08T00:00:00Z",
        assessor_name: "Chuyên viên C",
        assessment_result: "Đề xuất cấp chứng nhận",
        notes: null,
      },
      expect.objectContaining({ username: "operator.local", role: "inspector" }),
      true,
      null,
    );
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Chuyên viên C")).toBeInTheDocument();
    expect(screen.getByText("Tiếp nhận hồ sơ")).toBeInTheDocument();
  });

  it("preserves unsaved case assessment value on 409 conflict and keeps the timeline read-only", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.upsertCaseAssessment.mockRejectedValue(
      buildApiError("Stale case_assessment update. Expected version 2, current version is 3.", 409),
    );

    renderApp(["/search?event_tab=X%E1%BB%AD+l%C3%BD"]);

    expect(await screen.findByText("Thông tin xử lý")).toBeInTheDocument();
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Kết quả" }));
    fireEvent.change(screen.getByLabelText("Kết quả"), { target: { value: "Đề xuất trình ký" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Kết quả" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Không thể lưu vì bước xử lý đã bị thay đổi hoặc hồ sơ đã ở trạng thái kết thúc. Tải lại workspace rồi thử lại.",
    );
    expect(screen.getByLabelText("Kết quả")).toHaveValue("Đề xuất trình ký");
    expect(screen.getByText("Tiếp nhận hồ sơ")).toBeInTheDocument();
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("shows only direct case-linked certificates inside event steps and does not fabricate site-wide business eligibility", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(
      buildCaseWorkspace({
        linked_gxp_certificates: [
          buildCaseWorkspace().linked_gxp_certificates[0],
          {
            ...buildCaseWorkspace().linked_gxp_certificates[0],
            certificate_id: "cert-a-old",
            latest_flag: false,
            certificate_number: "533/GCN-QLD",
            issue_date: "2021-09-14",
            expiry_date: "2027-09-14",
            status: "superseded",
            scope_summary: "Thuốc không vô trùng cũ",
          },
        ],
        linked_business_eligibility_certificates: [],
      }),
    );

    renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /Chứng nhận GxP/ }));
    expect(await screen.findByRole("heading", { name: "Chứng nhận GxP liên kết" })).toBeInTheDocument();
    expect(screen.getAllByText("195/GCN-QLD").length).toBeGreaterThan(0);
    expect(screen.getAllByText("533/GCN-QLD").length).toBeGreaterThan(0);
    expect(screen.queryByText("ADMIN-001")).not.toBeInTheDocument();
    expect(screen.queryByText("B-001")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Chứng nhận ĐĐK/ }));
    expect(await screen.findByText("Chưa có chứng nhận ĐĐK liên kết")).toBeInTheDocument();
    expect(screen.queryByText("1201/ĐKKDD-BYT")).not.toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
  });

  it("keeps dashboard drilldown links aligned with the accepted facility-level semantics", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp(["/"]);

    await screen.findByText("Bảng điều phối nghiệp vụ");

    expect(screen.getByText("Cơ sở có hồ sơ đang xử lý")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở chờ kiểm tra")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở chờ cấp chứng nhận")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở có GCN còn hiệu lực")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở có GCN sắp hết hạn 90 ngày")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở có thay đổi chưa hoàn tất")).toBeInTheDocument();
  });

  it("renders the GxP certificate workspace as list plus detail and keeps search results untouched when switching certificates", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);
    apiMocks.listSiteGxpCertificates.mockResolvedValue({
      items: [
        {
          certificate_id: "cert-a-new",
          site_id: "site-1",
          case_id: "case-1",
          certificate_type: "GMP",
          line_code: "A",
          context_match_kind: "exact_line",
          latest_flag: true,
          certificate_number: "195/GCN-QLD",
          issue_date: "2025-04-17",
          expiry_date: "2027-04-17",
          applicable_standard: "WHO-GMP",
          issuing_authority: "Cục Quản lý Dược Việt Nam",
          status: "active",
        },
        {
          certificate_id: "cert-a-old",
          site_id: "site-1",
          case_id: "case-1",
          certificate_type: "GMP",
          line_code: "A",
          context_match_kind: "exact_line",
          latest_flag: false,
          certificate_number: "533/GCN-QLD",
          issue_date: "2021-09-14",
          expiry_date: "2027-09-14",
          applicable_standard: "WHO-GMP",
          issuing_authority: "Cục Quản lý Dược Việt Nam",
          status: "superseded",
        },
      ],
    });
    apiMocks.getGxpCertificateDetail
      .mockResolvedValueOnce({
        certificate_id: "cert-a-new",
        row_version: 3,
        site_id: "site-1",
        case_id: "case-1",
        certificate_type: "GMP",
        line_code: "A",
        issuance_basis: "inspection_case",
        latest_flag: true,
        certificate_number: "195/GCN-QLD",
        issue_date: "2025-04-17",
        expiry_date: "2027-04-17",
        applicable_standard: "WHO-GMP",
        issuing_authority: "Cục Quản lý Dược Việt Nam",
        status: "active",
        facility_name: "Nhà máy A",
        address: "KCN A",
        company_name: "Công ty A",
        company_legal_address: "123 Trụ sở chính",
        scope_summary: "Thuốc không vô trùng",
        limitation_text: null,
        source_description: "Đợt kiểm tra GMP ngày 10-01-2025",
        action_readiness: [
          {
            action_key: "promote_current",
            label: "Đặt làm chứng nhận hiện hành",
            available: true,
            reason_code: null,
            required_permissions: ["certificate.approve"],
            expected_version: 3,
          },
        ],
      })
      .mockResolvedValueOnce({
        certificate_id: "cert-a-old",
        site_id: "site-1",
        case_id: "case-1",
        certificate_type: "GMP",
        line_code: "A",
        issuance_basis: "inspection_case",
        latest_flag: false,
        certificate_number: "533/GCN-QLD",
        issue_date: "2021-09-14",
        expiry_date: "2027-09-14",
        applicable_standard: "WHO-GMP",
        issuing_authority: "Cục Quản lý Dược Việt Nam",
        status: "superseded",
        facility_name: "Nhà máy A",
        address: "KCN A",
        company_name: "Công ty A",
        company_legal_address: "123 Trụ sở chính",
        scope_summary: "Thuốc không vô trùng cũ",
        limitation_text: null,
        source_description: "Đợt kiểm tra GMP ngày 14-09-2021",
      });

    renderApp(["/search?facility_tab=Gi%E1%BA%A5y%20ch%E1%BB%A9ng%20nh%E1%BA%ADn%20GxP"]);

    expect(await screen.findByRole("heading", { name: "Danh mục GCN GxP" })).toBeInTheDocument();
    expect(document.querySelector(".certificate-workspace-split.master-detail-split.master-detail-split-certificate")).not.toBeNull();
    expect(document.querySelector(".certificate-list-panel.master-list-pane")).not.toBeNull();
    expect(document.querySelector(".certificate-detail-panel.detail-pane")).not.toBeNull();
    const gxpCertificateTable = document.querySelector(".certificate-history-table");
    expect(within(gxpCertificateTable as HTMLElement).queryByRole("columnheader", { name: "GxP" })).not.toBeInTheDocument();
    expect(within(gxpCertificateTable as HTMLElement).getByRole("columnheader", { name: "DC" })).toBeInTheDocument();
    expect(screen.getByText("195/GCN-QLD")).toBeInTheDocument();
    expect(screen.getByText("533/GCN-QLD")).toBeInTheDocument();
    expect(await screen.findByText("Thuốc không vô trùng")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đặt làm chứng nhận hiện hành" })).toBeEnabled();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText("533/GCN-QLD"));

    await waitFor(() => {
      expect(apiMocks.getGxpCertificateDetail).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText("Thuốc không vô trùng cũ")).toBeInTheDocument();
    expect(screen.getByText("Đã được thay thế")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.listSiteGxpCertificates).toHaveBeenCalledTimes(1);
  });

  it("issues from the selected case and refreshes only its workspace without promoting the new certificate", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    const certificateIssueReadiness = {
      action_key: "issue_certificate",
      label: "Cấp chứng nhận GxP",
      available: true,
      reason_code: null,
      required_permissions: ["certificate.issue"],
      certificate_type: "GMP",
      issuance_basis: "inspection_case",
    };
    apiMocks.getCaseWorkspace
      .mockResolvedValueOnce(buildCaseWorkspace({ certificate_issue_readiness: certificateIssueReadiness }))
      .mockResolvedValueOnce(buildCaseWorkspace({ certificate_issue_readiness: { ...certificateIssueReadiness, available: false, reason_code: "certificate_already_issued" } }));
    apiMocks.issueGxpCertificate.mockResolvedValue({ certificate_id: "cert-new", row_version: 1, latest_flag: false });

    renderApp(["/search"]);

    fireEvent.click(await screen.findByRole("button", { name: "Chứng nhận GxP" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cấp chứng nhận GxP" }));
    const dialog = screen.getByRole("dialog", { name: "Cấp giấy chứng nhận GxP" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Số GCN" }), { target: { value: "GCN-NEW" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cấp giấy chứng nhận" }));

    await waitFor(() => expect(apiMocks.issueGxpCertificate).toHaveBeenCalledWith(
      "site-1",
      expect.objectContaining({
        case_id: "case-1",
        certificate_type: "GMP",
        issuance_basis: "inspection_case",
        certificate_number: "GCN-NEW",
        scopes: [],
      }),
      expect.objectContaining({ username: "operator.local", role: "inspector" }),
      true,
      null,
    ));
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.promoteGxpCertificateCurrent).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled();
  });

  it.each([
    { kind: "GxP", tab: "Giấy chứng nhận GxP", list: "listSiteGxpCertificates", load: "getGxpCertificateDetail", id: "certificate_id", table: "Danh mục GCN GxP" },
    { kind: "ĐĐK", tab: "Giấy chứng nhận đủ điều kiện", list: "listSiteBusinessEligibilityCertificates", load: "getBusinessEligibilityDetail", id: "business_eligibility_certificate_id", table: "Danh mục GCN đủ điều kiện" },
  ] as const)("$kind keeps focus separate from requests and rejects a late A detail after B selection", async ({ tab, list, load, id, table }) => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [] }));
    const item = { site_id: "site-1", certificate_number: "SAME-REFERENCE", certificate_type: "GMP", line_code: "A", production_line_id: "line-uuid-1", context_match_kind: "exact_line", latest_flag: false, issue_date: null, issued_on: null, expiry_date: null, issuance_sequence_text: "1" };
    apiMocks[list].mockResolvedValue({ items: [{ ...item, [id]: "certificate-A" }, { ...item, [id]: "certificate-B" }], issue_readiness: null });
    let resolveA!: (value: unknown) => void;
    let resolveB!: (value: unknown) => void;
    apiMocks[load].mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; })).mockImplementationOnce(() => new Promise(resolve => { resolveB = resolve; }));
    renderApp([`/search?gxp_type=GMP&facility_tab=${encodeURIComponent(tab)}`]);
    const rows = within(await screen.findByRole("table", { name: table })).getAllByRole("row").slice(1);
    await waitFor(() => expect(apiMocks[load]).toHaveBeenCalledTimes(1));
    act(() => rows[0].focus());
    for (const key of ["ArrowDown", "Home", "End", "ArrowUp", "ArrowDown"]) fireEvent.keyDown(document.activeElement!, { key });
    expect(rows[1]).toHaveFocus();
    expect(rows[0]).toHaveAttribute("aria-selected", "true");
    expect(apiMocks[load]).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(rows[1], { key: "Enter" });
    await waitFor(() => expect(apiMocks[load]).toHaveBeenCalledTimes(2));
    expect(apiMocks[load].mock.calls.map(call => call[0])).toEqual(["certificate-A", "certificate-B"]);
    expect(screen.getByText(/Đang tải chi tiết/)).toBeInTheDocument();
    const detail = { ...item, [id]: "certificate-B", row_version: 3, facility_name: "B authoritative detail", linked_gxp_certificates: [], scopes: [], action_readiness: [] };
    await act(async () => resolveB(detail));
    expect(await screen.findByText("B authoritative detail")).toBeInTheDocument();
    await act(async () => resolveA({ ...detail, [id]: "certificate-A", facility_name: "A stale detail" }));
    expect(screen.queryByText("A stale detail")).not.toBeInTheDocument();
    expect(rows[1]).toHaveFocus();
    fireEvent.keyDown(rows[1], { key: " " });
    fireEvent.click(rows[1]);
    expect(apiMocks[load]).toHaveBeenCalledTimes(2);
    expect(apiMocks[list]).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
  });

  it.each([
    { tab: "Giấy chứng nhận GxP", list: "listSiteGxpCertificates", load: "getGxpCertificateDetail", id: "certificate_id", table: "Danh mục GCN GxP" },
    { tab: "Giấy chứng nhận đủ điều kiện", list: "listSiteBusinessEligibilityCertificates", load: "getBusinessEligibilityDetail", id: "business_eligibility_certificate_id", table: "Danh mục GCN đủ điều kiện" },
  ] as const)("$tab clears A-owned error in B's first commit and shows B's own failure", async ({ tab, list, load, id, table }) => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [] }));
    apiMocks[list].mockResolvedValue({ items: [{ [id]: "certificate-A" }, { [id]: "certificate-B" }], issue_readiness: null });
    let rejectB!: (error: Error) => void;
    apiMocks[load].mockRejectedValueOnce(new Error("Error owned by certificate A")).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectB = reject; }));
    renderApp([`/search?gxp_type=GMP&facility_tab=${encodeURIComponent(tab)}`]);
    await screen.findByRole("table", { name: table });
    await waitFor(() => expect(apiMocks[load]).toHaveBeenCalledTimes(1));
    await screen.findByText("Error owned by certificate A");
    const snapshots: boolean[] = [];
    contextCommit.observe.mockImplementation(() => {
      const rows = screen.queryByRole("table", { name: table })?.querySelectorAll("tbody tr");
      if (rows?.[1]?.getAttribute("aria-selected") === "true") snapshots.push(Boolean(screen.queryByText("Error owned by certificate A")));
    });
    fireEvent.click(within(screen.getByRole("table", { name: table })).getAllByRole("row")[2]);
    await waitFor(() => expect(apiMocks[load]).toHaveBeenCalledTimes(2));
    expect(snapshots.length).toBeGreaterThan(0);
    expect(snapshots.every(value => !value)).toBe(true);
    expect(screen.getByText(/Đang tải chi tiết/)).toBeInTheDocument();
    await act(async () => rejectB(new Error("B own failure")));
    expect(await screen.findByRole("alert")).toHaveTextContent("B own failure");
    expect(apiMocks[load]).toHaveBeenCalledTimes(2);
  });

  it("refreshes only the selected certificate after an edit conflict and keeps the edit form open", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);
    apiMocks.listSiteGxpCertificates.mockResolvedValue({
      items: [{
        certificate_id: "cert-stale", site_id: "site-1", case_id: "case-1", certificate_type: "GMP", line_code: "A",
        context_match_kind: "exact_line", latest_flag: true, certificate_number: "GCN-OLD", issue_date: "2026-09-01",
        expiry_date: "2027-09-01", applicable_standard: "WHO-GMP", issuing_authority: null, status: "active",
      }],
    });
    const detail = {
      certificate_id: "cert-stale", row_version: 7, site_id: "site-1", case_id: "case-1", certificate_type: "GMP", line_code: "A",
      issuance_basis: "inspection_case", latest_flag: true, certificate_number: "GCN-OLD", issue_date: "2026-09-01", expiry_date: "2027-09-01",
      applicable_standard: "WHO-GMP", issuing_authority: null, status: "active", facility_name: "Nhà máy A", address: null,
      company_name: "Công ty A", company_legal_address: null, scope_summary: "Summary must not be edited", limitation_text: null,
      source_description: null, scopes: [{ id: "scope-1", scope_key: "alpha", scope_text: "Alpha", language_code: "vi", sort_order: 1 }],
      action_readiness: [{ action_key: "edit_latest_version", label: "Cập nhật chứng nhận", available: true, reason_code: null, required_permissions: ["certificate.edit"], expected_version: 7 }],
    };
    apiMocks.getGxpCertificateDetail.mockResolvedValueOnce(detail).mockResolvedValueOnce({ ...detail, row_version: 8, certificate_number: "GCN-NEW" });
    apiMocks.upsertGxpCertificateLatestVersion.mockRejectedValue(Object.assign(new Error("409 conflict"), { status: 409 }));

    renderApp(["/search?facility_tab=Gi%E1%BA%A5y%20ch%E1%BB%A9ng%20nh%E1%BA%ADn%20GxP"]);

    fireEvent.click(await screen.findByRole("button", { name: "Cập nhật chứng nhận" }));
    const dialog = screen.getByRole("dialog", { name: "Sửa giấy chứng nhận GxP" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(apiMocks.getGxpCertificateDetail).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("alert")).toHaveTextContent("Dữ liệu chứng nhận đã thay đổi");
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.listSiteGxpCertificates).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
    expect(screen.getByText("GCN-NEW")).toBeInTheDocument();
  });

  it("renders the business eligibility workspace as list plus detail with linked GxP basis", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);
    apiMocks.listSiteBusinessEligibilityCertificates.mockResolvedValue({
      items: [
        {
          business_eligibility_certificate_id: "dkkd-5",
          site_id: "site-1",
          company_id: "company-1",
          latest_flag: true,
          certificate_number: "1201/ĐKKDD-BYT",
          issued_on: "2025-06-09",
          issuance_sequence_text: "5",
          current_status_text: "Chưa cấp chứng chỉ",
        },
      ],
    });
    apiMocks.getBusinessEligibilityDetail.mockResolvedValue({
      business_eligibility_certificate_id: "dkkd-5",
      site_id: "site-1",
      company_id: "company-1",
      latest_flag: true,
      certificate_number: "1201/ĐKKDD-BYT",
      issued_on: "2025-06-09",
      decision_reference: "QĐ-1201",
      issuance_sequence_text: "5",
      issuance_history_text: "Lần 1, Lần 2, Lần 3, Lần 4, Lần 5",
      company_name: "Công ty A",
      company_legal_address: "123 Trụ sở chính",
      facility_name: "Nhà máy A",
      address: "KCN A",
      professional_responsible_person_name: "Nguyễn Khắc Minh",
      quality_assurance_person_name: "Võ Việt Hùng",
      professional_qualification_text: "Dược sĩ đại học",
      professional_license_number: "2241/BD-CCHND",
      professional_license_issued_on: "2013-08-08",
      professional_license_issuer: "Sở Y tế",
      responsible_license_issued_on: "2020-07-14",
      responsible_license_issuer: "Sở Y tế Hà Tĩnh",
      business_activity_text: "Bán buôn thuốc",
      current_status_text: "Chưa cấp chứng chỉ",
      handled_by_name: "Hà Hoàng Phương",
      application_dossier_reference: "HS-001",
      replaces_certificate_number: "703/ĐKKDD-BYT",
      replaced_by_certificate_number: null,
      linked_gxp_certificates: [
        {
          certificate_id: "cert-a-new",
          certificate_type: "GMP",
          line_code: "A",
          certificate_number: "195/GCN-QLD",
          issue_date: "2025-04-17",
          link_role: "source_certificate",
        },
      ],
    });

    renderApp(["/search?facility_tab=Gi%E1%BA%A5y%20ch%E1%BB%A9ng%20nh%E1%BA%ADn%20%C4%91%E1%BB%A7%20%C4%91i%E1%BB%81u%20ki%E1%BB%87n"]);

    expect(await screen.findByRole("heading", { name: "Danh mục GCN đủ điều kiện" })).toBeInTheDocument();
    expect(document.querySelector(".eligibility-workspace-split.master-detail-split.master-detail-split-eligibility")).not.toBeNull();
    expect(document.querySelector(".certificate-list-panel.master-list-pane")).not.toBeNull();
    expect(document.querySelector(".certificate-detail-panel.detail-pane")).not.toBeNull();
    expect(screen.getByRole("columnheader", { name: "Số GCN" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Lần" })).toBeInTheDocument();
    expect(screen.getByText("1201/ĐKKDD-BYT")).toBeInTheDocument();
    expect(await screen.findByText("Nguyễn Khắc Minh")).toBeInTheDocument();
    expect(screen.getByText("Võ Việt Hùng")).toBeInTheDocument();
    expect(screen.getByText("703/ĐKKDD-BYT")).toBeInTheDocument();
    expect(screen.getByText(/GMP A · 195\/GCN-QLD · 17-04-2025/)).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.listSiteBusinessEligibilityCertificates).toHaveBeenCalledTimes(1);
    expect(apiMocks.getBusinessEligibilityDetail).toHaveBeenCalledTimes(1);
  });

  it("shows certificate-tab empty states without rendering fake detail forms", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);
    apiMocks.listSiteGxpCertificates.mockResolvedValue({ items: [] });

    renderApp(["/search?facility_tab=Gi%E1%BA%A5y%20ch%E1%BB%A9ng%20nh%E1%BA%ADn%20GxP"]);

    expect(await screen.findByText("Chưa có giấy chứng nhận GxP")).toBeInTheDocument();
    expect(screen.queryByText("Nguồn gốc")).not.toBeInTheDocument();
  });

  it("keeps q distinct from facility_name and exposes it as an active filter", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?q=KT-2026-001&facility_name=Factory%20Alpha"]);

    await waitFor(() => expect(apiMocks.searchFacilities).toHaveBeenCalled());
    expect(apiMocks.searchFacilities.mock.calls[0][0]).toMatchObject({ q: "KT-2026-001", facility_name: "Factory Alpha" });
    expect(await screen.findByText("Từ khóa: KT-2026-001")).toBeInTheDocument();
  });

  it("builds an exact Dashboard GLP deep link and opens its selected history", async () => {
    const resultKey = "site-1:GLP:canonical:line-glp";
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.getDashboardSummary.mockResolvedValue({
      total_facilities: 1, total_cases: 1, active_cases: 1, waiting_inspection: 0,
      waiting_certificate_decision: 0, active_certificates: 0, expiring_certificates_90_days: 0,
      incomplete_changes: 0,
      queue: [{ case_id: "case-glp", site_id: "site-1", result_key: resultKey, facility_name: "Factory GLP", company_name: "Company", gxp_type: "GLP", state: "planned", reference_code: "KT-2026-GLP-001", opened_year: 2026 }],
    });
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult({ result_key: resultKey, gxp_type: "GLP", production_line_id: "line-glp", line_code: "A" })], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [{ id: "case-glp", source_type: "case", title: "GLP case", occurred_on: "2026-01-01", state: "planned" }] }));
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    renderApp(["/"]);
    const link = await screen.findByRole("link", { name: "KT-2026-GLP-001" });
    expect(link).toHaveAttribute("href", expect.stringContaining("gxp_type=GLP"));
    expect(link).toHaveAttribute("href", expect.stringContaining("result_key=site-1%3AGLP%3Acanonical%3Aline-glp"));
    fireEvent.click(link);

    await waitFor(() => expect(apiMocks.searchFacilities.mock.calls.at(-1)?.[0]).toMatchObject({ q: "KT-2026-GLP-001", gxp_type: "GLP" }));
    await waitFor(() => expect(apiMocks.getCaseWorkspace.mock.calls.at(-1)?.[0]).toBe("case-glp"));
  });

  it("resolves an explicit result_key on a later page without selecting page one", async () => {
    const target = buildSearchResult({ result_key: "site-1:GLP:canonical:line-target", gxp_type: "GLP", production_line_id: "line-target", line_code: "A" });
    const firstPage = Array.from({ length: 100 }, (_, index) => buildSearchResult({
      result_key: `site-1:GLP:canonical:line-${index}`,
      gxp_type: "GLP",
      production_line_id: `line-${index}`,
      line_code: "A",
    }));
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities
      .mockResolvedValueOnce({ items: firstPage, total_count: 101, offset: 0, limit: 100 })
      .mockResolvedValueOnce({ items: [target], total_count: 101, offset: 100, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?gxp_type=GLP&result_key=site-1%3AGLP%3Acanonical%3Aline-target"]);

    await waitFor(() => expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-target"));
    expect(apiMocks.searchFacilities.mock.calls.map((call) => call[0].offset)).toEqual([0, 100]);
  });

  it.each([
    ["canonical UUID", "production_line_id=p2"],
    ["Site UUID", "site_id=site-2"],
    ["line hint", "line_code=B"],
    ["GxP context", "context_gxp=GLP"],
  ])("fails safe for an exact result_key with a contradictory %s", async (_label, contradictoryHint) => {
    const target = buildSearchResult({
      result_key: "site-1:GMP:canonical:p1",
      production_line_id: "p1",
      production_line_identity_state: "canonical",
      line_code: "A",
    });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [target], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp([`/search?result_key=site-1%3AGMP%3Acanonical%3Ap1&${contradictoryHint}`]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
  });

  it("accepts exact result_key with mutually consistent canonical identity hints", async () => {
    const target = buildSearchResult({
      result_key: "site-1:GMP:canonical:p1",
      production_line_id: "p1",
      production_line_identity_state: "canonical",
      line_code: "A",
    });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [target], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?result_key=site-1%3AGMP%3Acanonical%3Ap1&site_id=site-1&context_gxp=GMP&production_line_id=p1&line_code=A"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p1"));
  });

  it("fails safe when an explicit result_key is stale instead of opening the first row", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult({ result_key: "site-1:GMP:canonical:other" })], total_count: 1, offset: 0, limit: 100 });

    renderApp(["/search?result_key=site-1%3AGMP%3Acanonical%3Amissing"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
    expect(screen.getByRole("row", { name: /1\.1A/ })).toHaveAttribute("aria-selected", "false");

    fireEvent.click(screen.getByText("1.1A"));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps a stale explicit result key terminal after multi-page exhaustion", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities
      .mockResolvedValueOnce({ items: Array.from({ length: 100 }, (_, index) => buildSearchResult({ result_key: `site-1:GMP:canonical:other-${index}` })), total_count: 101, offset: 0, limit: 100 })
      .mockResolvedValueOnce({ items: [buildSearchResult({ result_key: "site-1:GMP:canonical:other-final" })], total_count: 101, offset: 100, limit: 100 });

    renderApp(["/search?result_key=site-1%3AGMP%3Acanonical%3Amissing"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMocks.searchFacilities.mock.calls.map((call) => call[0].offset)).toEqual([0, 100]);
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
  });

  it("loads the exact deep-linked line and history in the shared pane without overriding facility or event tabs", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult({ result_key: "site-1:GMP:canonical:line-uuid-1" })], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [
      { ...buildWorkspace().history[0], id: "case-other", occurred_on: "2026-01-01", state: "planned" },
      { ...buildWorkspace().history[0], id: "case-target", occurred_on: "2026-01-02", state: "planned" },
    ] }));
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search?result_key=site-1%3AGMP%3Acanonical%3Aline-uuid-1&history_id=case-target&facility_tab=Th%C3%B4ng%20tin%20chung&event_tab=Ki%E1%BB%83m%20tra"]);
    await waitFor(() => expect(apiMocks.getCaseWorkspace.mock.calls.at(-1)?.[0]).toBe("case-target"));
    expect(container.querySelectorAll(".history-table")).toHaveLength(1);
    expect(container.querySelector(".search-master-history .history-table tr.selected")).toHaveTextContent("02-01-2026");
    expect(container.querySelector(".facility-table tr.selected")).not.toBeNull();
    expect(screen.getByRole("tab", { name: "Thông tin chung" })).toHaveAttribute("aria-selected", "true");
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-uuid-1");
    fireEvent.click(screen.getByRole("tab", { name: "Các đợt kiểm tra & thay đổi" }));
    expect(await screen.findByRole("heading", { name: "Kế hoạch kiểm tra" })).toBeInTheDocument();
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
  });

  it("does not substitute the first history item for a stale deep-link history id", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [{ id: "case-other", source_type: "case", title: "Other", occurred_on: "2026-01-01", state: "planned" }] }));

    renderApp(["/search?history_id=case-missing"]);
    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy hồ sơ được liên kết");
    expect(apiMocks.getCaseWorkspace).not.toHaveBeenCalled();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMocks.getCaseWorkspace).not.toHaveBeenCalled();
  });

  it("rehydrates a later same-route deep link without clobbering its tabs or target", async () => {
    const first = buildSearchResult({ result_key: "site-1:GMP:canonical:line-first", production_line_id: "line-first" });
    const second = buildSearchResult({ result_key: "site-1:GLP:canonical:line-second", gxp_type: "GLP", production_line_id: "line-second" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockImplementation((params: { gxp_type: string; q?: string }) => Promise.resolve({
      items: [params.q === "B" ? second : first], total_count: 1, offset: 0, limit: 100,
    }));
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace({ history: [{ id: "case-2", source_type: "case", title: "Case two", occurred_on: "2026-01-02", state: "planned" }] }));
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    render(
      <MemoryRouter initialEntries={["/search?q=A&gxp_type=GMP&result_key=site-1%3AGMP%3Acanonical%3Aline-first&facility_tab=Th%C3%B4ng%20tin%20chung"]}>
        <SearchRouteNavigator to="/search?q=B&gxp_type=GLP&result_key=site-1%3AGLP%3Acanonical%3Aline-second&history_id=case-2&facility_tab=C%C3%A1c%20%C4%91%E1%BB%A3t%20ki%E1%BB%83m%20tra%20%26%20thay%20%C4%91%E1%BB%95i&event_tab=Ki%E1%BB%83m%20tra" />
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-first"));
    await act(async () => { await Promise.resolve(); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Đi tới ngữ cảnh khác" })); });
    await waitFor(() => expect(screen.getByTestId("route-location")).toHaveTextContent("gxp_type=GLP"));
    await waitFor(() => expect(apiMocks.searchFacilities.mock.calls.some((call) => call[0].gxp_type === "GLP")).toBe(true));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-second"));
    await waitFor(() => expect(apiMocks.getCaseWorkspace.mock.calls.at(-1)?.[0]).toBe("case-2"));
    expect(apiMocks.searchFacilities.mock.calls.at(-1)?.[0]).toMatchObject({ q: "B", gxp_type: "GLP" });
    expect(screen.getByRole("tab", { name: "Các đợt kiểm tra & thay đổi" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("button", { name: "Kiểm tra" })).toHaveAttribute("aria-current", "step");
    const selectedTab = screen.getByRole("tab", { name: "Các đợt kiểm tra & thay đổi" });
    expect(selectedTab).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tabpanel", { name: "Các đợt kiểm tra & thay đổi" })).toHaveAttribute("id", selectedTab.getAttribute("aria-controls"));
    expect(within(screen.getByRole("tablist", { name: "Tab nghiệp vụ cơ sở" })).getAllByRole("tab").filter((tab) => tab.tabIndex === 0)).toHaveLength(1);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Quay lại ngữ cảnh trước" })); });
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("line-first"));
    expect(apiMocks.searchFacilities.mock.calls.at(-1)?.[0]).toMatchObject({ q: "A", gxp_type: "GMP" });
  });

  it("resolves canonical compatibility hints by UUID rather than shared line code", async () => {
    const firstCanonical = buildSearchResult({ result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", line_code: "A" });
    const secondCanonical = buildSearchResult({ result_key: "site-1:GMP:canonical:p2", production_line_id: "p2", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [firstCanonical, secondCanonical], total_count: 2, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?site_id=site-1&context_gxp=GMP&production_line_id=p2"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p2"));
  });

  it("R13 resolves a production_line_id-only URL as an explicit canonical target", async () => {
    const p1 = buildSearchResult({ result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", line_code: "A" });
    const p2 = buildSearchResult({ result_key: "site-1:GMP:canonical:p2", production_line_id: "p2", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [p1, p2], total_count: 2, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?production_line_id=p2"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p2"));
    expect(apiMocks.getFacilityWorkspace.mock.calls.some((call) => call[6] === "p1")).toBe(false);
  });

  it("R14 keeps a stale production_line_id-only URL terminal and does not open the first row", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult({ production_line_id: "p1", line_code: "A" })], total_count: 1, offset: 0, limit: 100 });

    renderApp(["/search?production_line_id=missing"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
    expect(screen.getByRole("row", { name: /1\.1A/ })).toHaveAttribute("aria-selected", "false");
  });

  it("R15 resolves a line_code-only URL only to its unique legacy-unlinked context", async () => {
    const canonical = buildSearchResult({ result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", line_code: "A" });
    const legacy = buildSearchResult({ result_key: "site-1:GMP:legacy:A", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [canonical, legacy], total_count: 2, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?line_code=A"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBeNull());
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[4]).toBe("A");
    expect(apiMocks.getFacilityWorkspace.mock.calls.some((call) => call[6] === "p1")).toBe(false);
  });

  it("R16 fails safe for an ambiguous line_code-only URL", async () => {
    const firstLegacy = buildSearchResult({ result_key: "site-1:GMP:legacy:A:one", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    const secondLegacy = buildSearchResult({ result_key: "site-1:GLP:legacy:A:two", gxp_type: "GMP", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [firstLegacy, secondLegacy], total_count: 2, offset: 0, limit: 100 });

    renderApp(["/search?line_code=A"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
  });

  it("R17 normalizes a legacy line hint before resolving its unique context", async () => {
    const legacy = buildSearchResult({ result_key: "site-1:GMP:legacy:A", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [legacy], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?site_id=site-1&context_gxp=GMP&line_code=%20A%20"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBeNull());
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[4]).toBe("A");
  });

  it("R18 treats a blank line_code as no legacy identity and never synthesizes a UUID", async () => {
    const canonical = buildSearchResult({ result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [canonical], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?line_code=%20%20%20"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p1"));
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[4]).toBe("A");
  });

  it("R19 resolves a GLP production_line_id-only target without synthesizing a GMP filter", async () => {
    const gmp = buildSearchResult({ result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", line_code: "A" });
    const glp = buildSearchResult({ result_key: "site-1:GLP:canonical:p2", gxp_type: "GLP", production_line_id: "p2", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [gmp, glp], total_count: 2, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?production_line_id=p2"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[3]).toBe("GLP"));
    expect(apiMocks.searchFacilities.mock.calls[0][0].gxp_type).toBeNull();
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p2");
  });

  it("R20 resolves a GLP line_code-only target without selecting a same-code canonical row", async () => {
    const canonical = buildSearchResult({ result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", line_code: "A" });
    const legacyGlp = buildSearchResult({ result_key: "site-1:GLP:legacy:A", gxp_type: "GLP", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [canonical, legacyGlp], total_count: 2, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?line_code=A"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[3]).toBe("GLP"));
    expect(apiMocks.searchFacilities.mock.calls[0][0].gxp_type).toBeNull();
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBeNull();
  });

  it("R21 lets context_gxp constrain a production_line_id target without injecting gxp_type", async () => {
    const gmp = buildSearchResult({ result_key: "site-1:GMP:canonical:p2", production_line_id: "p2", line_code: "A" });
    const glp = buildSearchResult({ result_key: "site-1:GLP:canonical:p2", gxp_type: "GLP", production_line_id: "p2", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [glp], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?site_id=site-1&context_gxp=GLP&production_line_id=p2"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[3]).toBe("GLP"));
    expect(apiMocks.searchFacilities.mock.calls[0][0]).toMatchObject({ gxp_type: "GLP" });
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe(glp.production_line_id);
    expect(gmp.gxp_type).toBe("GMP");
  });

  it("R22 fails safe after discovering a second compatible legacy line on a later page", async () => {
    const firstPage = [
      buildSearchResult({ result_key: "site-1:GMP:legacy:A:one", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" }),
      ...Array.from({ length: 99 }, (_, index) => buildSearchResult({ result_key: `site-1:GMP:canonical:other-${index}`, production_line_id: `other-${index}`, line_code: "B" })),
    ];
    const secondLegacy = buildSearchResult({ result_key: "site-2:GMP:legacy:A:two", site_id: "site-2", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities
      .mockResolvedValueOnce({ items: firstPage, total_count: 101, offset: 0, limit: 100 })
      .mockResolvedValueOnce({ items: [secondLegacy], total_count: 101, offset: 100, limit: 100 });

    renderApp(["/search?line_code=A"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(apiMocks.searchFacilities.mock.calls.map((call) => call[0].offset)).toEqual([0, 100]);
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
  });

  it("R23 resolves a unique compatibility hint only after exhausting later pages", async () => {
    const firstPage = [
      buildSearchResult({ result_key: "site-1:GMP:legacy:A", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" }),
      ...Array.from({ length: 99 }, (_, index) => buildSearchResult({ result_key: `site-1:GMP:canonical:other-${index}`, production_line_id: `other-${index}`, line_code: "B" })),
    ];
    let resolveSecondPage!: (value: { items: ReturnType<typeof buildSearchResult>[]; total_count: number; offset: number; limit: number }) => void;
    const secondPage = new Promise<{ items: ReturnType<typeof buildSearchResult>[]; total_count: number; offset: number; limit: number }>((resolve) => { resolveSecondPage = resolve; });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities
      .mockResolvedValueOnce({ items: firstPage, total_count: 101, offset: 0, limit: 100 })
      .mockReturnValueOnce(secondPage);
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?line_code=A"]);

    await waitFor(() => expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2));
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
    resolveSecondPage({ items: [buildSearchResult({ result_key: "site-1:GMP:canonical:final", production_line_id: "final", line_code: "B" })], total_count: 101, offset: 100, limit: 100 });
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBeNull());
    expect(apiMocks.searchFacilities.mock.calls.map((call) => call[0].offset)).toEqual([0, 100, 0]);
  });

  it("R24 fails safe when a UUID-only target spans more than one regulatory context", async () => {
    const gmp = buildSearchResult({ result_key: "site-1:GMP:canonical:p2", production_line_id: "p2", line_code: "A" });
    const glp = buildSearchResult({ result_key: "site-1:GLP:canonical:p2", gxp_type: "GLP", production_line_id: "p2", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [gmp, glp], total_count: 2, offset: 0, limit: 100 });

    renderApp(["/search?production_line_id=p2"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
  });

  it("R25 fails closed for contradictory explicit gxp_type and context_gxp hints", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp(["/search?gxp_type=GMP&context_gxp=GLP&production_line_id=p2"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("không hợp lệ hoặc mâu thuẫn");
    expect(apiMocks.searchFacilities).not.toHaveBeenCalled();
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
  });

  it("R26 resolves an exact GLP result_key without a synthesized GMP filter", async () => {
    const glp = buildSearchResult({ result_key: "site-1:GLP:canonical:p2", gxp_type: "GLP", production_line_id: "p2", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [glp], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?result_key=site-1%3AGLP%3Acanonical%3Ap2"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[3]).toBe("GLP"));
    expect(apiMocks.searchFacilities.mock.calls[0][0].gxp_type).toBeNull();
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p2");
  });

  it("R27 keeps ordinary pagination available after an exact target resolves on page one", async () => {
    const target = buildSearchResult({ result_key: "site-1:GMP:canonical:target", production_line_id: "target", facility_name: "Target GMP" });
    const firstPage = [target, ...Array.from({ length: 99 }, (_, index) => buildSearchResult({
      result_key: `site-1:GMP:canonical:first-${index}`,
      production_line_id: `first-${index}`,
      facility_name: `First GMP ${index}`,
    }))];
    const secondPage = Array.from({ length: 100 }, (_, index) => buildSearchResult({
      result_key: `site-1:GMP:canonical:second-${index}`,
      production_line_id: `second-${index}`,
      facility_name: `Second GMP ${index}`,
    }));
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities
      .mockResolvedValueOnce({ items: firstPage, total_count: 201, offset: 0, limit: 100 })
      .mockResolvedValueOnce({ items: secondPage, total_count: 201, offset: 100, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?gxp_type=GMP&result_key=site-1%3AGMP%3Acanonical%3Atarget"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("target"));
    const scrollRegion = screen.getByTestId("facility-table-scroll");
    Object.defineProperties(scrollRegion, {
      scrollTop: { configurable: true, value: 260 },
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 400 },
    });
    fireEvent.scroll(scrollRegion);

    await waitFor(() => expect(apiMocks.searchFacilities.mock.calls.map((call) => call[0].offset)).toEqual([0, 100]));
    expect(apiMocks.searchFacilities.mock.calls.every((call) => call[0].gxp_type === "GMP")).toBe(true);
  });

  it("R28 reconciles an unfiltered cross-GxP lookup into a coherent settled result universe", async () => {
    const gmpLookupOnly = buildSearchResult({
      result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", facility_name: "Lookup-only GMP",
    });
    const glpTarget = buildSearchResult({
      result_key: "site-1:GLP:canonical:p2", gxp_type: "GLP", production_line_id: "p2", facility_name: "Settled GLP target",
    });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockImplementation((params: { gxp_type: string | null }) => Promise.resolve(
      params.gxp_type === "GLP"
        ? { items: [glpTarget], total_count: 1, offset: 0, limit: 100 }
        : { items: [gmpLookupOnly, glpTarget], total_count: 2, offset: 0, limit: 100 },
    ));
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?production_line_id=p2"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p2"));
    await waitFor(() => expect(apiMocks.searchFacilities.mock.calls.map((call) => call[0].gxp_type)).toEqual([null, "GLP"]));
    expect(await screen.findByText("Settled GLP target")).toBeInTheDocument();
    expect(screen.queryByText("Lookup-only GMP")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "GLP" })).toHaveAttribute("aria-selected", "true");
  });

  it("R29 restarts settled pagination at the settled GxP offset rather than an unfiltered lookup offset", async () => {
    const target = buildSearchResult({
      result_key: "site-1:GLP:canonical:p2", gxp_type: "GLP", production_line_id: "p2", facility_name: "GLP target",
    });
    const settledFirstPage = [
      target,
      buildSearchResult({ result_key: "site-1:GLP:canonical:p3", gxp_type: "GLP", production_line_id: "p3", facility_name: "GLP second" }),
    ];
    const settledSecondPage = [buildSearchResult({ result_key: "site-1:GLP:canonical:p4", gxp_type: "GLP", production_line_id: "p4", facility_name: "GLP third" })];
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockImplementation((params: { gxp_type: string | null; offset: number }) => Promise.resolve(
      params.gxp_type === null
        ? { items: [buildSearchResult({ facility_name: "Lookup GMP" }), target], total_count: 101, offset: 0, limit: 100 }
        : params.offset === 0
          ? { items: settledFirstPage, total_count: 3, offset: 0, limit: 100 }
          : { items: settledSecondPage, total_count: 3, offset: 2, limit: 100 },
    ));
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?result_key=site-1%3AGLP%3Acanonical%3Ap2"]);

    await waitFor(() => expect(apiMocks.searchFacilities.mock.calls.map((call) => [call[0].gxp_type, call[0].offset])).toEqual([[null, 0], ["GLP", 0]]));
    const scrollRegion = screen.getByTestId("facility-table-scroll");
    Object.defineProperties(scrollRegion, {
      scrollTop: { configurable: true, value: 260 },
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 400 },
    });
    fireEvent.scroll(scrollRegion);

    await waitFor(() => expect(apiMocks.searchFacilities.mock.calls.map((call) => [call[0].gxp_type, call[0].offset])).toEqual([[null, 0], ["GLP", 0], ["GLP", 2]]));
    expect(await screen.findByText("GLP third")).toBeInTheDocument();
  });

  it("R30 resolves an exact page-two target and continues from the settled query's later page", async () => {
    const firstPage = Array.from({ length: 100 }, (_, index) => buildSearchResult({
      result_key: `site-1:GLP:canonical:first-${index}`,
      gxp_type: "GLP",
      production_line_id: `first-${index}`,
    }));
    const target = buildSearchResult({ result_key: "site-1:GLP:canonical:target", gxp_type: "GLP", production_line_id: "target", facility_name: "Page two GLP target" });
    const secondPage = [target, ...Array.from({ length: 99 }, (_, index) => buildSearchResult({
      result_key: `site-1:GLP:canonical:second-${index}`,
      gxp_type: "GLP",
      production_line_id: `second-${index}`,
    }))];
    const thirdPage = [buildSearchResult({ result_key: "site-1:GLP:canonical:third", gxp_type: "GLP", production_line_id: "third", facility_name: "Page three GLP" })];
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities
      .mockResolvedValueOnce({ items: firstPage, total_count: 201, offset: 0, limit: 100 })
      .mockResolvedValueOnce({ items: secondPage, total_count: 201, offset: 100, limit: 100 })
      .mockResolvedValueOnce({ items: thirdPage, total_count: 201, offset: 200, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?gxp_type=GLP&result_key=site-1%3AGLP%3Acanonical%3Atarget"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("target"));
    const scrollRegion = screen.getByTestId("facility-table-scroll");
    Object.defineProperties(scrollRegion, {
      scrollTop: { configurable: true, value: 260 },
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 400 },
    });
    fireEvent.scroll(scrollRegion);

    await waitFor(() => expect(apiMocks.searchFacilities.mock.calls.map((call) => call[0].offset)).toEqual([0, 100, 200]));
    expect(await screen.findByText("Page three GLP")).toBeInTheDocument();
  });

  it("R31 settles a reconciled target without repeated search or workspace requests", async () => {
    const target = buildSearchResult({ result_key: "site-1:GLP:canonical:p2", gxp_type: "GLP", production_line_id: "p2" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockImplementation((params: { gxp_type: string | null }) => Promise.resolve(
      params.gxp_type === "GLP"
        ? { items: [target], total_count: 1, offset: 0, limit: 100 }
        : { items: [buildSearchResult({ production_line_id: "p1" }), target], total_count: 2, offset: 0, limit: 100 },
    ));
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?production_line_id=p2"]);

    await waitFor(() => expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBe("p2"));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2);
    expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(1);
  });

  it("R32 keeps a stale explicit target terminal when ordinary transport is no longer globally blocked", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({
      items: [buildSearchResult({ result_key: "site-1:GMP:canonical:other", production_line_id: "other" })],
      total_count: 1,
      offset: 0,
      limit: 100,
    });

    renderApp(["/search?result_key=site-1%3AGMP%3Acanonical%3Amissing"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
    expect(screen.getByRole("row", { name: /1\.1A/ })).toHaveAttribute("aria-selected", "false");
  });

  it("resolves legacy compatibility hints without selecting a same-code canonical row", async () => {
    const canonical = buildSearchResult({ result_key: "site-1:GMP:canonical:p1", production_line_id: "p1", line_code: "A" });
    const legacy = buildSearchResult({ result_key: "site-1:GMP:legacy:A", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [canonical, legacy], total_count: 2, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());

    renderApp(["/search?site_id=site-1&context_gxp=GMP&line_code=A"]);

    await waitFor(() => expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[6]).toBeNull());
    expect(apiMocks.getFacilityWorkspace.mock.calls.at(-1)?.[4]).toBe("A");
  });

  it("fails safe when compatibility hints are ambiguous", async () => {
    const legacy = buildSearchResult({ result_key: "site-1:GMP:legacy:A:one", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    const duplicate = buildSearchResult({ result_key: "site-1:GMP:legacy:A:two", production_line_id: null, production_line_identity_state: "legacy_unlinked", line_code: "A" });
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [legacy, duplicate], total_count: 2, offset: 0, limit: 100 });

    renderApp(["/search?site_id=site-1&context_gxp=GMP&line_code=A"]);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không tìm thấy ngữ cảnh được liên kết");
    expect(apiMocks.getFacilityWorkspace).not.toHaveBeenCalled();
  });

  it("creates a change request from backend facility readiness and selects the canonical workspace", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    const readyWorkspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "create_change_request"
          ? {
              ...item,
              readiness_status: "available",
              detail: "Có thể tạo yêu cầu thay đổi cho cơ sở đang chọn.",
              required_permissions: ["change_request.edit"],
            }
          : item,
      ),
    });
    const afterWorkspace = buildWorkspace({
      history: [
        {
          id: "change-new",
          source_type: "change_request",
          reference_code: null,
          event_type: "Thay đổi",
          gxp_type: null,
          standard: "Đổi kho",
          occurred_on: "2026-10-05",
          state: "received",
        },
        ...buildWorkspace().history,
      ],
    });
    apiMocks.getFacilityWorkspace.mockResolvedValueOnce(readyWorkspace).mockResolvedValue(afterWorkspace);
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.createChangeRequest.mockResolvedValue({
      change_request_id: "change-new",
      row_version: 1,
      state: "received",
      audit_event_id: "audit-change-new",
      change_detail_id: null,
      change_approval_id: null,
    });
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(
      buildChangeRequestWorkspace({
        id: "change-new",
        row_version: 1,
        legacy_change_request_id: null,
        scope_label: "Đổi kho",
        description: "Điều chỉnh kho bảo quản",
        submitted_on: "2026-10-05",
        requester_name: "QA",
        state: "received",
      }),
    );

    renderApp(["/search"]);

    await waitFor(() => expect(screen.getByRole("button", { name: "Thay đổi" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Thay đổi" }));
    const dialog = await screen.findByRole("dialog", { name: "Tạo yêu cầu thay đổi" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Phạm vi yêu cầu thay đổi" }), { target: { value: "Đổi kho" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Mô tả yêu cầu thay đổi" }), { target: { value: "Điều chỉnh kho bảo quản" } });
    fireEvent.change(within(dialog).getByLabelText("Ngày tạo yêu cầu thay đổi"), { target: { value: "2026-10-05" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Người tạo yêu cầu thay đổi" }), { target: { value: "QA" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Tạo yêu cầu thay đổi" }));

    await waitFor(() => expect(apiMocks.createChangeRequest).toHaveBeenCalledTimes(1));
    expect(apiMocks.createChangeRequest).toHaveBeenCalledWith(
      "site-1",
      {
        scope_label: "Đổi kho",
        description: "Điều chỉnh kho bảo quản",
        submitted_on: "2026-10-05",
        requester_name: "QA",
      },
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    );
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledWith(
      "change-new",
      expect.any(Object),
      true,
      null,
    ));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Tạo yêu cầu thay đổi" })).not.toBeInTheDocument());
    expect(await screen.findByText("Điều chỉnh kho bảo quản")).toBeInTheDocument();
  });

  it("issues an adjusted GxP certificate from backend successor readiness and refreshes authoritative workspaces", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    apiMocks.issueChangeRequestCertificateSuccessor.mockResolvedValue({
      change_request_id: "change-1",
      row_version: 5,
      state: "under_review",
      source_affected_artifact_id: "affected-cert-1",
      issued_artifact_link_id: "issued-cert-1",
      certificate_id: "cert-successor-1",
      audit_event_id: "audit-successor-1",
    });

    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(container.querySelector(".history-table")).not.toBeNull());
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tạo GCN điều chỉnh" }));

    await waitFor(() => expect(apiMocks.issueChangeRequestCertificateSuccessor).toHaveBeenCalledTimes(1));
    expect(apiMocks.issueChangeRequestCertificateSuccessor).toHaveBeenCalledWith(
      "change-1",
      {
        expected_version: 4,
        source_affected_artifact_id: "affected-cert-1",
      },
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    );
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.issueChangeRequestCertificateSuccessor).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("issues an adjusted DDKD from backend successor readiness and refreshes authoritative workspaces", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    apiMocks.issueChangeRequestBusinessEligibilitySuccessor.mockResolvedValue({
      change_request_id: "change-1",
      row_version: 5,
      state: "under_review",
      source_affected_artifact_id: "affected-dkkd-1",
      issued_artifact_link_id: "issued-dkkd-1",
      business_eligibility_certificate_id: "dkkd-successor-1",
      audit_event_id: "audit-dkkd-successor-1",
    });

    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(container.querySelector(".history-table")).not.toBeNull());
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tạo GCN ĐĐK điều chỉnh" }));

    await waitFor(() => expect(apiMocks.issueChangeRequestBusinessEligibilitySuccessor).toHaveBeenCalledTimes(1));
    expect(apiMocks.issueChangeRequestBusinessEligibilitySuccessor).toHaveBeenCalledWith(
      "change-1",
      {
        expected_version: 4,
        source_affected_artifact_id: "affected-dkkd-1",
      },
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    );
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.issueChangeRequestBusinessEligibilitySuccessor).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("promotes issued GxP and DDKD successors with artifact-owned tokens and refreshes authoritative workspaces", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    apiMocks.promoteGxpCertificateCurrent.mockResolvedValue(null);
    apiMocks.promoteBusinessEligibilityCurrent.mockResolvedValue(null);

    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(container.querySelector(".history-table")).not.toBeNull());
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Đặt làm chứng nhận hiện hành" }));

    await waitFor(() => expect(apiMocks.promoteGxpCertificateCurrent).toHaveBeenCalledTimes(1));
    expect(apiMocks.promoteGxpCertificateCurrent).toHaveBeenCalledWith(
      "cert-successor-1",
      11,
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    );
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.promoteGxpCertificateCurrent).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Đặt làm GCN đủ điều kiện hiện hành" }));

    await waitFor(() => expect(apiMocks.promoteBusinessEligibilityCurrent).toHaveBeenCalledTimes(1));
    expect(apiMocks.promoteBusinessEligibilityCurrent).toHaveBeenCalledWith(
      "dkkd-successor-1",
      13,
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    );
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(3));
    expect(apiMocks.promoteBusinessEligibilityCurrent).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("edits an issued GxP successor with its artifact-owned token and refreshes authoritative workspaces", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    apiMocks.getGxpCertificateDetail.mockResolvedValue({
      certificate_id: "cert-successor-1",
      row_version: 11,
      certificate_number: "GMP-DRAFT",
      issue_date: null,
      expiry_date: null,
      scopes: [],
    });
    apiMocks.upsertGxpCertificateLatestVersion.mockResolvedValue(null);

    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(container.querySelector(".history-table")).not.toBeNull());
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));

    await waitFor(() => expect(apiMocks.getGxpCertificateDetail).toHaveBeenCalledWith(
      "cert-successor-1",
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    ));
    const dialog = await screen.findByRole("dialog", { name: "Sửa giấy chứng nhận GxP" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Số GCN" }), {
      target: { value: "GMP-ADJUSTED" },
    });
    fireEvent.change(within(dialog).getByLabelText("Ngày cấp"), {
      target: { value: "2026-10-05" },
    });
    fireEvent.change(within(dialog).getByLabelText("Ngày hết hạn"), {
      target: { value: "2029-10-05" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(apiMocks.upsertGxpCertificateLatestVersion).toHaveBeenCalledTimes(1));
    expect(apiMocks.upsertGxpCertificateLatestVersion).toHaveBeenCalledWith(
      "cert-successor-1",
      {
        expected_version: 11,
        certificate_number: "GMP-ADJUSTED",
        issue_date: "2026-10-05",
        expiry_date: "2029-10-05",
        scopes: [],
        reason: null,
      },
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    );
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.upsertGxpCertificateLatestVersion).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("edits an issued DDKD successor with its artifact-owned token and site GxP basis", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    apiMocks.getBusinessEligibilityDetail.mockResolvedValue({
      business_eligibility_certificate_id: "dkkd-successor-1",
      row_version: 13,
      site_id: "site-1",
      company_id: "company-1",
      latest_flag: false,
      certificate_number: "DDKD-DRAFT",
      issued_on: "2026-10-01",
      expires_on: "2029-10-01",
      notes: "Draft notes",
      decision_reference: null,
      issuance_sequence_text: "2",
      issuance_history_text: null,
      company_name: "Công ty A",
      company_legal_address: null,
      facility_name: "Nhà máy A",
      address: null,
      professional_responsible_person_name: "Responsible Person",
      quality_assurance_person_name: null,
      professional_qualification_text: null,
      professional_license_number: null,
      professional_license_issued_on: null,
      professional_license_issuer: null,
      responsible_license_issued_on: null,
      responsible_license_issuer: null,
      business_activity_text: null,
      current_status_text: null,
      handled_by_name: null,
      application_dossier_reference: null,
      replaces_certificate_number: null,
      replaced_by_certificate_number: null,
      linked_gxp_certificates: [{
        certificate_id: "basis-cert-1",
        certificate_type: "GMP",
        line_code: "A",
        certificate_number: "GMP-001",
        issue_date: "2026-09-01",
        link_role: "source_certificate",
      }],
      action_readiness: [],
    });
    apiMocks.listSiteGxpCertificates.mockResolvedValue({
      items: [{
        certificate_id: "basis-cert-1",
        site_id: "site-1",
        case_id: "case-basis",
        certificate_type: "GMP",
        line_code: "A",
        production_line_id: "line-1",
        production_line_code: "A",
        production_line_identity_state: "canonical",
        context_match_kind: "exact_line",
        latest_flag: true,
        certificate_number: "GMP-001",
        issue_date: "2026-09-01",
        expiry_date: "2029-09-01",
        applicable_standard: "WHO-GMP",
        issuing_authority: null,
        status: "active",
      }],
    });
    apiMocks.upsertBusinessEligibilityLatestVersion.mockResolvedValue(null);

    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(container.querySelector(".history-table")).not.toBeNull());
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cập nhật GCN đủ điều kiện" }));

    await waitFor(() => expect(apiMocks.getBusinessEligibilityDetail).toHaveBeenCalledWith(
      "dkkd-successor-1",
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    ));
    expect(apiMocks.listSiteGxpCertificates).toHaveBeenCalledWith(
      "site-1",
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
      null,
      null,
      null,
    );
    const dialog = await screen.findByRole("dialog", { name: "Cập nhật GCN đủ điều kiện" });
    fireEvent.change(
      within(dialog).getByRole("combobox", { name: /Vai trò căn cứ GMP A · GMP-001/ }),
      { target: { value: "replacement_certificate" } },
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(apiMocks.upsertBusinessEligibilityLatestVersion).toHaveBeenCalledTimes(1));
    expect(apiMocks.upsertBusinessEligibilityLatestVersion).toHaveBeenCalledWith(
      "dkkd-successor-1",
      {
        expected_version: 13,
        certificate_number: "DDKD-DRAFT",
        issued_on: "2026-10-01",
        expires_on: "2029-10-01",
        professional_responsible_person_name: "Responsible Person",
        notes: "Draft notes",
        linked_certificates: [{
          certificate_id: "basis-cert-1",
          link_role: "replacement_certificate",
        }],
        reason: null,
      },
      expect.objectContaining({ username: "operator.local" }),
      true,
      null,
    );
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.upsertBusinessEligibilityLatestVersion).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("refreshes ChangeRequest state after a stale issued-GxP edit without retrying the mutation", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    apiMocks.getGxpCertificateDetail.mockResolvedValue({
      certificate_id: "cert-successor-1",
      row_version: 11,
      certificate_number: "GMP-DRAFT",
      issue_date: null,
      expiry_date: null,
      scopes: [],
    });
    apiMocks.upsertGxpCertificateLatestVersion.mockRejectedValue(
      Object.assign(new Error("Stale certificate update."), { status: 409 }),
    );

    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(container.querySelector(".history-table")).not.toBeNull());
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cập nhật chứng nhận" }));
    const dialog = await screen.findByRole("dialog", { name: "Sửa giấy chứng nhận GxP" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(apiMocks.upsertGxpCertificateLatestVersion).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.upsertGxpCertificateLatestVersion).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog", { name: "Sửa giấy chứng nhận GxP" })).not.toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Stale certificate update.");
  });

  it("refreshes change-request and facility workspaces once after a stale 409 without retrying mutation", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.getChangeRequestWorkspace.mockResolvedValue(buildChangeRequestWorkspace());
    apiMocks.updateChangeRequest.mockRejectedValue(Object.assign(new Error("Stale change_request update."), { status: 409 }));

    const { container } = renderApp(["/search"]);
    await waitFor(() => expect(container.querySelector(".history-table")).not.toBeNull());
    await waitFor(() => expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1));
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));
    expect(await screen.findByText("Điều chỉnh địa chỉ kho bảo quản")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sửa đề nghị" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Phạm vi thay đổi" }), { target: { value: "Đổi địa chỉ mới" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu đề nghị" }));

    await waitFor(() => expect(apiMocks.updateChangeRequest).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(apiMocks.getChangeRequestWorkspace).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(apiMocks.getFacilityWorkspace).toHaveBeenCalledTimes(2));
    expect(apiMocks.updateChangeRequest).toHaveBeenCalledTimes(1);
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("alert")).toHaveTextContent("Stale change_request update.");
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

});
