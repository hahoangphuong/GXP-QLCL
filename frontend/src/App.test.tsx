import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const apiMocks = vi.hoisted(() => ({
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
    vi.clearAllMocks();
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
    apiMocks.getCaseDetail.mockResolvedValue({
      id: "case-1",
      legacy_inspection_id: 1,
      legacy_inspection_code: "KT-2026-GMP-A",
      site_id: "site-1",
      gxp_type: "GMP",
      scope_code: "A",
      applicable_standard: "WHO-GMP",
      inspection_type: "Định kỳ",
      state: "awaiting_certificate_decision",
      opened_year: 2026,
    });

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
    expect(screen.queryByText(/^Prev$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Next$/)).not.toBeInTheDocument();
    expect(container.querySelector(".search-toolbar")).toBeNull();
    expect(container.querySelector(".search-workspace-split .history-panel")).toBeNull();
    expect(container.querySelector(".facility-workspace-panel .history-panel")).not.toBeNull();
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
    apiMocks.getCaseDetail.mockResolvedValue(null);

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
    apiMocks.getCaseDetail.mockResolvedValue(null);

    renderApp(["/search"]);

    expect(await screen.findByRole("columnheader", { name: "GxP" })).toBeInTheDocument();
  });

  it("formats result and history dates as dd-mm-yyyy and keeps selected rows highlighted in the workspace", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseDetail.mockResolvedValue({
      id: "case-1",
      legacy_inspection_id: 1,
      legacy_inspection_code: "KT-2026-GMP-A",
      site_id: "site-1",
      gxp_type: "GMP",
      scope_code: "A",
      applicable_standard: "WHO-GMP",
      inspection_type: "Định kỳ",
      state: "awaiting_certificate_decision",
      opened_year: 2026,
    });

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
    apiMocks.getCaseDetail.mockResolvedValue(null);

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
    apiMocks.getCaseDetail.mockResolvedValue(null);

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
    apiMocks.getCaseDetail.mockResolvedValue(null);

    renderApp(["/search"]);

    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    const scrollRegion = screen.getByTestId("facility-table-scroll");
    Object.defineProperty(scrollRegion, "scrollTop", { configurable: true, value: 260 });
    Object.defineProperty(scrollRegion, "clientHeight", { configurable: true, value: 200 });
    Object.defineProperty(scrollRegion, "scrollHeight", { configurable: true, value: 400 });

    fireEvent.scroll(scrollRegion);

    expect(await screen.findByText("1.1C")).toBeInTheDocument();
    expect(screen.getByText("3 dòng")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(2);
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
    apiMocks.getCaseDetail.mockResolvedValue({
      id: "case-1",
      legacy_inspection_id: 1,
      legacy_inspection_code: "KT-2026-GMP-A",
      site_id: "site-1",
      gxp_type: "GMP",
      scope_code: "A",
      applicable_standard: "WHO-GMP",
      inspection_type: "Định kỳ",
      state: "awaiting_certificate_decision",
      opened_year: 2026,
    });

    const { container } = renderApp(["/search"]);

    const workspacePanel = await screen.findByRole("tab", { name: "Các đợt kiểm tra & thay đổi" });
    expect(workspacePanel).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("navigation", { name: "Quy trình xử lý sự kiện" })).toBeInTheDocument();
    expect(screen.getByText("Phân loại")).toBeInTheDocument();
    expect(within(container.querySelector(".history-panel") as HTMLElement).getByText("Thay đổi")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Hồ sơ" })).not.toBeInTheDocument();
    expect(container.querySelector(".workspace-context-strip")).toBeNull();
    expect(container.querySelector(".event-workspace-split")).not.toBeNull();
    expect(container.querySelector(".event-workspace-history-pane .history-panel")).not.toBeNull();
    expect(container.querySelector(".event-workspace-detail-pane .event-workspace")).not.toBeNull();
  });

  it("updates only the right event pane when history selection changes and keeps ActionCard free of duplicated facility context", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseDetail.mockResolvedValue({
      id: "case-1",
      legacy_inspection_id: 1,
      legacy_inspection_code: "KT-2026-GMP-A",
      site_id: "site-1",
      gxp_type: "GMP",
      scope_code: "A",
      applicable_standard: "WHO-GMP",
      inspection_type: "Định kỳ",
      state: "awaiting_certificate_decision",
      opened_year: 2026,
    });

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
    expect(within(container.querySelector(".event-workspace") as HTMLElement).getByText("Đổi địa chỉ")).toBeInTheDocument();
    expect(container.querySelector(".facility-table tbody tr.selected")).not.toBeNull();
    expect(container.querySelector(".history-table tbody tr.selected")).not.toBeNull();
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
    apiMocks.getCaseDetail.mockResolvedValue(null);
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
          expiry_date: "2024-09-14",
          applicable_standard: "WHO-GMP",
          issuing_authority: "Cục Quản lý Dược Việt Nam",
          status: "expired",
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
        expiry_date: "2024-09-14",
        applicable_standard: "WHO-GMP",
        issuing_authority: "Cục Quản lý Dược Việt Nam",
        status: "expired",
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
    expect(screen.getByText("195/GCN-QLD")).toBeInTheDocument();
    expect(screen.getByText("533/GCN-QLD")).toBeInTheDocument();
    expect(await screen.findByText("Thuốc không vô trùng")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText("533/GCN-QLD"));

    expect(await screen.findByText("Thuốc không vô trùng cũ")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
    expect(apiMocks.listSiteGxpCertificates).toHaveBeenCalledTimes(1);
    expect(apiMocks.getGxpCertificateDetail).toHaveBeenCalledTimes(2);
  });

  it("renders the business eligibility workspace as list plus detail with linked GxP basis", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({ items: [buildSearchResult()], total_count: 1, offset: 0, limit: 100 });
    apiMocks.getFacilityWorkspace.mockResolvedValue(buildWorkspace());
    apiMocks.getCaseDetail.mockResolvedValue(null);
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
    apiMocks.getCaseDetail.mockResolvedValue(null);
    apiMocks.listSiteGxpCertificates.mockResolvedValue({ items: [] });

    renderApp(["/search?facility_tab=Gi%E1%BA%A5y%20ch%E1%BB%A9ng%20nh%E1%BA%ADn%20GxP"]);

    expect(await screen.findByText("Chưa có giấy chứng nhận GxP")).toBeInTheDocument();
    expect(screen.queryByText("Nguồn gốc")).not.toBeInTheDocument();
  });
});
