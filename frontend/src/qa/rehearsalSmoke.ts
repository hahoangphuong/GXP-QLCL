import {
  getAppStatus, getCurrentIdentity, searchFacilities, getFacilityWorkspace,
  getCaseWorkspace, listSiteGxpCertificates, getGxpCertificateDetail,
  listSiteBusinessEligibilityCertificates, getBusinessEligibilityDetail, getDocumentDetail,
} from "../lib/api";
import { loadOidcSession } from "../lib/storage";
import { isOidcSessionValid } from "../lib/oidc";

export type SmokeCheck = {
  name: string;
  outcome: "PASS" | "FAIL" | "SKIPPED";
  httpStatus?: number;
};
export type RehearsalSmokeReport = {
  verification: "READ_API_PASS" | "BLOCKED" | "FIXTURE_ONLY";
  authMode: string | null;
  deploymentSha: string | null;
  checks: SmokeCheck[];
  reads: number;
  passed: boolean;
  // This probe never imports mutation or binary APIs. Browser actions require
  // the separate read-only proxy and a manual UI smoke test.
  uiVerified: false;
  binaryVerified: false;
};

let running = false;

/** Read-only, bounded probe. Reports contain no record values, IDs or credentials. */
export async function runRehearsalSmoke(options: {
  fixture?: boolean;
  resultKey?: string;
} = {}): Promise<RehearsalSmokeReport> {
  if (running) throw new Error("Rehearsal probe already running");
  running = true;
  const report: RehearsalSmokeReport = {
    verification: "BLOCKED", authMode: null, deploymentSha: null,
    checks: [], reads: 0, passed: false, uiVerified: false, binaryVerified: false,
  };
  const check = (name: string, passed: boolean) => {
    report.checks.push({ name, outcome: passed ? "PASS" : "FAIL" });
  };
  const read = async <T>(name: string, request: () => Promise<T>): Promise<T | undefined> => {
    report.reads++;
    try {
      const value = await request();
      check(name, true);
      return value;
    } catch (error) {
      const status = (error as { status?: unknown } | null)?.status;
      report.checks.push({ name, outcome: "FAIL",
        ...(typeof status === "number" ? { httpStatus: status } : {}) });
      // Never copy server detail or exception text: they can contain dossier data.
      return undefined;
    }
  };
  try {
    const status = await read("app-status", getAppStatus);
    if (!status) return report;
    report.authMode = status.auth_mode;
    report.deploymentSha = status.deployment?.git_sha ?? null;
    const stub = options.fixture === true && status.auth_mode === "header_stub";
    check("supported-auth", stub || status.auth_mode === "google_oidc");
    if (!stub && status.auth_mode !== "google_oidc") return report;
    const session = loadOidcSession();
    const token = !stub && isOidcSessionValid(session) ? session?.token : null;
    // Also exercise the real unauthenticated 401/403 boundary when no session exists.
    const auth = { username: "fixture.reader", role: "reader" as const };
    const identity = await read("authenticated-identity", () => getCurrentIdentity(auth, stub, token));
    if (!identity || (!stub && !token)) return report;
    const page = await read("facility-search", () => searchFacilities({ limit: 10 }, auth, stub, token));
    if (!page) return report;
    const selected = options.resultKey
      ? page.items.find(item => item.result_key === options.resultKey) : page.items[0];
    if (!selected) {
      report.checks.push({ name: "selected-facility", outcome: options.resultKey ? "FAIL" : "SKIPPED" });
      return report;
    }
    const siteId = selected.site_id;
    const lineId = selected.production_line_id ?? null;
    const facility = await read("facility-workspace", () => getFacilityWorkspace(
      siteId, auth, stub, selected.gxp_type, selected.line_code, token, lineId,
    ));
    if (!facility) return report;
    check("facility-site-identity", facility.summary.site_id === siteId);
    check("facility-line-identity", facility.summary.selected_production_line_id === lineId);
    if (report.checks.some(item => item.outcome === "FAIL")) return report;
    const caseEvent = facility.history.find(event => event.source_type === "case");
    if (caseEvent) {
      const workspace = await read("case-workspace", () => getCaseWorkspace(caseEvent.id, auth, stub, token));
      if (workspace) {
        check("case-identity", workspace.case_summary.id === caseEvent.id && workspace.case_summary.site_id === siteId);
        check("case-step-owners", [workspace.application, workspace.inspection,
          workspace.remediation, workspace.processing, workspace.evaluation_scope].every(Boolean));
        if (report.checks.some(item => item.outcome === "FAIL")) return report;
        // Deduplication is by document UUID, never filename/checklist prefix.
        const ids = [...new Set(workspace.contextual_document_actions.filter(action =>
          action.detail_available && action.document_id !== null,
        ).map(action => action.document_id!))].slice(0, 2);
        for (const [index, id] of ids.entries()) {
          const document = await read(`document-metadata-${index + 1}`, () => getDocumentDetail(id, auth, stub, token));
          if (document) {
            check(`document-identity-${index + 1}`, document.document_id === id);
            check(`document-rendition-version-identity-${index + 1}`, Array.isArray(document.variants)
              && document.variants.every(variant => Boolean(variant.id) && variant.id !== id
                && Array.isArray(variant.versions) && variant.versions.every(version =>
                  Boolean(version.id) && version.id !== id && version.id !== variant.id)));
          }
        }
        if (!ids.length) report.checks.push({ name: "document-metadata", outcome: "SKIPPED" });
      }
    } else report.checks.push({ name: "case-workspace", outcome: "SKIPPED" });
    const gps = await read("facility-gps-list", () => listSiteGxpCertificates(
      siteId, auth, stub, selected.gxp_type, selected.line_code, token, lineId,
    ));
    for (const [index, item] of (gps?.items ?? []).slice(0, 2).entries()) {
      const detail = await read(`facility-gps-detail-${index + 1}`, () => getGxpCertificateDetail(item.certificate_id, auth, stub, token));
      if (detail) check(`gps-identity-${index + 1}`, detail.certificate_id === item.certificate_id && detail.site_id === siteId);
    }
    if (gps && !gps.items.length) report.checks.push({ name: "facility-gps-detail", outcome: "SKIPPED" });
    const ddk = await read("facility-ddk-list", () => listSiteBusinessEligibilityCertificates(siteId, auth, stub, token));
    for (const [index, item] of (ddk?.items ?? []).slice(0, 2).entries()) {
      const detail = await read(`facility-ddk-detail-${index + 1}`, () => getBusinessEligibilityDetail(item.business_eligibility_certificate_id, auth, stub, token));
      if (detail) check(`ddk-identity-${index + 1}`, detail.business_eligibility_certificate_id === item.business_eligibility_certificate_id && detail.site_id === siteId);
    }
    if (ddk && !ddk.items.length) report.checks.push({ name: "facility-ddk-detail", outcome: "SKIPPED" });
    report.passed = report.checks.every(item => item.outcome === "PASS");
    if (options.fixture) report.verification = "FIXTURE_ONLY";
    else if (report.passed) report.verification = "READ_API_PASS";
    return report;
  } finally {
    running = false;
  }
}
