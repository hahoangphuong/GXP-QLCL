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
  getGxpCertificateDetail,
  getGxpCertificateVersionHistory,
  getBusinessEligibilityDetail,
  getBusinessEligibilityVersionHistory,
  getGxpCertificateDocumentMetadata,
  getBusinessEligibilityDocumentMetadata,
  listSiteGxpCertificates,
  listSiteBusinessEligibilityCertificates,
  openCaseDocumentCurrentContent,
  upsertCaseApplication,
} from "./api";

type Fixture = Record<
  "case" | "other_case" | "site" | "document" | "conflict_document" |
  "missing_file_document" | "wrong_checksum_document" | "version" | "binary_text" |
  "gxp_certificate" | "gxp_version_old" | "gxp_version_current" |
  "gxp_scope_old" | "gxp_scope_current" | "ddk_certificate" |
  "ddk_version_old" | "ddk_version_current" | "ddk_link_current" |
  "gxp_document" | "gxp_document_variant" | "gxp_document_version" | "ddk_document",
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

it("reads actual GxP aggregate, current detail and historical version-owned scopes", async () => {
  const list = await listSiteGxpCertificates(fixture.site, auth, true, "GMP");
  expect(list.items.some(row => row.certificate_id === fixture.gxp_certificate)).toBe(true);
  const current = await getGxpCertificateDetail(fixture.gxp_certificate, auth, true);
  expect(current.certificate_id).toBe(fixture.gxp_certificate);
  expect(current.certificate_number).toBe("SYNTH-GMP-CURRENT");
  expect(current.scopes.map(scope => scope.scope_key)).toEqual(["current-scope"]);

  const history = await getGxpCertificateVersionHistory(fixture.gxp_certificate, auth, true);
  expect(history.certificate_id).toBe(fixture.gxp_certificate);
  expect(history.site_id).toBe(fixture.site);
  expect(history.case_id).toBe(fixture.case);
  expect(history.aggregate_latest_flag).toBe(false);
  expect(history.latest_version_id).toBe(fixture.gxp_version_current);
  expect(history.versions.map(version => version.certificate_version_id))
    .toEqual([fixture.gxp_version_current, fixture.gxp_version_old]);
  expect(history.versions.map(version => version.version_no)).toEqual([2, 1]);
  expect(history.versions[0].lifecycle_state).toBeNull();
  expect(history.versions[1].lifecycle_state).toBeNull();
  expect(history.versions[0].scopes).toEqual([
    expect.objectContaining({
      id: fixture.gxp_scope_current, scope_key: "current-scope",
      scope_text: "Current synthetic scope only",
    }),
  ]);
  expect(history.versions[1].scopes).toEqual([
    expect.objectContaining({
      id: fixture.gxp_scope_old, scope_key: "old-scope",
      scope_text: "Old synthetic scope only",
    }),
  ]);
});

it("reads actual DDK version history with exact-version stored FK evidence only", async () => {
  const list = await listSiteBusinessEligibilityCertificates(fixture.site, auth, true);
  expect(list.items.some(row => row.business_eligibility_certificate_id === fixture.ddk_certificate)).toBe(true);
  const detail = await getBusinessEligibilityDetail(fixture.ddk_certificate, auth, true);
  expect(detail.business_eligibility_certificate_id).toBe(fixture.ddk_certificate);
  expect(detail.certificate_number).toBe("SYNTH-DDK-CURRENT");

  const history = await getBusinessEligibilityVersionHistory(fixture.ddk_certificate, auth, true);
  expect(history.business_eligibility_certificate_id).toBe(fixture.ddk_certificate);
  expect(history.site_id).toBe(fixture.site);
  expect(history.aggregate_latest_flag).toBe(false);
  expect(history.latest_selection_method).toBe("max_persisted_version_no");
  expect(history.gxp_source_tokens_included).toBe(false);
  expect(history.canonical_link_status).toBe("stored_fk_only_not_validated");
  expect(history.latest_version_id).toBe(fixture.ddk_version_current);
  expect(history.versions.map(v => v.business_eligibility_version_id))
    .toEqual([fixture.ddk_version_current, fixture.ddk_version_old]);
  expect(history.versions.map(v => v.version_no)).toEqual([2, 1]);
  expect(history.versions[0].stored_link_records).toEqual([
    expect.objectContaining({
      link_id: fixture.ddk_link_current,
      certificate_id: fixture.gxp_certificate,
      link_role: "source_certificate",
    }),
  ]);
  expect(history.versions[1].stored_link_records).toEqual([]);
  expect(history.versions[1].issuance_history_text)
    .toBe("Synthetic archival prose, not extra versions");
});

