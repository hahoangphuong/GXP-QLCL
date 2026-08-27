import { useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { getAppStatus } from "./lib/api";
import { decodeOidcCredential, isOidcSessionValid, loadGoogleIdentityScript } from "./lib/oidc";
import { clearOidcSession, loadAuthState, loadOidcSession, saveAuthState, saveOidcSession } from "./lib/storage";
import { DashboardPage } from "./pages/DashboardPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { SearchPage } from "./pages/SearchPage";
import type { AppStatus, OidcSession, StubAuthState } from "./types";

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
  onAuthChange,
  onOidcSession,
  onOidcLogout,
}: {
  auth: StubAuthState;
  authMode: string | null;
  oidcClientId: string | null;
  oidcSession: OidcSession | null;
  onAuthChange: (value: StubAuthState) => void;
  onOidcSession: (session: OidcSession) => void;
  onOidcLogout: () => void;
}) {
  const usesStubAuth = authMode === "header_stub" || authMode === null;

  return (
    <header className="topbar">
      <div className="brand-block">
        <span className="brand-mark">GxP QLCL</span>
        <div className="brand-copy">
          <strong>Tra cứu và điều phối nghiệp vụ</strong>
        </div>
      </div>
      {usesStubAuth ? (
        <div className="auth-cluster">
          <label>
            <span>Người dùng giả lập</span>
            <input
            value={auth.username}
            onChange={(event) => onAuthChange({ ...auth, username: event.target.value })}
            placeholder="vanhanh.local"
            aria-label="Người dùng giả lập"
          />
          </label>
          <label>
            <span>Vai trò</span>
            <select
              value={auth.role}
              onChange={(event) => onAuthChange({ ...auth, role: event.target.value as StubAuthState["role"] })}
              aria-label="Vai trò"
            >
              <option value="reader">reader</option>
              <option value="inspector">inspector</option>
              <option value="manager">manager</option>
              <option value="admin">admin</option>
            </select>
          </label>
        </div>
      ) : oidcSession ? (
        <div className="auth-cluster auth-cluster-compact">
          <span className="auth-label">{oidcSession.email ?? oidcSession.name ?? "Google Workspace"}</span>
          <button className="secondary" onClick={onOidcLogout} type="button">
            Đăng xuất
          </button>
        </div>
      ) : oidcClientId ? (
        <GoogleOidcButton clientId={oidcClientId} onCredential={onOidcSession} />
      ) : (
        <div className="auth-cluster auth-cluster-compact">
          <span className="auth-label">Google OIDC chưa sẵn sàng</span>
        </div>
      )}
    </header>
  );
}

export function App() {
  const [auth, setAuth] = useState<StubAuthState>(() => loadAuthState());
  const [oidcSession, setOidcSession] = useState<OidcSession | null>(() => {
    const stored = loadOidcSession();
    return isOidcSessionValid(stored) ? stored : null;
  });
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  useEffect(() => {
    saveAuthState(auth);
  }, [auth]);

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

  const apiAccess: ApiAccess = {
    auth,
    useStubAuth: status?.auth_mode === "header_stub" || status === null,
    bearerToken: oidcSession?.token ?? null,
    canLoadSecureApi: status?.auth_mode === "header_stub" || Boolean(oidcSession?.token),
  };

  return (
    <AppShell
      canAccessAdmin={auth.role === "admin" || auth.role === "manager"}
      header={
        <AppHeader
          auth={auth}
          authMode={status?.auth_mode ?? null}
          oidcClientId={status?.auth.oidc_client_id ?? null}
          oidcSession={oidcSession}
          onAuthChange={setAuth}
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
        <Route path="/search" element={<SearchPage access={apiAccess} statusError={statusError} />} />
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
        <Route
          path="/admin/system-status"
          element={
            <PlaceholderPage
              title="Trạng thái hệ thống"
              description="Thông tin kỹ thuật đã được đẩy khỏi dashboard operator và dành cho khu vực quản trị."
            />
          }
        />
        <Route path="/cases" element={<Navigate to="/search" replace />} />
        <Route path="/cases/:caseId" element={<Navigate to="/search" replace />} />
      </Routes>
    </AppShell>
  );
}
