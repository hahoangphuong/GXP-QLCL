import { afterEach, describe, expect, it, vi } from "vitest";
import { runRehearsalSmoke } from "./rehearsalSmoke";
import { readOnlyProxy, tunnelTarget, directBackendPath } from "./rehearsalProxy";

const site = "00000000-0000-4000-8000-000000000001";
const line = "00000000-0000-4000-8000-000000000002";
const caseId = "00000000-0000-4000-8000-000000000003";
const result = { result_key: "selected", site_id: site, production_line_id: line, gxp_type: "GMP", line_code: "A" };

function fixture(path: string) {
  if (path === "/api/app/status") return { auth_mode: "google_oidc", deployment: { git_sha: "runtime-sha" } };
  if (path === "/api/auth/me") return { permissions: ["workspace.read"] };
  if (path === "/api/search/facilities") return { items: [result] };
  if (path === `/api/sites/${site}/workspace`) return {
    summary: { site_id: site, selected_production_line_id: line }, history: [{ id: caseId, source_type: "case" }],
  };
  if (path === `/api/cases/${caseId}/workspace`) return {
    case_summary: { id: caseId, site_id: site }, application: {}, inspection: {}, remediation: {}, processing: {}, evaluation_scope: {},
    contextual_document_actions: ["doc-a", "doc-a", "doc-b"].map(document_id => ({ document_id, detail_available: true, original_filename: "same.docx" })),
  };
  if (path.startsWith("/api/documents/")) return { document_id: path.split("/").pop(), variants: [{ id: "rendition-id", versions: [{ id: "version-id" }] }] };
  if (path.endsWith("/gxp-certificates")) return { items: ["gps-a", "gps-b"].map(certificate_id => ({ certificate_id, certificate_number: "same-number" })) };
  if (path.startsWith("/api/certificates/")) return { certificate_id: path.split("/").pop(), site_id: site };
  if (path === `/api/sites/${site}/business-eligibility-certificates`) return { items: ["ddk-a", "ddk-b"].map(business_eligibility_certificate_id => ({ business_eligibility_certificate_id, certificate_number: "same-number" })) };
  if (path.startsWith("/api/business-eligibility-certificates/")) return { business_eligibility_certificate_id: path.split("/").pop(), site_id: site };
  throw new Error("Unexpected fixture path");
}

function response(body: unknown, status = 200) {
  return { ok: status < 400, status, statusText: "", headers: new Headers({ "Content-Type": "application/json" }), json: async () => body };
}

function setup(change?: (path: string, body: unknown) => ReturnType<typeof response>) {
  sessionStorage.setItem("gxp-operator-shell-oidc", JSON.stringify({ token: "secret-test-token", expires_at_epoch_seconds: Date.now() / 1000 + 3600 }));
  return vi.fn(async (url: string, init: RequestInit) => {
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    const path = url.split("?")[0];
    return change ? change(path, fixture(path)) : response(fixture(path));
  });
}

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

