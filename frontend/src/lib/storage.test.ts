import { afterEach, describe, expect, it } from "vitest";

import { clearOidcSession, loadOidcSession, saveOidcSession } from "./storage";

describe("OIDC storage contract", () => {
  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("stores the OIDC session in sessionStorage instead of localStorage", () => {
    saveOidcSession({
      token: "oidc-token",
      email: "operator@example.com",
      name: "Operator",
      subject: "subject-123",
      expires_at_epoch_seconds: 2_000_000_000,
    });

    expect(window.localStorage.getItem("gxp-operator-shell-oidc")).toBeNull();
    expect(window.sessionStorage.getItem("gxp-operator-shell-oidc")).toContain("oidc-token");
    expect(loadOidcSession()).toMatchObject({
      token: "oidc-token",
      email: "operator@example.com",
    });
  });

  it("removes the OIDC session from sessionStorage on logout", () => {
    window.sessionStorage.setItem(
      "gxp-operator-shell-oidc",
      JSON.stringify({
        token: "oidc-token",
        email: "operator@example.com",
        name: "Operator",
        subject: "subject-123",
        expires_at_epoch_seconds: 2_000_000_000,
      }),
    );

    clearOidcSession();

    expect(window.sessionStorage.getItem("gxp-operator-shell-oidc")).toBeNull();
    expect(window.localStorage.getItem("gxp-operator-shell-oidc")).toBeNull();
  });
});
