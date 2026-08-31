import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const apiMocks = vi.hoisted(() => ({
  createInspectionCase: vi.fn(),
  getAppStatus: vi.fn(),
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
  listSiteGxpCertificates: vi.fn().mockResolvedValue({ items: [] }),
  getGxpCertificateDetail: vi.fn().mockResolvedValue(null),
  listSiteBusinessEligibilityCertificates: vi.fn().mockResolvedValue({ items: [] }),
  getBusinessEligibilityDetail: vi.fn().mockResolvedValue(null),
  getDocumentDetail: vi.fn().mockResolvedValue(null),
  getGenerationRun: vi.fn().mockResolvedValue(null),
  listCases: vi.fn().mockResolvedValue([]),
  listCompanies: vi.fn().mockResolvedValue([]),
  listSites: vi.fn().mockResolvedValue([]),
  prepareDocument: vi.fn(),
  renderTemplateDocx: vi.fn(),
}));

const oidcMocks = vi.hoisted(() => ({
  loadGoogleIdentityScript: vi.fn().mockResolvedValue(undefined),
  decodeOidcCredential: vi.fn(),
  isOidcSessionValid: vi.fn(() => false),
}));

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
  apiMocks.createInspectionCase.mockReset();
  apiMocks.getDashboardSummary.mockReset();
  apiMocks.searchFacilities.mockReset();
  apiMocks.getFacilityWorkspace.mockReset();
  apiMocks.getCaseDetail.mockReset();
  apiMocks.getCaseWorkspace.mockReset();
  apiMocks.getChangeRequestWorkspace.mockReset();
  apiMocks.listSiteGxpCertificates.mockReset();
  apiMocks.getGxpCertificateDetail.mockReset();
  apiMocks.listSiteBusinessEligibilityCertificates.mockReset();
  apiMocks.getBusinessEligibilityDetail.mockReset();
  apiMocks.getDocumentDetail.mockReset();
  apiMocks.getGenerationRun.mockReset();
  apiMocks.listCases.mockReset();
  apiMocks.listCompanies.mockReset();
  apiMocks.listSites.mockReset();
  apiMocks.prepareDocument.mockReset();
  apiMocks.renderTemplateDocx.mockReset();

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
  apiMocks.createInspectionCase.mockResolvedValue(null);
  apiMocks.getFacilityWorkspace.mockResolvedValue(null);
  apiMocks.getCaseDetail.mockResolvedValue(null);
  apiMocks.getCaseWorkspace.mockResolvedValue(null);
  apiMocks.getChangeRequestWorkspace.mockResolvedValue(null);
  apiMocks.listSiteGxpCertificates.mockResolvedValue({ items: [] });
  apiMocks.getGxpCertificateDetail.mockResolvedValue(null);
  apiMocks.listSiteBusinessEligibilityCertificates.mockResolvedValue({ items: [] });
  apiMocks.getBusinessEligibilityDetail.mockResolvedValue(null);
  apiMocks.getDocumentDetail.mockResolvedValue(null);
  apiMocks.getGenerationRun.mockResolvedValue(null);
  apiMocks.listCases.mockResolvedValue([]);
  apiMocks.listCompanies.mockResolvedValue([]);
  apiMocks.listSites.mockResolvedValue([]);
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
        detail: "Chưa có create contract owner-safe để mở hồ sơ tái đánh giá mới cho ngữ cảnh GMP.",
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
      submitted_on: "2026-01-15T00:00:00Z",
      dossier_code: "HS-001",
      dossier_reference: "QĐ-TN-01",
      applicant_name: "Nguyễn Văn A",
      assigned_specialist: "Hà Hoàng Phương",
      assigned_specialist_source: "company_master",
    },
    inspection: {
      decision_reference: "QĐ-KT-01",
      decision_document_hint: null,
      plan_start_on: null,
      plan_end_on: null,
      planning_sheet_name: null,
      inspected_on: "2026-08-05",
      inspected_to_on: "2026-08-06",
      executed_on: "2026-08-06T09:30:00Z",
      bbkt_reference: "BBKT-01",
      outcome_result: "Đạt WHO-GMP dây chuyền A",
      team_display_text: null,
    },
    remediation: {
      cycles: [],
    },
    processing: {
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
          label: "QĐ cấp CC",
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

function buildChangeRequestWorkspace(overrides: Record<string, unknown> = {}) {
  return {
    id: "change-1",
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
    ...overrides,
  };
}

function renderApp(initialEntries: string[] = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <App />
    </MemoryRouter>,
  );
}