describe("bounded rehearsal probe using the real API client", () => {
  it("reads distinct UUIDs sharing filenames/numbers once, forwards canonical line and redacts its report", async () => {
    const fetch = setup(); vi.stubGlobal("fetch", fetch);
    const report = await runRehearsalSmoke({ fixture: true });
    expect(report.verification).toBe("FIXTURE_ONLY");
    expect(report.checks.every(check => check.outcome === "PASS")).toBe(true);
    expect(report.reads).toBe(13);
    expect(fetch.mock.calls.filter(([url]) => url === "/api/documents/doc-a")).toHaveLength(1);
    expect(fetch.mock.calls.filter(([url]) => url.startsWith(`/api/sites/${site}/workspace?`))[0][0]).toContain(`production_line_id=${line}`);
    for (const id of ["gps-a", "gps-b", "ddk-a", "ddk-b"]) expect(fetch.mock.calls.filter(([url]) => url.endsWith(`/${id}`))).toHaveLength(1);
    expect(JSON.stringify(report)).not.toMatch(/secret-test-token|same-number|same.docx|doc-a|gps-a/);
    expect(report.uiVerified).toBe(false);
  });

  it.each([401, 403, 409, 422])("records HTTP %s without retry or server detail", async status => {
    const fetch = setup((path, body) => path === "/api/auth/me" ? response({ detail: "sensitive dossier and token" }, status) : response(body));
    vi.stubGlobal("fetch", fetch);
    const report = await runRehearsalSmoke();
    expect(report.verification).toBe("BLOCKED");
    expect(report.checks.at(-1)).toEqual({ name: "authenticated-identity", outcome: "FAIL", httpStatus: status });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.stringify(report)).not.toContain("sensitive");
  });

  it("fails closed on header_stub for live mode", async () => {
    const fetch = setup((path, body) => response(path === "/api/app/status" ? { auth_mode: "header_stub" } : body));
    vi.stubGlobal("fetch", fetch);
    expect((await runRehearsalSmoke()).verification).toBe("BLOCKED");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not authenticate anonymously after a successful identity response", async () => {
    const fetch = setup(); sessionStorage.clear(); vi.stubGlobal("fetch", fetch);
    expect((await runRehearsalSmoke()).verification).toBe("BLOCKED");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[1][1].headers).not.toHaveProperty("Authorization");
  });

  it("keeps empty data and a stale exact target unverified", async () => {
    const fetch = setup((path, body) => response(path === "/api/search/facilities" ? { items: [] } : body));
    vi.stubGlobal("fetch", fetch);
    expect((await runRehearsalSmoke()).checks.at(-1)?.outcome).toBe("SKIPPED");
    expect((await runRehearsalSmoke({ resultKey: "missing" })).checks.at(-1)?.outcome).toBe("FAIL");
  });

  it("rejects mismatched identity without declaring read verification", async () => {
    const fetch = setup((path, body) => response(path.startsWith("/api/certificates/") ? { certificate_id: "wrong", site_id: site } : body));
    vi.stubGlobal("fetch", fetch);
    expect((await runRehearsalSmoke()).verification).toBe("BLOCKED");
  });

  it("rejects conflated document/rendition/version identities", async () => {
    const fetch = setup((path, body) => response(path.startsWith("/api/documents/")
      ? { document_id: path.split("/").pop(), variants: [{ id: "conflated", versions: [{ id: "conflated" }] }] } : body));
    vi.stubGlobal("fetch", fetch);
    const report = await runRehearsalSmoke({ fixture: true });
    expect(report.passed).toBe(false);
    expect(report.checks.find(item => item.name === "document-rendition-version-identity-1")?.outcome).toBe("FAIL");
  });

  it("stops before following a mismatched facility's history", async () => {
    const fetch = setup((path, body) => response(path.endsWith("/workspace") ? { summary: { site_id: "other-site", selected_production_line_id: line } } : body));
    vi.stubGlobal("fetch", fetch);
    expect((await runRehearsalSmoke()).verification).toBe("BLOCKED");
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it("does not leak a network exception or retry it", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("private hostname/token")); vi.stubGlobal("fetch", fetch);
    const report = await runRehearsalSmoke();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(report.checks).toEqual([{ name: "app-status", outcome: "FAIL" }]);
  });

  it("prevents overlapping probe runs and releases ownership after completion", async () => {
    let release!: (value: ReturnType<typeof response>) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise(resolve => { release = resolve; })));
    const first = runRehearsalSmoke();
    await expect(runRehearsalSmoke()).rejects.toThrow("already running");
    release(response({ auth_mode: "unsupported" })); await first;
    vi.stubGlobal("fetch", setup());
    expect((await runRehearsalSmoke({ fixture: true })).verification).toBe("FIXTURE_ONLY");
  });
});

describe("rehearsal proxy safety", () => {
  it("strips only an explicitly selected direct-FastAPI prefix", () => {
    expect(directBackendPath("/api/app/status")).toBe("/app/status");
    expect(directBackendPath("/api/search/facilities?limit=10")).toBe("/search/facilities?limit=10");
    expect(directBackendPath("/readyz")).toBe("/readyz");
    expect(directBackendPath("/apifoo")).toBe("/apifoo");
  });
  it.each(["https://example.com", "http://127.0.0.1:8000/api", "http://user:secret@localhost:8000", "http://localhost:8000/?token=secret"])("rejects a non-tunnel target %s", value => {
    expect(() => tunnelTarget(value)).toThrow();
  });
  it("accepts an explicit loopback origin", () => expect(tunnelTarget("http://127.0.0.1:8000")).toBe("http://127.0.0.1:8000"));
  it.each(["POST", "PUT", "PATCH", "DELETE"])("blocks %s before proxy forwarding", method => {
    let middleware!: (request: any, response: any, next: () => void) => void;
    const plugin = readOnlyProxy();
    (plugin.configureServer as (server: any) => void)({ middlewares: { use: (fn: typeof middleware) => { middleware = fn; } } });
    const end = vi.fn(); const next = vi.fn();
    const result = { statusCode: 0, setHeader: vi.fn(), end };
    middleware({ url: "/api/cases/case-id/transition", method }, result, next);
    expect(result.statusCode).toBe(405); expect(end).toHaveBeenCalledOnce(); expect(next).not.toHaveBeenCalled();
    middleware({ url: "/api/search/facilities", method: "GET" }, result, next);
    expect(next).toHaveBeenCalledOnce();
  });
});
