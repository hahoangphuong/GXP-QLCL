/** History state is a navigation hint, never an authorization decision. */
export function reportReturnLocation(state: unknown, kind: "certificates" | "change_requests"): string | null {
  if (!state || typeof state !== "object" || !("reportReturn" in state)) return null;
  const value = state.reportReturn;
  if (typeof value !== "string" || value.length > 2048 || !value.startsWith("/reports?")) return null;
  const params = new URLSearchParams(value.slice("/reports?".length));
  return params.getAll("report").length === 1 && params.get("report") === kind ? value : null;
}
