/** Actual frontend API client against the independent backend-head fixture server.
 * Copied to the pinned frontend checkout only inside disposable CI.
 * Never modifies the Codex branch or uses a browser/site cookie.
 */
import { readFileSync } from "node:fs";
import { afterAll, beforeAll, expect, it, vi } from "vitest";
import {
  createInspectionCase,
  getAppStatus,
  getCaseWorkspace,
  getDocumentDetail,
  getFacilityWorkspace,
  openCaseDocumentCurrentContent,
  upsertCaseApplication,
} from "./api";

type Fixture = Record<
  "case" | "other_case" | "site" | "document" | "conflict_document" |
  "missing_file_document" | "wrong_checksum_document" | "version" | "binary_text",
  string
>;
const fixturePath = process.env.GXP_CROSS_HEAD_FIXTURE_JSON;
if (!fixturePath) throw new Error("Disposable cross-head fixture metadata path missing.");
const fixture = JSON.parse(readFileSync(fixturePath, "utf-8")) as Fixture;
const auth = { username: "ci-only-reader", role: "reader" } as const;
const backend = "http://127.0.0.1:8000";
const routeCalls: { path: string; method: string }[] = [];

beforeAll(() => {
  const realFetch = globalThis.fetch.bind(globalThis);
  vi.stubGlobal("fetch", (input: string | URL | Request, options?: RequestInit) => {
    const raw = typeof input === "string" ? input : input.toString();
    // Frontend owns /api while the deployment proxy strips this prefix
    // before forwarding to the actual FastAPI route. Reject any external URL.
    if (!raw.startsWith("/api/")) throw new Error("Cross-head test tried a non-/api request.");
    const path = raw.slice(4);
    const method = options?.method ?? "GET";
    routeCalls.push({ path, method });
    return realFetch(backend + path, options);
  });
});
afterAll(() => vi.unstubAllGlobals());

it("connects actual frontend status client to FastAPI app status", async () => {
  const result = await getAppStatus();
  expect(result.auth.mode).toBe("header_stub");
  expect(routeCalls.at(-1)).toMatchObject({ path: "/app/status", method: "GET" });
});

it("reads a real synthetic document and its exact UUID version", async () => {
  const detail = await getDocumentDetail(fixture.document, auth, true);
  expect(detail.document_id).toBe(fixture.document);
  expect(detail.case_id).toBe(fixture.case);
  const versions = detail.variants.flatMap(variant => variant.versions);
  expect(versions).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: fixture.version, is_current: true }),
  ]));
});

it("reads real synthetic document bytes through case-scoped StorageService", async () => {
  const result = await openCaseDocumentCurrentContent(
    fixture.case, fixture.document, auth, true,
  );
  // Vitest's jsdom Blob does not implement Blob.text; use the browser's
  // actual FileReader interface rather than mocking the binary response.
  const body = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(result.blob);
  });
  expect(body).toBe(fixture.binary_text);
  expect(result.filename).toBe("synthetic-current.docx");
  expect(result.contentType).toContain("application/");
});

it("returns 404 for wrong case ownership and does not expose binary bytes", async () => {
  await expect(openCaseDocumentCurrentContent(
    fixture.other_case, fixture.document, auth, true,
  )).rejects.toMatchObject({ status: 404 });
});

it("returns 404 for an unknown document via the exact frontend metadata client", async () => {
  await expect(getDocumentDetail(
    "ffffffff-ffff-ffff-ffff-ffffffffffff", auth, true,
  )).rejects.toMatchObject({ status: 404 });
});

it("returns 409 for a real document lacking a current binary without automatic retry", async () => {
  const before = routeCalls.length;
  await expect(openCaseDocumentCurrentContent(
    fixture.case, fixture.conflict_document, auth, true,
  )).rejects.toMatchObject({ status: 409 });
  expect(routeCalls.length).toBe(before + 1);
});

it("enforces real backend write RBAC for a reader; no mutation proceeds", async () => {
  await expect(createInspectionCase(
    fixture.site,
    { gxp_type: "GMP", line_code: null, applicable_standard: null },
    auth,
    true,
  )).rejects.toMatchObject({ status: 403 });
});

it("responds with real UUID-owned case and facility workspaces", async () => {
  const caseResult = await getCaseWorkspace(fixture.case, auth, true);
  expect(caseResult.case_summary.id).toBe(fixture.case);
  const facility = await getFacilityWorkspace(fixture.site, auth, true);
  expect(facility.summary.site_id).toBe(fixture.site);
});


it("enforces real optimistic-concurrency 409 across two authorized sessions", async () => {
  // Distinct users and distinct requests, with a stale token retained by A.
  // All writes are confined to a synthetic case in disposable PostgreSQL.
  const writerA = { username: "cross-head-writer-a", role: "inspector" } as const;
  const writerB = { username: "cross-head-writer-b", role: "inspector" } as const;
  const initialize = await upsertCaseApplication(
    fixture.other_case,
    { expected_version: null, dossier_code: "CI_INITIAL" },
    writerA, true,
  );
  expect(initialize.case_id).toBe(fixture.other_case);
  expect(initialize.dossier_code).toBe("CI_INITIAL");
  const staleToken = initialize.row_version;

  const winner = await upsertCaseApplication(
    fixture.other_case,
    { expected_version: staleToken, dossier_code: "CI_WINNER" },
    writerB, true,
  );
  expect(winner.row_version).toBeGreaterThan(staleToken);
  expect(winner.dossier_code).toBe("CI_WINNER");

  const callsBeforeConflict = routeCalls.length;
  const staleDraft = { expected_version: staleToken, dossier_code: "CI_STALE_DRAFT" };
  await expect(upsertCaseApplication(
    fixture.other_case, staleDraft, writerA, true,
  )).rejects.toMatchObject({ status: 409 });
  expect(routeCalls.slice(callsBeforeConflict)).toEqual([
    { path: `/cases/${fixture.other_case}/application`, method: "PUT" },
  ]);
  // A caller's stale draft/token must not be silently rewritten, retried
  // or accepted by the server after B has committed a newer version.
  expect(staleDraft).toEqual({
    expected_version: staleToken, dossier_code: "CI_STALE_DRAFT",
  });
  const workspace = await getCaseWorkspace(fixture.other_case, writerA, true);
  expect(workspace.application.row_version).toBe(winner.row_version);
  expect(workspace.application.dossier_code).toBe("CI_WINNER");
});


it.each([
  ["missing file", fixture.missing_file_document],
  ["checksum mismatch", fixture.wrong_checksum_document],
])("rejects persisted binary %s with 409 and never returns bytes", async (_kind, documentId) => {
  const before = routeCalls.length;
  await expect(openCaseDocumentCurrentContent(
    fixture.case, documentId, auth, true,
  )).rejects.toMatchObject({ status: 409 });
  expect(routeCalls.slice(before)).toEqual([
    { path: `/cases/${fixture.case}/documents/${documentId}/content`, method: "GET" },
  ]);
});
