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
      address: "KCN A",
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
    expect(screen.getByRole("heading", { name: "Xử lý" })).toBeInTheDocument();
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

  it("renders three grouped sections in Thông tin chung and shows missing owner-gap fields as Chưa có", async () => {
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
    expect(screen.getByText("Nhà máy A")).toBeInTheDocument();
    expect(screen.getByText("KCN A")).toBeInTheDocument();
    expect(screen.getByText("GCN-789")).toBeInTheDocument();
    expect(screen.getByText("15-03-2026")).toBeInTheDocument();
    expect(screen.getByText("15-03-2027")).toBeInTheDocument();
    expect(screen.getByText("PIC/S-GMP")).toBeInTheDocument();
    expect(screen.getByText("Dây chuyền thuốc nước")).toBeInTheDocument();
    expect(screen.getByText("Còn hiệu lực")).toBeInTheDocument();
    expect(screen.getAllByText("Chưa có").length).toBeGreaterThan(0);
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
});
