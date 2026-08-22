import type { OidcSession } from "../types";

const GOOGLE_IDENTITY_SCRIPT_ID = "google-identity-services";
const GOOGLE_IDENTITY_SCRIPT_SRC = "https://accounts.google.com/gsi/client";

type JwtPayload = {
  email?: string;
  name?: string;
  sub?: string;
  exp?: number;
};

function decodeBase64Url(value: string): string {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  return atob(padded);
}

export function decodeOidcCredential(token: string): OidcSession {
  const parts = token.split(".");
  if (parts.length !== 3) {
    throw new Error("Google OIDC credential is malformed.");
  }
  const payload = JSON.parse(decodeBase64Url(parts[1])) as JwtPayload;
  if (typeof payload.exp !== "number") {
    throw new Error("Google OIDC credential is missing exp.");
  }
  return {
    token,
    email: payload.email ?? null,
    name: payload.name ?? null,
    subject: payload.sub ?? null,
    expires_at_epoch_seconds: payload.exp,
  };
}

export function isOidcSessionValid(session: OidcSession | null, nowEpochSeconds = Date.now() / 1000): boolean {
  if (!session) {
    return false;
  }
  return session.expires_at_epoch_seconds - 30 > nowEpochSeconds;
}

export async function loadGoogleIdentityScript(): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }
  if (window.google?.accounts?.id) {
    return;
  }
  const existing = document.getElementById(GOOGLE_IDENTITY_SCRIPT_ID) as HTMLScriptElement | null;
  if (existing?.dataset.loaded === "true") {
    return;
  }
  await new Promise<void>((resolve, reject) => {
    const script = existing ?? document.createElement("script");
    script.id = GOOGLE_IDENTITY_SCRIPT_ID;
    script.src = GOOGLE_IDENTITY_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      script.dataset.loaded = "true";
      resolve();
    };
    script.onerror = () => reject(new Error("Failed to load Google Identity Services."));
    if (!existing) {
      document.head.appendChild(script);
    }
  });
}

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (config: Record<string, unknown>) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
          prompt: () => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}
