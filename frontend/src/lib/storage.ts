import type { OidcSession, StubAuthState } from "../types";

const STORAGE_KEY = "gxp-operator-shell-auth";
const OIDC_STORAGE_KEY = "gxp-operator-shell-oidc";

export function loadAuthState(): StubAuthState {
  if (typeof window === "undefined") {
    return { username: "operator.local", role: "inspector" };
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return { username: "operator.local", role: "inspector" };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<StubAuthState>;
    if (!parsed.username || !parsed.role) {
      return { username: "operator.local", role: "inspector" };
    }
    return {
      username: parsed.username,
      role: parsed.role,
    };
  } catch {
    return { username: "operator.local", role: "inspector" };
  }
}

export function saveAuthState(value: StubAuthState): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export function loadOidcSession(): OidcSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.sessionStorage.getItem(OIDC_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<OidcSession>;
    if (!parsed.token || typeof parsed.expires_at_epoch_seconds !== "number") {
      return null;
    }
    return {
      token: parsed.token,
      email: parsed.email ?? null,
      name: parsed.name ?? null,
      subject: parsed.subject ?? null,
      expires_at_epoch_seconds: parsed.expires_at_epoch_seconds,
    };
  } catch {
    return null;
  }
}

export function saveOidcSession(value: OidcSession): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(OIDC_STORAGE_KEY, JSON.stringify(value));
}

export function clearOidcSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(OIDC_STORAGE_KEY);
}
