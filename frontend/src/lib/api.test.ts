import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getAppStatus,
  getCaseDetail,
  getChangeRequestWorkspace,
  getCaseWorkspace,
  getFacilityWorkspace,
  getDocumentDetail,
  getGenerationRun,
  listCases,
  listCompanies,
  listSites,
  prepareDocument,
  searchFacilities,
  renderTemplateDocx,
} from "./api";

type MockJsonResponse = {
  ok?: boolean;
  status?: number;
  statusText?: string;
  json?: unknown;
  contentType?: string;
};

function mockJsonResponse({
  ok = true,
  status = 200,
  statusText = "OK",
  json = [],
  contentType = "application/json; charset=utf-8",
}: MockJsonResponse = {}) {
  return {
    ok,
    status,
    statusText,
    headers: {
      get: (name: string) => (name.toLowerCase() === "content-type" ? contentType : null),
    },
    json: async () => json,
  };
}

describe("frontend API routing contract", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("uses /api/app/status by default in production-safe mode", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { auth_mode: "header_stub" } }));
    vi.stubGlobal("fetch", fetchMock);

    await getAppStatus();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/app/status",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("uses /api/companies for companies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);

    await listCompanies({ username: "operator.local", role: "manager" }, true);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/companies",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Auth-User": "operator.local",
          "X-Auth-Role": "manager",
        }),
      }),
    );
  });

  it("uses /api/sites for sites", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);

    await listSites({ username: "operator.local", role: "manager" }, true);

    expect(fetchMock).toHaveBeenCalledWith("/api/sites", expect.any(Object));
  });

  it("uses /api/cases for cases", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);

    await listCases({ username: "operator.local", role: "manager" }, true);

    expect(fetchMock).toHaveBeenCalledWith("/api/cases", expect.any(Object));
  });

  it("uses exactly one /api prefix for document, case detail, case workspace, and change-request workspace endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await getCaseDetail("case-123", { username: "operator.local", role: "manager" }, true);
    await getCaseWorkspace("case-123", { username: "operator.local", role: "manager" }, true);
    await getChangeRequestWorkspace("change-123", { username: "operator.local", role: "manager" }, true);
    await prepareDocument(
      { case_id: "case-123", family_code: "DDKD_CERTIFICATE" } as never,
      { username: "operator.local", role: "manager" },
      true,
    );
    await renderTemplateDocx(
      { case_id: "case-123", family_code: "DDKD_CERTIFICATE", output_filename: "result.docx" } as never,
      { username: "operator.local", role: "manager" },
      true,
    );
    await getGenerationRun("run-123", { username: "operator.local", role: "manager" }, true);
    await getDocumentDetail("doc-123", { username: "operator.local", role: "manager" }, true);

    const urls = fetchMock.mock.calls.map((call) => call[0]);
    expect(urls).toEqual([
      "/api/cases/case-123",
      "/api/cases/case-123/workspace",
      "/api/change-requests/change-123/workspace",
      "/api/documents/prepare",
      "/api/documents/render-template-docx",
      "/api/document-generation-runs/run-123",
      "/api/documents/doc-123",
    ]);
    for (const url of urls) {
      expect(String(url)).not.toContain("/api/api/");
    }
  });

  it("supports VITE_API_BASE_URL override without double slash or double api", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com/base/");

    await listCompanies({ username: "operator.local", role: "manager" }, false, "oidc-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.com/base/companies",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer oidc-token",
        }),
      }),
    );
    expect(fetchMock.mock.calls[0][0]).not.toContain("//companies");
    expect(fetchMock.mock.calls[0][0]).not.toContain("/api/api/");
  });

  it("normalizes same-origin /api override without double slash or double api", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_BASE_URL", "/api/");

    await listSites({ username: "operator.local", role: "manager" }, true);

    expect(fetchMock).toHaveBeenCalledWith("/api/sites", expect.any(Object));
    expect(fetchMock.mock.calls[0][0]).not.toContain("/api/api/");
    expect(fetchMock.mock.calls[0][0]).not.toContain("//sites");
  });

  it("reports a clear diagnostic when an API endpoint returns HTML instead of JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockJsonResponse({
        contentType: "text/html; charset=utf-8",
        json: "<!doctype html>",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getAppStatus()).rejects.toThrow("Kỳ vọng JSON từ /api/app/status nhưng nhận được text/html");
  });

  it("sends Authorization bearer token in google_oidc mode", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);

    await listCompanies({ username: "operator.local", role: "manager" }, false, "oidc-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/companies",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer oidc-token",
        }),
      }),
    );
    expect(fetchMock.mock.calls[0][1].headers["X-Auth-User"]).toBeUndefined();
  });

  it("encodes repeated facility search filters plus paging for exact drilldown predicates", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);

    await searchFacilities(
      {
        gxp_type: "GMP",
        case_state: ["planned", "decision_issued", "inspection_in_progress"],
        change_request_state: ["received", "under_review"],
        certificate_state: "active",
        certificate_expiring_within_days: 90,
        offset: 100,
        limit: 100,
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/search/facilities?gxp_type=GMP&case_state=planned&case_state=decision_issued&case_state=inspection_in_progress&change_request_state=received&change_request_state=under_review&certificate_state=active&certificate_expiring_within_days=90&offset=100&limit=100",
      expect.any(Object),
    );
  });

  it("encodes field-specific search filters and the canonical GMPbb selector", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse());
    vi.stubGlobal("fetch", fetchMock);

    await searchFacilities(
      {
        facility_name: "Nhà máy GMPbb",
        certificate_scope: "Bao bì vô trùng",
        gxp_type: "GMPbb",
        case_state: ["awaiting_certificate_decision"],
        limit: 100,
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/search/facilities?facility_name=Nh%C3%A0+m%C3%A1y+GMPbb&certificate_scope=Bao+b%C3%AC+v%C3%B4+tr%C3%B9ng&gxp_type=GMPbb&case_state=awaiting_certificate_decision&limit=100",
      expect.any(Object),
    );
  });

  it("passes gxp_type through facility workspace requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { summary: {}, history: [] } }));
    vi.stubGlobal("fetch", fetchMock);

    await getFacilityWorkspace("site-123", { username: "operator.local", role: "manager" }, true, "GLP");

    expect(fetchMock).toHaveBeenCalledWith("/api/sites/site-123/workspace?gxp_type=GLP", expect.any(Object));
  });
});
