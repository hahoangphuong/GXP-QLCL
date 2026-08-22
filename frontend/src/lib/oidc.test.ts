import { describe, expect, it } from "vitest";

import { decodeOidcCredential, isOidcSessionValid } from "./oidc";

function buildToken(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  const header = encode({ alg: "none", typ: "JWT" });
  const body = encode(payload);
  return `${header}.${body}.signature`;
}

describe("OIDC helpers", () => {
  it("decodes the browser Google ID token payload", () => {
    const token = buildToken({
      email: "operator@example.com",
      name: "Operator",
      sub: "google-subject",
      exp: 2_000_000_000,
    });

    expect(decodeOidcCredential(token)).toEqual({
      token,
      email: "operator@example.com",
      name: "Operator",
      subject: "google-subject",
      expires_at_epoch_seconds: 2_000_000_000,
    });
  });

  it("treats near-expiry tokens as invalid", () => {
    expect(
      isOidcSessionValid(
        {
          token: "token",
          email: null,
          name: null,
          subject: null,
          expires_at_epoch_seconds: 1_000,
        },
        980,
      ),
    ).toBe(false);
  });
});
