import type { StubAuthState } from "../types";

const STORAGE_KEY = "gxp-operator-shell-auth";

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
