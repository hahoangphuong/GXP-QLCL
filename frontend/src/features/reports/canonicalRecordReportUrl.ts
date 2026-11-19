export type CanonicalRecordReportKind = "certificates" | "change_requests";
export type CanonicalRecordReportFilters = {
  gxp_type: string;
  expiry_days: string;
  state: string;
  q: string;
  number: string;
};

export const EMPTY_CANONICAL_RECORD_REPORT_FILTERS: CanonicalRecordReportFilters = {
  gxp_type: "",
  expiry_days: "90",
  state: "",
  q: "",
  number: "",
};

export function parseCanonicalRecordReportUrl(
  params: URLSearchParams,
  kind: CanonicalRecordReportKind,
  expiryDefault: string,
  returnQueue?: "change_requests",
): { filters: CanonicalRecordReportFilters; offset: number; valid: boolean } {
  const names = kind === "certificates"
    ? ["gxp_type", "expiry_days", "number", "q", "offset"]
    : ["state", "q", "offset"];
  const routeKeys = returnQueue ? ["queue"] : ["report"];
  const unique = names.every(name => params.getAll(name).length <= 1);
  const known = [...params.keys()].every(name => [...names, ...routeKeys].includes(name));
  const filters = {
    ...EMPTY_CANONICAL_RECORD_REPORT_FILTERS,
    expiry_days: expiryDefault,
    q: params.get("q") ?? "",
  };
  if (kind === "certificates") {
    filters.gxp_type = params.get("gxp_type") ?? "";
    filters.expiry_days = params.has("expiry_days") ? params.get("expiry_days")! : expiryDefault;
    filters.number = params.get("number") ?? "";
  } else {
    filters.state = params.get("state") ?? "";
  }
  const rawOffset = params.get("offset") ?? "0";
  const offset = Number(rawOffset);
  const routeValid = returnQueue
    ? kind === "change_requests" && params.getAll("queue").length === 1
      && params.get("queue") === returnQueue && !params.has("report")
    : params.getAll("report").length === 1 && params.get("report") === kind && !params.has("queue");
  const valid = unique && known && routeValid && /^(0|[1-9]\d*)$/.test(rawOffset)
    && Number.isSafeInteger(offset) && offset % 100 === 0
    && ["", "GMP", "GLP", "GMPbb", "GSP", "GDP"].includes(filters.gxp_type)
    && ["", "30", "60", "90"].includes(filters.expiry_days)
    && ["", "received", "under_review"].includes(filters.state)
    && [filters.q, filters.number].every(value => value.length <= 200
      && [...value].every(char => char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127));
  return { filters, offset: valid ? offset : 0, valid };
}

export function canonicalRecordReportParams(
  kind: CanonicalRecordReportKind,
  filters: CanonicalRecordReportFilters,
  offset: number,
  returnQueue?: "change_requests",
): URLSearchParams {
  const next = new URLSearchParams(returnQueue ? { queue: returnQueue } : { report: kind });
  if (kind === "certificates") {
    if (filters.gxp_type) next.set("gxp_type", filters.gxp_type);
    next.set("expiry_days", filters.expiry_days);
    if (filters.number) next.set("number", filters.number);
  } else if (filters.state) {
    next.set("state", filters.state);
  }
  if (filters.q) next.set("q", filters.q);
  if (offset) next.set("offset", String(offset));
  return next;
}
