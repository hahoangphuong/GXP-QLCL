import { parseCanonicalRecordReportUrl } from "./canonicalRecordReportUrl";

/** History state is a navigation hint, never an authorization decision. */
export function reportReturnLocation(state: unknown, kind: "certificates" | "change_requests"): string | null {
  if (!state || typeof state !== "object" || !("reportReturn" in state)) return null;
  const value = state.reportReturn;
  if (typeof value !== "string" || value.length > 2048) return null;
  if (value.startsWith("/workflow?")) {
    if (kind !== "change_requests") return null;
    return parseCanonicalRecordReportUrl(
      new URLSearchParams(value.slice("/workflow?".length)),
      kind,
      "90",
      "change_requests",
      { strictKeys: true },
    ).valid ? value : null;
  }
  if (!value.startsWith("/reports?")) return null;
  return parseCanonicalRecordReportUrl(
    new URLSearchParams(value.slice("/reports?".length)),
    kind,
    "90",
    undefined,
    { strictKeys: true },
  ).valid ? value : null;
}
