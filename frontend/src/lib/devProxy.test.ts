// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { ProxyOptions } from "vite";
import config from "../../vite.config.js";

describe("development API proxy", () => {
  it("forwards the API suffix to the backend as production Nginx does", () => {
    const proxy = config.server?.proxy?.["/api"] as ProxyOptions;
    expect(proxy.rewrite).toBeTypeOf("function");
    expect(proxy.rewrite?.("/api/app/status")).toBe("/app/status");
    expect(proxy.rewrite?.("/api/cases/example/workspace")).toBe("/cases/example/workspace");
    expect(proxy.rewrite?.("/apix")).toBe("/apix");
  });
});
