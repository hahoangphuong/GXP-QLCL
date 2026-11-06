import type { CaseWorkflowQueue } from "../search/caseNavigation";

export type CaseReportFilters = { gxp_type: string; state: string; q: string; opened_year: string; inspection_queue: boolean };
export const caseStates = ["draft", "application_received", "under_assessment", "planned", "decision_issued", "inspection_in_progress", "inspection_completed", "awaiting_certificate_decision"];
export const inspectionStates = ["planned", "decision_issued", "inspection_in_progress"];

export function parseCaseReportUrl(params: URLSearchParams, inspection: boolean, initialState: string, queue?: CaseWorkflowQueue) {
  const names = ["report", "queue", "gxp_type", "state", "case_state", "q", "opened_year", "offset"];
  const alias = params.get("case_state");
  const explicit = params.get("state");
  const filters: CaseReportFilters = { gxp_type: params.get("gxp_type") ?? "", state: explicit ?? alias ?? initialState, q: params.get("q") ?? "", opened_year: params.get("opened_year") ?? "", inspection_queue: inspection };
  const raw = params.get("offset") ?? "0", offset = Number(raw);
  const year = filters.opened_year;
  const valid = names.every(name => params.getAll(name).length <= 1)
    && (queue ? (params.get("queue") === queue || (queue === "active" && !params.has("queue"))) && !params.has("report") : params.get("report") === (inspection ? "inspection" : "cases") && !params.has("queue"))
    && (alias === null || (!inspection && alias === "awaiting_certificate_decision"))
    && !(alias !== null && explicit !== null && alias !== explicit)
    && ["", "GMP", "GLP", "GMPbb"].includes(filters.gxp_type)
    && (!filters.state || (inspection ? inspectionStates : caseStates).includes(filters.state))
    && (!year || (/^\d{4}$/.test(year) && Number(year) >= 1900 && Number(year) <= 9999))
    && /^(0|[1-9]\d*)$/.test(raw) && Number.isSafeInteger(offset) && offset % 100 === 0
    && filters.q.length <= 200 && [...filters.q].every(c => { const code = c.charCodeAt(0); return code >= 32 && (code < 127 || code > 159); })
    && !params.has("expiry_days") && !params.has("number");
  return { filters, offset: valid ? offset : 0, valid };
}

export function caseReportParams(filters: CaseReportFilters, offset: number, queue?: CaseWorkflowQueue): URLSearchParams {
  const params = new URLSearchParams(queue ? { queue } : { report: filters.inspection_queue ? "inspection" : "cases" });
  if (filters.gxp_type) params.set("gxp_type", filters.gxp_type);
  // Preserve an explicit empty state for the certificate-decision queue.
  if (filters.state || queue === "certificate_decision") params.set("state", filters.state);
  if (filters.q) params.set("q", filters.q);
  if (filters.opened_year) params.set("opened_year", filters.opened_year);
  if (offset) params.set("offset", String(offset));
  return params;
}

/** Accept only internal Case report and Case queue navigation hints. */
export function caseReportReturn(state: unknown): string | null {
  if (!state || typeof state !== "object" || !("caseReportReturn" in state)) return null;
  const value = state.caseReportReturn;
  if (typeof value !== "string" || value.length > 2048) return null;
  const prefix = value.startsWith("/reports?") ? "/reports?" : value.startsWith("/workflow?") ? "/workflow?" : null;
  if (!prefix) return null;
  const params = new URLSearchParams(value.slice(prefix.length));
  const allowed = new Set(["report", "queue", "gxp_type", "state", "case_state", "q", "opened_year", "offset"]);
  if ([...params.keys()].some(key => !allowed.has(key))) return null;
  const queue = params.get("queue");
  if (prefix === "/workflow?") {
    if (queue !== "active" && queue !== "inspection" && queue !== "certificate_decision") return null;
    return parseCaseReportUrl(params, queue === "inspection", queue === "certificate_decision" ? "awaiting_certificate_decision" : "", queue).valid ? value : null;
  }
  const report = params.get("report");
  if (report !== "cases" && report !== "inspection") return null;
  return parseCaseReportUrl(params, report === "inspection", "").valid ? value : null;
}
