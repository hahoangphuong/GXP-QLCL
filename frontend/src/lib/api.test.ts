import { afterEach, describe, expect, it, vi } from "vitest";

import { listCompanies } from "./api";

describe("frontend API auth contract", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends stub headers only in header_stub mode", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    await listCompanies({ username: "operator.local", role: "manager" }, true);

    expect(fetchMock).toHaveBeenCalledWith(
      "/companies",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Auth-User": "operator.local",
          "X-Auth-Role": "manager",
        }),
      }),
    );
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("sends Authorization bearer token in google_oidc mode", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    await listCompanies({ username: "operator.local", role: "manager" }, false, "oidc-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "/companies",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer oidc-token",
        }),
      }),
    );
    expect(fetchMock.mock.calls[0][1].headers["X-Auth-User"]).toBeUndefined();
  });
});
