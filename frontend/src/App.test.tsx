import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    facility_name: "Nhà máy A",
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
      address: "Hà Nội",
      province_name: "Hà Nội",
      gxp_types: ["GMP"],
      selected_gxp_type: "GMP",
      current_state: "awaiting_certificate_decision",
      primary_standard: "WHO-GMP",
      current_certificate_number: "GCN-001",
      current_certificate_expiry: "2026-12-31",
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
        occurred_on: "2026-08-01",
        state: "awaiting_certificate_decision",
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

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });
  return { promise, resolve, reject };
}

describe("App Slice A shell", () => {
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

  it("renders the business shell with compact header and Tra cứu as primary navigation", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    const { container } = renderApp();

    expect(await screen.findByText("GxP QLCL")).toBeInTheDocument();
    expect(screen.getByText("Tra cứu và điều phối nghiệp vụ")).toBeInTheDocument();
    expect(screen.getByText("Tổng quan")).toBeInTheDocument();
    expect(screen.getByText("Tra cứu")).toBeInTheDocument();
    expect(container.querySelector(".shell-chrome")).not.toBeNull();
    expect(container.querySelector(".primary-nav")).not.toBeNull();
  });

  it("keeps stub auth controls in header_stub mode", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp();

    expect(await screen.findByText("Người dùng giả lập")).toBeInTheDocument();
    expect(screen.getByDisplayValue("operator.local")).toBeInTheDocument();
    expect(await screen.findByText("Bảng điều phối nghiệp vụ")).toBeInTheDocument();
  });

  it("prompts sign-in instead of loading data in google_oidc mode without session", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("google_oidc", null));

    renderApp(["/search"]);

    expect(await screen.findByText("Cần đăng nhập")).toBeInTheDocument();
    expect(screen.queryByText("Người dùng giả lập")).not.toBeInTheDocument();
    expect(apiMocks.searchFacilities).not.toHaveBeenCalled();
  });

  it("renders Google sign-in button when google_oidc has a client id", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("google_oidc", "client-123"));

    renderApp();

    expect(await screen.findByText("Đăng nhập")).toBeInTheDocument();
    expect(screen.queryByText("Người dùng giả lập")).not.toBeInTheDocument();
    expect(window.google?.accounts?.id?.renderButton).toHaveBeenCalled();
  });

  it("renders compact search split, line-grain results, and bottom facility tabs from authenticated API", async () => {
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

    expect(await screen.findByText("Cơ sở/dây chuyền")).toBeInTheDocument();
    expect(await screen.findByText("1.1A")).toBeInTheDocument();
    expect(await screen.findByText("Dây chuyền viên nén A")).toBeInTheDocument();
    expect(screen.getByText("1-1 / 1 dòng")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Thông tin chung" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Các đợt kiểm tra & thay đổi" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Giấy chứng nhận GxP" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Giấy chứng nhận đủ điều kiện" })).toBeInTheDocument();
    expect(screen.getAllByText("KT-2026-GMP-A").length).toBeGreaterThan(0);
    expect(container.querySelector(".search-workspace-split")).not.toBeNull();
    expect(container.querySelector(".facility-workspace-panel")).not.toBeNull();
    expect(container.querySelector(".history-panel")).not.toBeNull();
  });

  it("keeps active filter chips visible while advanced filters stay collapsed by default", async () => {
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

    const { container } = renderApp(["/search?certificate_state=active&certificate_expiring_within_days=90&case_state=planned"]);

    expect(await screen.findByText("Chứng nhận: Còn hiệu lực")).toBeInTheDocument();
    expect(screen.getByText("Sắp hết hạn: 90 ngày")).toBeInTheDocument();
    expect(screen.getByText("Trạng thái hồ sơ: Đã lập kế hoạch")).toBeInTheDocument();
    expect(container.querySelector(".toolbar-grid")).toBeNull();
    expect(screen.getByRole("button", { name: "Bộ lọc" })).toBeInTheDocument();
  });

  it("preserves selected facility, line, and gxp context while switching facility tabs", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({
      items: [
        buildSearchResult(),
        buildSearchResult({
        result_key: "site-1:GMP:B",
        context_code: "1.1B",
        line_code: "B",
        certificate_scope_summary: "Dây chuyền thuốc bột B",
        last_inspection_on: "2026-08-05",
      }),
      ],
      total_count: 2,
      offset: 0,
      limit: 100,
    });
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

    renderApp(["/search"]);

    expect(await screen.findByText(/Dây chuyền\s*A/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Thông tin chung" }));
    expect(screen.getAllByText("Phạm vi chứng nhận").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1.1A").length).toBeGreaterThan(0);
    expect(screen.getByText(/Dây chuyền\s*A/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Giấy chứng nhận GxP" }));
    expect(await screen.findByText("Số GCN hiện hành")).toBeInTheDocument();
    expect(screen.getAllByText("Dây chuyền viên nén A").length).toBeGreaterThan(0);
    expect(screen.getByText("Lịch sử chứng nhận chưa mở ở Slice A.2")).toBeInTheDocument();
  });

  it("shows API error instead of fake empty state on failed search", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockRejectedValue(new Error("403 Forbidden"));

    renderApp(["/search"]);

    expect(await screen.findByText("Yêu cầu thất bại")).toBeInTheDocument();
    expect(screen.getByText("403 Forbidden")).toBeInTheDocument();
    expect(screen.queryByText("Không có kết quả")).not.toBeInTheDocument();
  });

  it("keeps dashboard drilldowns aligned with metric predicates", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp(["/"]);

    await screen.findByText("Bảng điều phối nghiệp vụ");

    expect(screen.getByText("Cơ sở có hồ sơ đang xử lý")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở chờ kiểm tra")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở chờ cấp chứng nhận")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở có GCN còn hiệu lực")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở có GCN sắp hết hạn 90 ngày")).toBeInTheDocument();
    expect(screen.getByText("Cơ sở có thay đổi chưa hoàn tất")).toBeInTheDocument();

    const metricLinks = Array.from(document.querySelectorAll(".metric-grid a")).map((node) => node.getAttribute("href"));
    expect(metricLinks).toContain(
      "/search?case_state=draft&case_state=application_received&case_state=under_assessment&case_state=planned&case_state=decision_issued&case_state=inspection_in_progress&case_state=inspection_completed&case_state=awaiting_certificate_decision",
    );
    expect(metricLinks).toContain("/search?case_state=planned&case_state=decision_issued&case_state=inspection_in_progress");
    expect(metricLinks).toContain("/search?case_state=awaiting_certificate_decision");
    expect(metricLinks).toContain("/search?certificate_state=active");
    expect(metricLinks).toContain("/search?certificate_expiring_within_days=90");
    expect(metricLinks).toContain("/search?change_request_state=received&change_request_state=under_review");
  });

  it("clears stale case detail while switching history items quickly", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({
      items: [
      buildSearchResult({
        current_state: "inspection_in_progress",
        last_inspection_on: "2026-08-05",
      }),
      ],
      total_count: 1,
      offset: 0,
      limit: 100,
    });
    apiMocks.getFacilityWorkspace.mockResolvedValue({
      ...buildWorkspace(),
      summary: {
        ...buildWorkspace().summary,
        current_state: "inspection_in_progress",
        primary_standard: "WHO-GMP/PIC/S",
      },
      history: [
        {
          id: "case-a",
          source_type: "case",
          reference_code: "KT-2026-GMP-A",
          event_type: "Định kỳ",
          gxp_type: "GMP",
          standard: "WHO-GMP",
          occurred_on: "2026-08-01",
          state: "planned",
        },
        {
          id: "case-b",
          source_type: "case",
          reference_code: "KT-2026-GMP-B",
          event_type: "Đột xuất",
          gxp_type: "GMP",
          standard: "PIC/S-GMP",
          occurred_on: "2026-08-05",
          state: "inspection_in_progress",
        },
      ],
    });
    const caseA = deferredPromise<{
      id: string;
      legacy_inspection_id: number;
      legacy_inspection_code: string;
      site_id: string;
      gxp_type: string;
      scope_code: string;
      applicable_standard: string;
      inspection_type: string;
      state: string;
      opened_year: number;
    }>();
    const caseB = deferredPromise<{
      id: string;
      legacy_inspection_id: number;
      legacy_inspection_code: string;
      site_id: string;
      gxp_type: string;
      scope_code: string;
      applicable_standard: string;
      inspection_type: string;
      state: string;
      opened_year: number;
    }>();
    apiMocks.getCaseDetail.mockImplementation((caseId: string) => {
      if (caseId === "case-a") {
        return caseA.promise;
      }
      if (caseId === "case-b") {
        return caseB.promise;
      }
      return Promise.reject(new Error(`Unexpected case id ${caseId}`));
    });

    renderApp(["/search"]);

    expect(await screen.findByText("Đang tải chi tiết hồ sơ")).toBeInTheDocument();

    fireEvent.click((await screen.findByText("Đột xuất")).closest("tr") as HTMLElement);

    expect(screen.getByText("Đang tải chi tiết hồ sơ")).toBeInTheDocument();

    caseA.resolve({
      id: "case-a",
      legacy_inspection_id: 1,
      legacy_inspection_code: "KT-2026-GMP-A",
      site_id: "site-1",
      gxp_type: "GMP",
      scope_code: "A",
      applicable_standard: "WHO-GMP",
      inspection_type: "Định kỳ",
      state: "planned",
      opened_year: 2026,
    });

    await waitFor(() => {
      expect(screen.getByText("Đang tải chi tiết hồ sơ")).toBeInTheDocument();
    });

    caseB.resolve({
      id: "case-b",
      legacy_inspection_id: 2,
      legacy_inspection_code: "KT-2026-GMP-B",
      site_id: "site-1",
      gxp_type: "GMP",
      scope_code: "B",
      applicable_standard: "PIC/S-GMP",
      inspection_type: "Đột xuất",
      state: "inspection_in_progress",
      opened_year: 2026,
    });

    expect(await screen.findByText("PIC/S-GMP")).toBeInTheDocument();
    expect(screen.getAllByText("Đang kiểm tra").length).toBeGreaterThan(0);
    expect(screen.queryByText("Không tải được chi tiết hồ sơ")).not.toBeInTheDocument();
  });

  it("does not refetch the result list when selecting another result row", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue({
      items: [
        buildSearchResult(),
        buildSearchResult({
          result_key: "site-1:GMP:B",
          context_code: "1.1B",
          line_code: "B",
          facility_name: "Công ty cổ phần Dược phẩm Trung ương I",
          certificate_scope_summary: "Dây chuyền thuốc bột B",
          last_inspection_on: "2026-08-05",
        }),
      ],
      total_count: 2,
      offset: 0,
      limit: 100,
    });
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

    renderApp(["/search"]);

    expect(await screen.findByText("Cty CP Dược phẩm Trung ương I")).toBeInTheDocument();
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText("1.1B"));

    await waitFor(() => {
      const lastCall = apiMocks.getFacilityWorkspace.mock.calls.at(-1);
      expect(lastCall?.[0]).toBe("site-1");
      expect(lastCall?.[2]).toBe(true);
      expect(lastCall?.[3]).toBe("GMP");
      expect(lastCall?.[4]).toBe("B");
    });
    expect(apiMocks.searchFacilities).toHaveBeenCalledTimes(1);
  });

  it("renders facility tabs as a dedicated tab strip", async () => {
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

    await screen.findByRole("tab", { name: "Thông tin chung" });
    expect(container.querySelector(".tab-strip-primary")).not.toBeNull();
    expect(screen.getByRole("tab", { name: "Các đợt kiểm tra & thay đổi" })).toHaveAttribute("aria-selected", "true");
  });
});
