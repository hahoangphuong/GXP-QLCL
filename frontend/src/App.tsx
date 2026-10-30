import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { PrimaryNav } from "./components/PrimaryNav";
import { getAppStatus, getCurrentIdentity } from "./lib/api";
import { decodeOidcCredential, isOidcSessionValid, loadGoogleIdentityScript } from "./lib/oidc";
import { clearOidcSession, loadAuthState, loadOidcSession, saveOidcSession } from "./lib/storage";
import { DashboardPage } from "./pages/DashboardPage";
import { AdminSystemStatusPage } from "./pages/AdminSystemStatusPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { SearchPage } from "./pages/SearchPage";
import { TermsPage } from "./pages/TermsPage";
import type { AppStatus, AuthenticatedIdentity, OidcSession, StubAuthState } from "./types";

export type ApiAccess = {
  auth: StubAuthState;
  useStubAuth: boolean;
  bearerToken: string | null;
  canLoadSecureApi: boolean;
  accessGeneration: number;
};

function GoogleOidcButton({
  clientId,
  onCredential,
}: {
  clientId: string;
  onCredential: (session: OidcSession) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadGoogleIdentityScript()
      .then(() => {
        if (cancelled || !containerRef.current || !window.google?.accounts?.id) {
          return;
        }
        containerRef.current.innerHTML = "";
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (response: { credential?: string }) => {
            if (!response.credential) {
              setError("Google không trả về ID token.");
              return;
            }
            try {
              onCredential(decodeOidcCredential(response.credential));
              setError(null);
            } catch (nextError) {
              setError(nextError instanceof Error ? nextError.message : "Không thể giải mã Google ID token.");
            }
          },
        });
        window.google.accounts.id.renderButton(containerRef.current, {
          theme: "outline",
          size: "medium",
          text: "signin_with",
          shape: "pill",
        });
        window.google.accounts.id.prompt();
      })
      .catch((nextError: Error) => {
        if (!cancelled) {
          setError(nextError.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, onCredential]);

  return (
    <div className="auth-cluster auth-cluster-compact">
      <span className="auth-label">Đăng nhập</span>
      <div ref={containerRef} />
      {error ? <span className="auth-error">{error}</span> : null}
    </div>
  );
}

function AppHeader({
  auth,
  authMode,
  oidcClientId,
  oidcSession,
  canAccessAdmin,
  onOidcSession,
  onOidcLogout,
}: {
  auth: StubAuthState;
  authMode: string | null;
  oidcClientId: string | null;
  oidcSession: OidcSession | null;
  canAccessAdmin: boolean;
  onOidcSession: (session: OidcSession) => void;
  onOidcLogout: () => void;
}) {
  const usesStubAuth = authMode === "header_stub";
  const identityLabel = oidcSession?.email ?? oidcSession?.name ?? `${auth.username} (${auth.role})`;

  return (
    <header className="topbar">
      <div className="header-brand-group">
        <img alt="GXP QLCL" className="app-logo" src="/gxp-qlcl-logo.png" />
        <div className="brand-copy">
          <strong>Quản lý GxP</strong>
          <span>Cơ sở sản xuất, kinh doanh dược phẩm</span>
        </div>
      </div>
      <PrimaryNav canAccessAdmin={canAccessAdmin} />
      <div className="header-identity-group">
        {usesStubAuth || oidcSession ? (
          <div className="auth-cluster auth-cluster-compact">
            <span className="auth-label">{identityLabel}</span>
            <button className="secondary" disabled={usesStubAuth} onClick={onOidcLogout} type="button">
              Đăng xuất
            </button>
          </div>
        ) : null}
      </div>
      {!usesStubAuth && !oidcSession && oidcClientId ? (
        <GoogleOidcButton clientId={oidcClientId} onCredential={onOidcSession} />
      ) : !usesStubAuth && !oidcClientId ? (
        <div className="auth-cluster auth-cluster-compact">
          <span className="auth-label">Google OIDC chưa sẵn sàng</span>
        </div>
      ) : null}
    </header>
  );
}

export function App() {
  const location = useLocation();
  const [auth] = useState<StubAuthState>(() => loadAuthState());
  const [oidcSession, setOidcSession] = useState<OidcSession | null>(() => {
    const stored = loadOidcSession();
    return isOidcSessionValid(stored) ? stored : null;
  });
  // This opaque generation binds client state to the credential that loaded it
  // without exposing token or principal data in URLs, DOM attributes or logs.
  const [accessGeneration, setAccessGeneration] = useState(0);
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [identity, setIdentity] = useState<AuthenticatedIdentity | null>(null);

  useEffect(() => {
    if (location.pathname === "/privacy") {
      document.title = "GXP QLCL Privacy Policy";
      return;
    }
    if (location.pathname === "/terms") {
      document.title = "GXP QLCL Terms of Service";
      return;
    }
    document.title = "GxP Web Operator Shell";
  }, [location.pathname]);

  useEffect(() => {
    if (!oidcSession) {
      clearOidcSession();
      return;
    }

    const session = oidcSession;
    let active = true;
    let timer: number | undefined;
    function checkExpiry() {
      if (!active) return;
      window.clearTimeout(timer);
      if (!isOidcSessionValid(session)) {
        active = false;
        setAccessGeneration((current) => current + 1);
        setOidcSession(null);
        clearOidcSession();
        return;
      }
      // Match the existing 30-second validity margin. Recheck on resume too:
      // suspended/background tabs may delay timers or observe a changed clock.
      const remaining = session.expires_at_epoch_seconds * 1000 - Date.now() - 30_000;
      timer = window.setTimeout(checkExpiry, Math.max(1, Math.min(remaining, 2_147_483_647)));
    }
    function onVisibilityChange() {
      if (document.visibilityState === "visible") checkExpiry();
    }
    checkExpiry();
    if (isOidcSessionValid(oidcSession)) saveOidcSession(oidcSession);
    window.addEventListener("focus", checkExpiry);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      active = false;
      window.clearTimeout(timer);
      window.removeEventListener("focus", checkExpiry);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [oidcSession]);

  useEffect(() => {
    let cancelled = false;
    void getAppStatus()
      .then((payload) => {
        if (!cancelled) {
          setStatus(payload);
          setStatusError(null);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setStatusError(error.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const useStubAuth = status?.auth_mode === "header_stub";
  const canLoadSecureApi = status !== null && (useStubAuth || Boolean(oidcSession?.token));

  useEffect(() => {
    if (!canLoadSecureApi) {
      setIdentity(null);
      return;
    }
    let cancelled = false;
    void getCurrentIdentity(auth, useStubAuth, oidcSession?.token)
      .then((payload) => {
        if (!cancelled) {
          setIdentity(payload);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIdentity(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [auth, canLoadSecureApi, oidcSession?.token, useStubAuth]);

  const acceptOidcSession = useCallback((session: OidcSession) => {
    // There is no authoritative browser-visible authorization revision. Treat
    // every accepted credential, including refresh, as a new access owner.
    setAccessGeneration((current) => current + 1);
    setOidcSession(session);
  }, []);

  const clearActiveOidcSession = useCallback(() => {
    window.google?.accounts?.id?.disableAutoSelect?.();
    setAccessGeneration((current) => current + 1);
    setOidcSession(null);
  }, []);

  const apiAccess: ApiAccess = {
    auth,
    useStubAuth,
    bearerToken: oidcSession?.token ?? null,
    canLoadSecureApi,
    accessGeneration,
  };
  const isAuthenticated = useStubAuth || Boolean(oidcSession);

  return (
    <AppShell
      showPublicLegalNav={!isAuthenticated}
      header={
        <AppHeader
          auth={auth}
          authMode={status?.auth_mode ?? null}
          canAccessAdmin={identity?.permissions.includes("admin.users") ?? false}
          oidcClientId={status?.auth.oidc_client_id ?? null}
          oidcSession={oidcSession}
          onOidcSession={acceptOidcSession}
          onOidcLogout={clearActiveOidcSession}
        />
      }
    >
      <Routes>
        <Route path="/" element={<DashboardPage access={apiAccess} statusError={statusError} />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/search" element={<SearchPage access={apiAccess} statusError={statusError} />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route
          path="/workflow"
          element={
            <PlaceholderPage
              title="Nghiệp vụ"
              description="Slice A giữ mục này như lối vào cấu trúc nghiệp vụ; các thao tác sâu hơn sẽ nối ở Slice B."
            />
          }
        />
        <Route
          path="/documents"
          element={
            <PlaceholderPage
              title="Tài liệu"
              description="Document checklist và thao tác theo loại tài liệu sẽ được gắn từ workspace ngữ cảnh thay vì file browser rời."
            />
          }
        />
        <Route
          path="/reports"
          element={
            <PlaceholderPage
              title="Báo cáo"
              description="Báo cáo tổng hợp sẽ nối sau khi Slice A ổn định dashboard và Tra cứu."
            />
          }
        />
        <Route path="/admin/system-status" element={<AdminSystemStatusPage access={apiAccess} />} />
        <Route path="/cases" element={<Navigate to="/search" replace />} />
        <Route path="/cases/:caseId" element={<Navigate to="/search" replace />} />
      </Routes>
    </AppShell>
  );
}
