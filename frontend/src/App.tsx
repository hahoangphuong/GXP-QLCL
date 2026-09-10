import { useEffect, useRef, useState } from "react";
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
  const usesStubAuth = authMode === "header_stub" || authMode === null;
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
    if (oidcSession && !isOidcSessionValid(oidcSession)) {
      setOidcSession(null);
      clearOidcSession();
      return;
    }
    if (oidcSession) {
      saveOidcSession(oidcSession);
    } else {
      clearOidcSession();
    }
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

  const useStubAuth = status?.auth_mode === "header_stub" || status === null;
  const canLoadSecureApi = useStubAuth || Boolean(oidcSession?.token);

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

  const apiAccess: ApiAccess = {
    auth,
    useStubAuth,
    bearerToken: oidcSession?.token ?? null,
    canLoadSecureApi,
  };
  const isAuthenticated = status?.auth_mode === "header_stub" || Boolean(oidcSession);

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
          onOidcSession={setOidcSession}
          onOidcLogout={() => {
            window.google?.accounts?.id?.disableAutoSelect?.();
            setOidcSession(null);
          }}
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
