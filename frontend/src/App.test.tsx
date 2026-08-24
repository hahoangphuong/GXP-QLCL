import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const apiMocks = vi.hoisted(() => ({
  getAppStatus: vi.fn(),
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

function renderApp() {
  return render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
}

describe("App auth rendering", () => {
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
    apiMocks.getCaseDetail.mockResolvedValue(null);
    apiMocks.getDocumentDetail.mockResolvedValue(null);
    apiMocks.getGenerationRun.mockResolvedValue(null);
    apiMocks.listCases.mockResolvedValue([]);
    apiMocks.listCompanies.mockResolvedValue([]);
    apiMocks.listSites.mockResolvedValue([]);
  });

  it("renders the migration cockpit shell", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp();

    expect(await screen.findByText("Buồng điều phối di trú GxP Web")).toBeInTheDocument();
    expect(screen.getByText("Tổng quan")).toBeInTheDocument();
    expect(screen.getByText("Không gian hồ sơ")).toBeInTheDocument();
  });

  it("keeps stub controls for header_stub mode", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("header_stub", null));

    renderApp();

    expect(await screen.findByText("Người dùng giả lập")).toBeInTheDocument();
    expect(screen.getByDisplayValue("operator.local")).toBeInTheDocument();
  });

  it("does not render stub controls in google_oidc mode", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("google_oidc", null));

    renderApp();

    expect(await screen.findByText("Thiếu Google OIDC client ID trong trạng thái ứng dụng.")).toBeInTheDocument();
    expect(screen.queryByText("Người dùng giả lập")).not.toBeInTheDocument();
    expect(apiMocks.listCompanies).not.toHaveBeenCalled();
    expect(apiMocks.listSites).not.toHaveBeenCalled();
    expect(apiMocks.listCases).not.toHaveBeenCalled();
  });

  it("renders Google sign-in button when google_oidc has a client id", async () => {
    apiMocks.getAppStatus.mockResolvedValue(buildStatus("google_oidc", "client-123"));

    renderApp();

    expect(await screen.findByText("Đăng nhập bằng tài khoản Google Workspace để mở giao diện vận hành.")).toBeInTheDocument();
    expect(screen.queryByText("Người dùng giả lập")).not.toBeInTheDocument();
    expect(window.google?.accounts?.id?.renderButton).toHaveBeenCalled();
  });
});