it("fails closed on unknown GxP/DDK history identity without retry or fallback", async () => {
  const missing = "ffffffff-ffff-ffff-ffff-ffffffffffff";
  const before = routeCalls.length;
  await expect(getGxpCertificateVersionHistory(missing, auth, true))
    .rejects.toMatchObject({ status: 404 });
  await expect(getBusinessEligibilityVersionHistory(missing, auth, true))
    .rejects.toMatchObject({ status: 404 });
  expect(routeCalls.slice(before)).toEqual([
    { path: `/certificates/${missing}/versions`, method: "GET" },
    { path: `/business-eligibility-certificates/${missing}/versions`, method: "GET" },
  ]);
});

it("uses the new Codex frontend clients with real GxP and ĐĐK metadata-only owner routes", async () => {
  const before = routeCalls.length;
  const gxp = await getGxpCertificateDocumentMetadata(fixture.gxp_certificate, auth, true);
  const ddk = await getBusinessEligibilityDocumentMetadata(fixture.ddk_certificate, auth, true);

  expect(routeCalls.slice(before)).toEqual([
    { path: `/certificates/${fixture.gxp_certificate}/document-metadata`, method: "GET" },
    { path: `/business-eligibility-certificates/${fixture.ddk_certificate}/document-metadata`, method: "GET" },
  ]);
  expect(gxp).toMatchObject({
    owner_kind: "certificate",
    owner_id: fixture.gxp_certificate,
    metadata_status: "registered_metadata_only_unverified",
    binary_verified: false,
    original_signed_document_verified: false,
  });
  expect(ddk).toMatchObject({
    owner_kind: "business_eligibility_certificate",
    owner_id: fixture.ddk_certificate,
    metadata_status: "registered_metadata_only_unverified",
    binary_verified: false,
    original_signed_document_verified: false,
  });
  expect(gxp.documents).toEqual([{
    document_id: fixture.gxp_document,
    family_code: "SYNTHETIC_GXP_METADATA",
    document_type_code: "REGISTERED_ONLY",
    title: "Synthetic unverified GxP metadata",
    registered_variant_count: 1,
    registered_version_count: 1,
    registered_current_version_count: 1,
  }]);
  expect(ddk.documents).toEqual([{
    document_id: fixture.ddk_document,
    family_code: "SYNTHETIC_DDK_METADATA",
    document_type_code: "REGISTERED_ONLY",
    title: "Synthetic unverified DDK metadata",
    registered_variant_count: 0,
    registered_version_count: 0,
    registered_current_version_count: 0,
  }]);
  // A registered version is NOT authority to claim file or signed-original proof.
  for (const result of [gxp, ddk]) {
    const serialized = JSON.stringify(result);
    for (const forbidden of ["storage_root", "storage_relative_path", "checksum_sha256",
      "original_filename", "binary_url", "download_url", "synthetic-no-binary.docx"]) {
      expect(serialized).not.toContain(forbidden);
    }
  }
});

it("does not substitute linked GxP / ĐĐK owners for missing canonical metadata owners", async () => {
  const missing = "ffffffff-ffff-ffff-ffff-ffffffffffff";
  const before = routeCalls.length;
  await expect(getGxpCertificateDocumentMetadata(missing, auth, true))
    .rejects.toMatchObject({ status: 404 });
  await expect(getBusinessEligibilityDocumentMetadata(missing, auth, true))
    .rejects.toMatchObject({ status: 404 });
  expect(routeCalls.slice(before)).toEqual([
    { path: `/certificates/${missing}/document-metadata`, method: "GET" },
    { path: `/business-eligibility-certificates/${missing}/document-metadata`, method: "GET" },
  ]);
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
