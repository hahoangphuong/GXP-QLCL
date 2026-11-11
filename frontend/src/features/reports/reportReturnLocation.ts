/** History state is a navigation hint, never an authorization decision. */
export function reportReturnLocation(state: unknown, kind: "certificates" | "change_requests"): string | null {
  if (!state || typeof state !== "object" || !("reportReturn" in state)) return null;
  const value = state.reportReturn;
  if (typeof value !== "string" || value.length > 2048) return null;
  if (kind === "change_requests" && value.startsWith("/workflow?")) {
    const params = new URLSearchParams(value.slice("/workflow?".length));
    const allowed = ["queue", "state", "q", "offset"];
    const state = params.get("state") ?? "";
    const q = params.get("q") ?? "";
    const raw = params.get("offset") ?? "0";
    return allowed.every(name => params.getAll(name).length <= 1)
      && [...params.keys()].every(name => allowed.includes(name))
      && params.get("queue") === "change_requests"
      && ["", "received", "under_review"].includes(state)
      && q.length <= 200 && [...q].every(char => char.charCodeAt(0) >= 32 && char.charCodeAt(0) !== 127)
      && /^(0|[1-9]\d*)$/.test(raw) && Number.isSafeInteger(Number(raw))
      && Number(raw) % 100 === 0 ? value : null;
  }
  if (!value.startsWith("/reports?")) return null;
  const params = new URLSearchParams(value.slice("/reports?".length));
  return params.getAll("report").length === 1 && params.get("report") === kind ? value : null;
}
