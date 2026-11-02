import { afterEach, describe, expect, it } from "vitest";
import { clearOidcSession } from "./storage";

describe("OIDC storage cleanup", () => {
  afterEach(() => { window.localStorage.clear(); window.sessionStorage.clear(); });
  it("removes any legacy OIDC session from both browser stores", () => {
    window.sessionStorage.setItem("gxp-operator-shell-oidc", "synthetic-legacy-session");
    window.localStorage.setItem("gxp-operator-shell-oidc", "synthetic-legacy-session");
    clearOidcSession();
    expect(window.sessionStorage.getItem("gxp-operator-shell-oidc")).toBeNull();
    expect(window.localStorage.getItem("gxp-operator-shell-oidc")).toBeNull();
  });
});