describe("App Slice A.4 search workspace", () => {
  beforeEach(() => {
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
  });

  it("renders compact header without the old subtitle and keeps identity beside the brand", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    const { container } = renderApp();

    expect(await screen.findByText("GxP QLCL")).toBeInTheDocument();
    expect(screen.queryByText("Tra cứu và điều phối nghiệp vụ")).not.toBeInTheDocument();
    expect(screen.getByText("operator.local (inspector)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đăng xuất" })).toBeInTheDocument();
    expect(container.querySelector(".header-identity-group")).not.toBeNull();
    expect(container.querySelector(".primary-nav")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Terms of Service" })).toHaveAttribute("href", "/terms");
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
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    expect(await screen.findByRole("heading", { name: "Cơ sở/dây chuyền" })).toBeInTheDocument();
    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Tên cơ sở" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Phạm vi chứng nhận" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Trạng thái hồ sơ" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Tỉnh/thành" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Chứng nhận" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Xử lý" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Công ty mới" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hồ sơ kiểm tra" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dây chuyền mới" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "D.chuyền mới" })).not.toBeInTheDocument();
    for (const label of ["Công ty mới", "Cơ sở mới", "Dây chuyền mới", "Tái đánh giá", "Thay đổi"]) {
      expect(screen.getByRole("button", { name: label })).toBeDisabled();
    }
    expect(screen.getByRole("button", { name: "Tái đánh giá" })).toHaveAttribute(
      "title",
      "Chưa có create contract owner-safe để mở hồ sơ tái đánh giá mới cho ngữ cảnh GMP.",
    );
    expect(screen.queryByText(/^Prev$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Next$/)).not.toBeInTheDocument();
    expect(container.querySelector(".search-toolbar")).toBeNull();
    expect(container.querySelector(".search-workspace-split .history-panel")).toBeNull();
    expect(container.querySelector(".facility-workspace-panel .history-panel")).not.toBeNull();
  }, 10000);

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
                detail: "Có thể mở hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
                required_permissions: ["case.edit"],
              }
            : item,
        ),
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    renderApp(["/search"]);

    expect(await screen.findByText("1.1A")).toBeInTheDocument();
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
                detail: "Có thể mở hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
                required_permissions: ["case.edit"],
              }
            : item,
        ),
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));

    const dialog = await screen.findByRole("dialog", { name: "Mở hồ sơ tái đánh giá" });
    expect(within(dialog).getByText("Công ty cổ phần dược phẩm Trung ương I")).toBeInTheDocument();
    expect(within(dialog).getByText("GMP")).toBeInTheDocument();
    expect(within(dialog).getByText("A")).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "Tiêu chuẩn áp dụng" })).toHaveFocus();
    expect(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Hủy" })).toBeInTheDocument();
    expect(container.querySelector(".action-stack .create-inspection-case-panel")).toBeNull();

    fireEvent.click(within(dialog).getByRole("button", { name: "Hủy" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Mở hồ sơ tái đánh giá" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Tái đánh giá" })).toHaveFocus();
  });

  it("creates a reassessment case without refetching search and refreshes workspace/history to the new case", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace
      .mockResolvedValueOnce(
        buildWorkspace({
          action_readiness: buildWorkspace().action_readiness.map((item) =>
            item.action_key === "create_reassessment_case"
              ? {
                  ...item,
                  readiness_status: "available",
                  detail: "Có thể mở hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
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

    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    const createAction = screen.getByRole("button", { name: "Tái đánh giá" });
    fireEvent.click(createAction);

    const dialog = await screen.findByRole("dialog", { name: "Mở hồ sơ tái đánh giá" });
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
        applicable_standard: "WHO-GMP",
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
    await waitFor(() => {
      expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Mở hồ sơ tái đánh giá" })).not.toBeInTheDocument();
    });
    expect(await screen.findByRole("heading", { name: "Thông tin hồ sơ" })).toBeInTheDocument();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  });

  it("keeps the reassessment dialog open while submit is pending and allows escape close when idle", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
   apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    const reassessmentReadyWorkspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "create_reassessment_case"
          ? {
              ...item,
              readiness_status: "available",
              detail: "Có thể mở hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
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

    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));
    let dialog = await screen.findByRole("dialog", { name: "Mở hồ sơ tái đánh giá" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" }));

    await waitFor(() => {
      expect(within(screen.getByRole("dialog", { name: "Mở hồ sơ tái đánh giá" })).getByRole("button", { name: "Đang tạo..." })).toBeDisabled();
    });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "Mở hồ sơ tái đánh giá" })).toBeInTheDocument();

     releaseCreate();
     await waitFor(() => {
       expect(screen.queryByRole("dialog", { name: "Mở hồ sơ tái đánh giá" })).not.toBeInTheDocument();
     });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));
    dialog = await screen.findByRole("dialog", { name: "Mở hồ sơ tái đánh giá" });
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Mở hồ sơ tái đánh giá" })).not.toBeInTheDocument();
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
                detail: "Có thể mở hồ sơ tái đánh giá mới cho đúng ngữ cảnh cơ sở/GxP/dây chuyền đang chọn.",
                required_permissions: ["case.edit"],
              }
            : item,
        ),
      }),
    );
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());
    apiMocks.createInspectionCase.mockRejectedValue(new Error("An open inspection case already exists for the selected facility/GxP/line context."));

    renderApp(["/search"]);

    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Tái đánh giá" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Tái đánh giá" }));
    const dialog = await screen.findByRole("dialog", { name: "Mở hồ sơ tái đánh giá" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Tạo hồ sơ tái đánh giá" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "An open inspection case already exists for the selected facility/GxP/line context.",
    );
    expect(screen.getByRole("dialog", { name: "Mở hồ sơ tái đánh giá" })).toBeInTheDocument();
    expect(screen.getByText("1.1A")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("uses the canonical GMPbb value and hides the GxP column outside the Tất cả view", async () => {
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
    expect(screen.getByRole("button", { name: "GMPbb" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("columnheader", { name: "GxP" })).not.toBeInTheDocument();
  });

  it("shows the GxP column only under the Tất cả view", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(null);

    renderApp(["/search"]);

    expect(await screen.findByRole("columnheader", { name: "GxP" })).toBeInTheDocument();
  });

  it("formats result and history dates as dd-mm-yyyy and keeps selected rows highlighted in the workspace", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("01-08-2026")).toBeInTheDocument();
    await screen.findByText("Lịch sử kiểm tra & thay đổi");
    expect(screen.getByText("05-08-2026")).toBeInTheDocument();
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
    expect(screen.getByText("Nhà máy A")).toBeInTheDocument();
    expect(screen.getByText("KCN A")).toBeInTheDocument();
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
          buildSearchResult({ result_key: "site-1:GMP:A", context_code: "1.1A" }),
          buildSearchResult({ result_key: "site-1:GMP:B", context_code: "1.1B", line_code: "B" }),
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

    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    expect(await screen.findByText("Đã tải 2 / 3")).toBeInTheDocument();
    const scrollRegion = screen.getByTestId("facility-table-scroll");
    Object.defineProperty(scrollRegion, "scrollTop", { configurable: true, value: 260 });
    Object.defineProperty(scrollRegion, "clientHeight", { configurable: true, value: 200 });
    Object.defineProperty(scrollRegion, "scrollHeight", { configurable: true, value: 400 });

    fireEvent.scroll(scrollRegion);

    await waitFor(() => {
      expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText("1.1C")).toBeInTheDocument();
    expect(screen.getByText("3 dòng")).toBeInTheDocument();
    expect(screen.queryByText(/^Prev$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Next$/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("1.1B"));

    await waitFor(() => {
      const lastCall = apiMocks.getFacilityWorkspace.mock.calls.at(-1);
      expect(lastCall?.[0]).toBe("site-1");
      expect(lastCall?.[3]).toBe("GMP");
      expect(lastCall?.[4]).toBe("B");
    });
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2);
  });

  it("renders history inside the facility tab and uses workflow-step navigation instead of nested peer tabs", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseWorkspace.mockResolvedValue(buildCaseWorkspace());

    const { container } = renderApp(["/search"]);

    const workspacePanel = await screen.findByRole("tab", { name: "Các đợt kiểm tra & thay đổi" });
    expect(workspacePanel).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("navigation", { name: "Quy trình xử lý sự kiện" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Thông tin hồ sơ" })).toBeInTheDocument();
    expect(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Hồ sơ" })).not.toBeInTheDocument();
    expect(container.querySelector(".workspace-context-strip")).toBeNull();
    expect(container.querySelector(".event-workspace-split.master-detail-split.master-detail-split-history")).not.toBeNull();
    expect(container.querySelector(".event-workspace-history-pane.master-list-pane .history-panel")).not.toBeNull();
    expect(container.querySelector(".event-workspace-detail-pane.detail-pane .event-workspace")).not.toBeNull();
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
      expect(container.querySelector(".history-panel")).not.toBeNull();
    });
    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "TD-01" })).toBeInTheDocument();
    });
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

    expect(await screen.findByRole("heading", { name: "KT-2026-GMP-A" })).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);

    fireEvent.click(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi"));

    expect(await screen.findByRole("heading", { name: "TD-01" })).toBeInTheDocument();
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

    expect(await screen.findByRole("heading", { name: "KT-2026-GMP-A" })).toBeInTheDocument();
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
          cycles: [
            {
              capa_cycle_id: "capa-1",
              round_no: 1,
              requested_on: "2026-08-07",
              submitted_on: "2026-08-09",
              assessed_on: "2026-08-12",
              assessor_name: "Chuyên viên B",
              result: "Đạt",
              status: "accepted",
              notes: "Đã hoàn tất",
            },
          ],
        },
      }),
    );

    const { container } = renderApp(["/search"]);

    expect(await screen.findByText("HS-001")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Kiểm tra/ }));
    expect(await screen.findByText("QĐ-KT-01")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Khắc phục/ }));
    expect(await screen.findByText("Lịch sử khắc phục")).toBeInTheDocument();
    expect(screen.getByText("Đã hoàn tất")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Xử lý/ }));
    expect(await screen.findByText("Đề xuất cấp chứng nhận")).toBeInTheDocument();
    expect(screen.getByText("Tiếp nhận hồ sơ")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Tài liệu" }));
    expect(await screen.findByText("QĐ cấp CC")).toBeInTheDocument();
    expect(screen.getByText("8 qd cap cc GMP.docx")).toBeInTheDocument();

    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.getCaseWorkspace).toHaveBeenCalledTimes(1);
    expect(apiMocks.getChangeRequestWorkspace).not.toHaveBeenCalled();
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
  }, 10000);

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
    expect(screen.getByText("195/GCN-QLD")).toBeInTheDocument();
    expect(screen.getByText("533/GCN-QLD")).toBeInTheDocument();
    expect(await screen.findByText("Thuốc không vô trùng")).toBeInTheDocument();
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
});
