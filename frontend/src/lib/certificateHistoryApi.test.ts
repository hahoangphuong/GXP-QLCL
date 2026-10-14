import { afterEach, describe, expect, it, vi } from "vitest";
import { getBusinessEligibilityVersionHistory, getGxpCertificateVersionHistory } from "./api";
afterEach(() => vi.unstubAllGlobals());
describe("persisted history API client", () => {
  it.each([[getGxpCertificateVersionHistory, "certificates"], [getBusinessEligibilityVersionHistory, "business-eligibility-certificates"]] as const)("uses canonical encoded GET, bearer auth and cancellation: %s", async (load, path) => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ versions: [] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    await load("id/with space", { username: "reader", role: "reader" }, false, "fixture-token", controller.signal);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe(`/api/${path}/id%2Fwith%20space/versions`);
    const options = fetch.mock.calls[0][1];
    expect(options.signal).toBe(controller.signal);
    expect(options.method ?? "GET").toBe("GET");
    expect(new Headers(options.headers).get("Authorization")).toBe("Bearer fixture-token");
    expect(new Headers(options.headers).get("X-User")).toBeNull();
  });
});
