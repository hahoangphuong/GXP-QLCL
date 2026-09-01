import { afterEach, describe, expect, it, vi } from "vitest";

import {
  assessCapaCycle,
  createCapaCycle,
  createInspectionCase,
  getAppStatus,
  getCaseDetail,
  getChangeRequestWorkspace,
  getCaseWorkspace,
  getFacilityWorkspace,
  getDocumentDetail,
  openCapaCycleDocumentCurrentContent,
  openCaseDocumentCurrentContent,
  getGenerationRun,
  listCases,
  listCompanies,
  listSites,
  prepareDocument,
  renderTemplateDocx,
  searchFacilities,
  submitCapaCycle,
  upsertCaseApplication,
  upsertCaseAssessment,
  updateCapaCycle,
  upsertInspectionOutcome,
  upsertInspectionPlan,
} from "./api";

type MockJsonResponse = {
  ok?: boolean;
  status?: number;
  statusText?: string;
  json?: unknown;
  blob?: Blob;
  contentType?: string;
  contentDisposition?: string | null;
};

function mockJsonResponse({
  ok = true,
  status = 200,
  statusText = "OK",
  json = [],
  blob = new Blob(),
  contentType = "application/json; charset=utf-8",
  contentDisposition = null,
}: MockJsonResponse = {}) {
  return {
    ok,
    status,
    statusText,
    headers: {
      get: (name: string) => {
        const normalized = name.toLowerCase();
        if (normalized === "content-type") {
          return contentType;
        }
        if (normalized === "content-disposition") {
          return contentDisposition;
        }
        return null;
      },
    },
    json: async () => json,
    blob: async () => blob,
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
    await openCaseDocumentCurrentContent("case-123", "doc-123", { username: "operator.local", role: "manager" }, true);
    await openCapaCycleDocumentCurrentContent(
      "case-123",
      "capa-123",
      "doc-456",
      { username: "operator.local", role: "manager" },
      true,
    );

    const urls = fetchMock.mock.calls.map((call) => call[0]);
    expect(urls).toEqual([
      "/api/cases/case-123",
      "/api/cases/case-123/workspace",
      "/api/change-requests/change-123/workspace",
      "/api/documents/prepare",
      "/api/documents/render-template-docx",
      "/api/document-generation-runs/run-123",
      "/api/documents/doc-123",
      "/api/cases/case-123/documents/doc-123/content",
      "/api/cases/case-123/capa-cycles/capa-123/documents/doc-456/content",
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

  it("opens document binary with auth headers and parses content disposition filename", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockJsonResponse({
        contentType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        contentDisposition: "inline; filename*=UTF-8''ke-hoach-kiem-tra.docx",
        blob: new Blob(["demo"]),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await openCaseDocumentCurrentContent(
      "case-123",
      "doc-123",
      { username: "operator.local", role: "manager" },
      false,
      "oidc-token",
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cases/case-123/documents/doc-123/content",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          Authorization: "Bearer oidc-token",
        }),
      }),
    );
    expect(result.filename).toBe("ke-hoach-kiem-tra.docx");
    expect(result.contentType).toBe("application/vnd.openxmlformats-officedocument.wordprocessingml.document");
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

  it("posts inspection-case creation to the canonical site workflow endpoint with exactly one /api prefix", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { case_id: "case-123" } }));
    vi.stubGlobal("fetch", fetchMock);

    await createInspectionCase(
      "site-123",
      {
        gxp_type: "GMP",
        line_code: "A",
        applicable_standard: "WHO-GMP",
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sites/site-123/inspection-cases",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-Auth-User": "operator.local",
          "X-Auth-Role": "manager",
        }),
        body: JSON.stringify({
          gxp_type: "GMP",
          line_code: "A",
          applicable_standard: "WHO-GMP",
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("/api/api/");
  });

  it("puts case application updates to the canonical case workflow endpoint with optimistic concurrency payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { case_id: "case-123", row_version: 2 } }));
    vi.stubGlobal("fetch", fetchMock);

    await upsertCaseApplication(
      "case-123",
      {
        expected_version: 1,
        submitted_on: "2026-08-31T00:00:00Z",
        dossier_code: "HS-2026-01",
        dossier_reference: "CV-123",
        applicant_name: "Nguyễn Văn A",
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cases/case-123/application",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          "X-Auth-User": "operator.local",
          "X-Auth-Role": "manager",
        }),
        body: JSON.stringify({
          expected_version: 1,
          submitted_on: "2026-08-31T00:00:00Z",
          dossier_code: "HS-2026-01",
          dossier_reference: "CV-123",
          applicant_name: "Nguyễn Văn A",
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("/api/api/");
  });

  it("puts case assessment updates to the canonical assessment endpoint with optimistic concurrency payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { case_id: "case-123", row_version: 3 } }));
    vi.stubGlobal("fetch", fetchMock);

    await upsertCaseAssessment(
      "case-123",
      {
        expected_version: 2,
        assessed_on: "2026-09-07T00:00:00Z",
        assessor_name: "Chuyên viên C",
        assessment_result: "Đề xuất trình ký",
        notes: null,
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cases/case-123/assessment",
      expect.objectContaining({
        method: "PUT",
        headers: expect.objectContaining({
          "X-Auth-User": "operator.local",
          "X-Auth-Role": "manager",
        }),
        body: JSON.stringify({
          expected_version: 2,
          assessed_on: "2026-09-07T00:00:00Z",
          assessor_name: "Chuyên viên C",
          assessment_result: "Đề xuất trình ký",
          notes: null,
        }),
      }),
    );
    expect(String(fetchMock.mock.calls[0][0])).not.toContain("/api/api/");
  });

  it("puts inspection plan updates to the canonical plan endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { case_id: "case-123", row_version: 2 } }));
    vi.stubGlobal("fetch", fetchMock);

    await upsertInspectionPlan(
      "case-123",
      {
        expected_version: 1,
        plan_start_on: "2026-09-01",
        plan_end_on: "2026-09-02",
        planning_sheet_name: "KHKT-01",
        decision_document_hint: "QD-01",
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cases/case-123/plan",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          expected_version: 1,
          plan_start_on: "2026-09-01",
          plan_end_on: "2026-09-02",
          planning_sheet_name: "KHKT-01",
          decision_document_hint: "QD-01",
        }),
      }),
    );
  });

  it("puts inspection outcome updates to the canonical outcome endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { case_id: "case-123", row_version: 2 } }));
    vi.stubGlobal("fetch", fetchMock);

    await upsertInspectionOutcome(
      "case-123",
      {
        expected_version: 1,
        inspected_on: "2026-09-03",
        inspected_to_on: "2026-09-04",
        decision_reference: "QD-02",
        bbkt_reference: "BBKT-02",
        outcome_result: "Đạt",
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cases/case-123/outcome",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          expected_version: 1,
          inspected_on: "2026-09-03",
          inspected_to_on: "2026-09-04",
          decision_reference: "QD-02",
          bbkt_reference: "BBKT-02",
          outcome_result: "Đạt",
        }),
      }),
    );
  });

  it("posts CAPA cycle creation to the canonical case endpoint with case row_version concurrency", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { capa_cycle_id: "capa-1", row_version: 1 } }));
    vi.stubGlobal("fetch", fetchMock);

    await createCapaCycle(
      "case-123",
      {
        expected_case_version: 8,
        requested_on: "2026-09-01",
        notes: "Yêu cầu khắc phục vòng 1",
      },
      { username: "operator.local", role: "inspector" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cases/case-123/capa-cycles",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_case_version: 8,
          requested_on: "2026-09-01",
          notes: "Yêu cầu khắc phục vòng 1",
        }),
      }),
    );
  });

  it("puts CAPA cycle updates to the canonical cycle endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { capa_cycle_id: "capa-1", row_version: 2 } }));
    vi.stubGlobal("fetch", fetchMock);

    await updateCapaCycle(
      "capa-1",
      {
        expected_version: 1,
        requested_on: "2026-09-02",
        notes: "Bổ sung bằng chứng",
      },
      { username: "operator.local", role: "inspector" },
      true,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/capa-cycles/capa-1",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({
          expected_version: 1,
          requested_on: "2026-09-02",
          notes: "Bổ sung bằng chứng",
        }),
      }),
    );
  });

  it("posts CAPA submit and assess commands to their dedicated endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse({ json: { capa_cycle_id: "capa-1", row_version: 3 } }));
    vi.stubGlobal("fetch", fetchMock);

    await submitCapaCycle(
      "capa-1",
      {
        expected_version: 2,
        submitted_on: "2026-09-03",
        notes: "Đã nhận khắc phục",
      },
      { username: "operator.local", role: "inspector" },
      true,
    );

    await assessCapaCycle(
      "capa-1",
      {
        expected_version: 3,
        assessed_on: "2026-09-04",
        result: "accepted",
        notes: "Đạt yêu cầu",
      },
      { username: "operator.local", role: "manager" },
      true,
    );

    expect(fetchMock.mock.calls[0][0]).toBe("/api/capa-cycles/capa-1/submit");
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_version: 2,
          submitted_on: "2026-09-03",
          notes: "Đã nhận khắc phục",
        }),
      }),
    );
    expect(fetchMock.mock.calls[1][0]).toBe("/api/capa-cycles/capa-1/assess");
    expect(fetchMock.mock.calls[1][1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          expected_version: 3,
          assessed_on: "2026-09-04",
          result: "accepted",
          notes: "Đạt yêu cầu",
        }),
      }),
    );
  });
});
