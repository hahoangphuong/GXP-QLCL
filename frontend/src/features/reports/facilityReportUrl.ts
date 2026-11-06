import { REPORT_PAGE_SIZE } from "./facilityReportExport";

export type FacilityReportFilters = { gxp_type: "GMP" | "GLP" | "GMPbb"; q: string; province: string };
export type FacilityReportLocation = { filters: FacilityReportFilters; offset: number };

export const DEFAULT_FACILITY_FILTERS: FacilityReportFilters = { gxp_type: "GMP", q: "", province: "" };
const OWNED_KEYS = ["gxp_type", "q", "province", "offset"] as const;
const CONTROL = /[\p{Cc}\p{Cf}]/u;

// An invalid bookmark cannot authorize a broader, defaulted facility query.
export function parseFacilityReportLocation(params: URLSearchParams): FacilityReportLocation | null {
  if (OWNED_KEYS.some(key => params.getAll(key).length > 1)) return null;
  const gxp = params.get("gxp_type") ?? "GMP";
  if (gxp !== "GMP" && gxp !== "GLP" && gxp !== "GMPbb") return null;
  const q = params.get("q") ?? "";
  const province = params.get("province") ?? "";
  if (q.length > 200 || province.length > 200 || CONTROL.test(q) || CONTROL.test(province)) return null;
  const rawOffset = params.get("offset");
  if (rawOffset !== null && !/^(0|[1-9][0-9]*)$/.test(rawOffset)) return null;
  const offset = rawOffset === null ? 0 : Number(rawOffset);
  if (!Number.isSafeInteger(offset) || offset < 0 || offset % REPORT_PAGE_SIZE !== 0) return null;
  return { filters: { gxp_type: gxp, q, province }, offset };
}

export function writeFacilityReportLocation(params: URLSearchParams, location: FacilityReportLocation): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of OWNED_KEYS) next.delete(key);
  next.set("report", "facilities");
  if (location.filters.gxp_type !== "GMP") next.set("gxp_type", location.filters.gxp_type);
  if (location.filters.q) next.set("q", location.filters.q);
  if (location.filters.province) next.set("province", location.filters.province);
  if (location.offset > 0) next.set("offset", String(location.offset));
  return next;
}
