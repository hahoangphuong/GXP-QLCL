import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
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
  searchFacilities: vi.fn().mockResolvedValue([]),
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

function renderApp(initialEntries: string[] = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <App />
    </MemoryRouter>,
  );
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

  it("renders the business shell with Tra cứu as primary navigation", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp();

    expect(await screen.findByText("Workspace nghiệp vụ")).toBeInTheDocument();
    expect(screen.getByText("Tổng quan")).toBeInTheDocument();
    expect(screen.getByText("Tra cứu")).toBeInTheDocument();
    expect(screen.queryByText("Không gian hồ sơ")).not.toBeInTheDocument();
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

  it("renders search master history detail structure from authenticated API", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockResolvedValue([
      {
        site_id: "site-1",
        legacy_site_id: 101,
        facility_code: "GMP-101",
        facility_name: "Nhà máy A",
        company_name: "Công ty A",
        gxp_types: ["GMP"],
        primary_standard: "WHO-GMP",
        province_name: "Hà Nội",
        last_inspection_code: "KT-2026-GMP",
        current_state: "awaiting_certificate_decision",
        current_certificate_number: "GCN-001",
        current_certificate_expiry: "2026-12-31",
      },
    ]);
    apiMocks.getFacilityWorkspace.mockResolvedValue({
      summary: {
        site_id: "site-1",
        legacy_site_id: 101,
        facility_code: "GMP-101",
        facility_name: "Nhà máy A",
        company_name: "Công ty A",
        address: "Hà Nội",
        province_name: "Hà Nội",
        gxp_types: ["GMP"],
        current_state: "awaiting_certificate_decision",
        primary_standard: "WHO-GMP",
        current_certificate_number: "GCN-001",
        current_certificate_expiry: "2026-12-31",
      },
      history: [
        {
          id: "case-1",
          source_type: "case",
          reference_code: "KT-2026-GMP",
          event_type: "Định kỳ",
          gxp_type: "GMP",
          standard: "WHO-GMP",
          occurred_on: "2026-08-01",
          state: "awaiting_certificate_decision",
        },
      ],
    });
    apiMocks.getCaseDetail.mockResolvedValue({
      id: "case-1",
      legacy_inspection_id: 1,
      legacy_inspection_code: "KT-2026-GMP",
      site_id: "site-1",
      gxp_type: "GMP",
      scope_code: "WHO-GMP",
      applicable_standard: "WHO-GMP",
      inspection_type: "Định kỳ",
      state: "awaiting_certificate_decision",
      opened_year: 2026,
    });

    renderApp(["/search"]);

    expect(await screen.findByText("Danh sách cơ sở")).toBeInTheDocument();
    expect(await screen.findByText("Ngữ cảnh cơ sở")).toBeInTheDocument();
    expect(await screen.findByText("Kiểm tra và thay đổi")).toBeInTheDocument();
    expect(await screen.findByText("Business workspace")).toBeInTheDocument();
    expect(screen.getAllByText("Nhà máy A")).toHaveLength(2);
    expect(screen.getAllByText("KT-2026-GMP").length).toBeGreaterThan(0);
  });

  it("shows API error instead of fake empty state on failed search", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));
    apiMocks.searchFacilities.mockRejectedValue(new Error("403 Forbidden"));

    renderApp(["/search"]);

    expect(await screen.findByText("Yêu cầu thất bại")).toBeInTheDocument();
    expect(screen.getByText("403 Forbidden")).toBeInTheDocument();
    expect(screen.queryByText("Không có kết quả")).not.toBeInTheDocument();
  });
});
