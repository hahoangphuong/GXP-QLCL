import {
  type FormEvent,
  type ReactNode,
  startTransition,
  useDeferredValue,
  useEffect,
  useRef,
  useState,
} from "react";
import { NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";

import {
  getAppStatus,
  getCaseDetail,
  getDocumentDetail,
  getGenerationRun,
  listCases,
  listCompanies,
  listSites,
  prepareDocument,
  renderTemplateDocx,
} from "./lib/api";
import { decodeOidcCredential, isOidcSessionValid, loadGoogleIdentityScript } from "./lib/oidc";
import { clearOidcSession, loadAuthState, loadOidcSession, saveAuthState, saveOidcSession } from "./lib/storage";
import type {
  AppStatus,
  CaseDetail,
  CaseListItem,
  Company,
  DocumentDetail,
  DocumentGenerationPrepareRequest,
  DocumentGenerationRunStatus,
  DocumentPreparationResponse,
  DocumentRenderResponse,
  OidcSession,
  Site,
  StubAuthState,
} from "./types";

type OperatorSnapshot = {
  status: AppStatus | null;
  companies: Company[];
  sites: Site[];
  cases: CaseListItem[];
};

type LoadState = {
  loading: boolean;
  error: string | null;
};

const ROLE_OPTIONS: StubAuthState["role"][] = ["reader", "inspector", "manager", "admin"];
const FAMILY_SUGGESTIONS = [
  "DDKD_CERTIFICATE",
  "CERTIFICATE_DECISION",
  "INSPECTION_BBTD_HOSO_DK",
  "INSPECTION_CAPA_LAN_1",
  "INSPECTION_CAPA_LAN_2",
];

function useOperatorSnapshot(auth: StubAuthState, bearerToken: string | null) {
  const [snapshot, setSnapshot] = useState<OperatorSnapshot>({
    status: null,
    companies: [],
    sites: [],
    cases: [],
  });
  const [state, setState] = useState<LoadState>({ loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, error: null });
    void getAppStatus()
      .then(async (status) => {
        if (status.auth_mode === "google_oidc" && !bearerToken) {
          return { status, companies: [], sites: [], cases: [] };
        }
        const useStubAuth = status.auth_mode === "header_stub";
        const [companies, sites, cases] = await Promise.all([
          listCompanies(auth, useStubAuth, bearerToken),
          listSites(auth, useStubAuth, bearerToken),
          listCases(auth, useStubAuth, bearerToken),
        ]);
        return { status, companies, sites, cases };
      })
      .then(({ status, companies, sites, cases }) => {
        if (cancelled) {
          return;
        }
        setSnapshot({ status, companies, sites, cases });
        setState({ loading: false, error: null });
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setState({ loading: false, error: error.message });
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken]);

  return { snapshot, state };
}

function useCaseDetail(caseId: string | undefined, auth: StubAuthState, bearerToken: string | null) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [state, setState] = useState<LoadState>({ loading: false, error: null });

  useEffect(() => {
    if (!caseId) {
      setDetail(null);
      setState({ loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState({ loading: true, error: null });
    void getAppStatus()
      .then((status) => getCaseDetail(caseId, auth, status.auth_mode === "header_stub", bearerToken))
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setDetail(payload);
        setState({ loading: false, error: null });
      })
      .catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setState({ loading: false, error: error.message });
      });
    return () => {
      cancelled = true;
    };
  }, [auth, bearerToken, caseId]);

  return { detail, state };
}

function formatLabel(value: string | null | undefined, fallback = "Không rõ"): string {
  const normalized = String(value ?? "").trim();
  return normalized.length > 0 ? normalized : fallback;
}

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
          size: "large",
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
    <div className="auth-panel auth-panel-readonly">
      <p className="eyebrow">Nguồn định danh</p>
      <strong>google_oidc</strong>
      <span>Đăng nhập bằng tài khoản Google Workspace để mở giao diện vận hành.</span>
      <div ref={containerRef} />
      {error ? <span>{error}</span> : null}
    </div>
  );
}

function Header({
  auth,
  status,
  oidcSession,
  onChange,
  onOidcSession,
  onOidcLogout,
}: {
  auth: StubAuthState;
  status: AppStatus | null;
  oidcSession: OidcSession | null;
  onChange: (next: StubAuthState) => void;
  onOidcSession: (session: OidcSession) => void;
  onOidcLogout: () => void;
}) {
  const authMode = status?.auth_mode ?? null;
  const usesStubAuth = authMode === "header_stub" || authMode === null;
  const oidcClientId = status?.auth.oidc_client_id ?? null;

  return (
    <header className="shell-header">
      <div>
        <p className="eyebrow">Pha 13 Nền tảng xác thực đám mây</p>
        <h1>Buồng điều phối di trú GxP Web</h1>
      </div>
      {usesStubAuth ? (
        <div className="auth-panel">
          <label>
            <span>Người dùng giả lập</span>
            <input
              value={auth.username}
              onChange={(event) => onChange({ ...auth, username: event.target.value })}
              placeholder="vanhanh.local"
            />
          </label>
          <label>
            <span>Vai trò</span>
            <select
              value={auth.role}
              onChange={(event) =>
                onChange({ ...auth, role: event.target.value as StubAuthState["role"] })
              }
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : oidcSession ? (
        <div className="auth-panel auth-panel-readonly">
          <p className="eyebrow">Nguồn định danh</p>
          <strong>{oidcSession.email ?? oidcSession.name ?? "Người dùng Google"}</strong>
          <span>{authMode}</span>
          <button className="secondary" onClick={onOidcLogout} type="button">
            Đăng xuất
          </button>
        </div>
      ) : oidcClientId ? (
        <GoogleOidcButton clientId={oidcClientId} onCredential={onOidcSession} />
      ) : (
        <div className="auth-panel auth-panel-readonly">
          <p className="eyebrow">Nguồn định danh</p>
          <strong>{authMode}</strong>
          <span>Thiếu Google OIDC client ID trong trạng thái ứng dụng.</span>
        </div>
      )}
    </header>
  );
}

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-card">
        <p className="sidebar-kicker">Điều hướng</p>
        <nav className="sidebar-nav">
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/">
            Tổng quan
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")} to="/cases">
            Không gian hồ sơ
          </NavLink>
        </nav>
      </div>
      <div className="sidebar-card accent">
        <p className="sidebar-kicker">Nguyên tắc</p>
        <ul className="plain-list">
          <li>Frontend không bao giờ chạm vào thông tin xác thực NAS.</li>
          <li>Luồng tài liệu luôn fail-closed khi có lỗi.</li>
          <li>Logic quy trình nghiệp vụ luôn nằm ở phía máy chủ.</li>
        </ul>
      </div>
    </aside>
  );
}

function StatusCards({ status }: { status: AppStatus | null }) {
  const phaseState = status?.phases;
  const cards = [
    { label: "Nền tảng", value: status?.deployment_platform ?? "không rõ" },
    { label: "Chế độ xác thực", value: status?.auth_mode ?? "không rõ" },
    { label: "Pha 5", value: phaseState?.phase5_status ?? "không rõ" },
    { label: "Pha 6", value: phaseState?.phase6_status ?? "không rõ" },
    { label: "Pha 7", value: phaseState?.phase7_status ?? "không rõ" },
    {
      label: "Xung đột projection",
      value:
        phaseState?.current_projection_conflicts_unresolved_count === null ||
        phaseState?.current_projection_conflicts_unresolved_count === undefined
          ? "không rõ"
          : String(phaseState.current_projection_conflicts_unresolved_count),
    },
  ];

  return (
    <div className="status-grid">
      {cards.map((card) => (
        <article className="metric-card" key={card.label}>
          <p>{card.label}</p>
          <strong>{card.value}</strong>
        </article>
      ))}
    </div>
  );
}

function DashboardPage({ snapshot, state }: { snapshot: OperatorSnapshot; state: LoadState }) {
  return (
    <section className="page-stack">
      <div className="hero-card">
        <div>
          <p className="eyebrow">Trạng thái ứng dụng</p>
          <h2>Nền tảng ưu tiên backend, nay đã có giao diện vận hành</h2>
        </div>
        <p className="hero-copy">
          Giao diện này vận hành trên các API đọc có xác thực, thay đổi workflow và chạy tài liệu
          đã được xây dựng trong các Pha 8-11. Nó không tái hiện logic nghiệp vụ trong trình duyệt.
        </p>
      </div>
      {state.error ? <ErrorBanner message={state.error} /> : null}
      <StatusCards status={snapshot.status} />
      <div className="summary-grid">
        <article className="summary-card">
          <p className="eyebrow">Danh mục</p>
          <h3>{snapshot.companies.length}</h3>
          <span>công ty đã được lập chỉ mục</span>
        </article>
        <article className="summary-card">
          <p className="eyebrow">Cơ sở</p>
          <h3>{snapshot.sites.length}</h3>
          <span>cơ sở hiển thị với vai trò hiện tại</span>
        </article>
        <article className="summary-card">
          <p className="eyebrow">Hồ sơ</p>
          <h3>{snapshot.cases.length}</h3>
          <span>dòng kiểm tra có thể tra cứu trong giao diện</span>
        </article>
      </div>
      {state.loading ? <p className="muted-panel">Đang tải ảnh chụp vận hành…</p> : null}
      {!state.loading && snapshot.status?.auth_mode === "google_oidc" && snapshot.cases.length === 0 ? (
        <p className="muted-panel">Hãy đăng nhập Google để tải dữ liệu vận hành.</p>
      ) : null}
    </section>
  );
}

function CaseWorkspacePage({
  snapshot,
  auth,
  bearerToken,
}: {
  snapshot: OperatorSnapshot;
  auth: StubAuthState;
  bearerToken: string | null;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);

  const normalizedQuery = deferredQuery.trim().toLowerCase();
  const filteredCases = snapshot.cases.filter((item) => {
    if (!normalizedQuery) {
      return true;
    }
    const site = snapshot.sites.find((candidate) => candidate.id === item.site_id);
    const company = snapshot.companies.find((candidate) => candidate.id === site?.company_id);
    const haystack = [
      item.legacy_inspection_code,
      item.gxp_type,
      item.state,
      site?.site_name,
      company?.legal_name,
    ]
      .map((value) => formatLabel(value, "").toLowerCase())
      .join(" ");
    return haystack.includes(normalizedQuery);
  });

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <p className="eyebrow">Không gian vận hành</p>
          <h2>Tìm hồ sơ và kiểm tra mức sẵn sàng của tài liệu</h2>
        </div>
        <div className="search-box">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm theo cơ sở, công ty, trạng thái hoặc mã kiểm tra"
          />
        </div>
      </div>
      <div className="workspace-grid">
        <div className="list-panel">
          <div className="panel-header">
            <h3>Hàng đợi hồ sơ</h3>
            <span>{filteredCases.length} mục hiển thị</span>
          </div>
          <div className="case-list">
            {filteredCases.map((item) => {
              const site = snapshot.sites.find((candidate) => candidate.id === item.site_id);
              const company = snapshot.companies.find((candidate) => candidate.id === site?.company_id);
              const selected = selectedCaseId === item.id;
              return (
                <button
                  className={selected ? "case-row active" : "case-row"}
                  key={item.id}
                  onClick={() =>
                    startTransition(() => {
                      setSelectedCaseId(item.id);
                    })
                  }
                  type="button"
                >
                  <div>
                    <strong>{formatLabel(item.legacy_inspection_code, item.id)}</strong>
                    <span>{formatLabel(site?.site_name)}</span>
                  </div>
                  <div>
                    <span>{formatLabel(company?.short_name ?? company?.legal_name)}</span>
                    <span>{item.gxp_type}</span>
                  </div>
                  <div>
                    <span className="state-pill">{item.state}</span>
                    <span className="text-link" onClick={() => navigate(`/cases/${item.id}`)}>
                      Chi tiết
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
        <div className="detail-panel">
          {selectedCaseId ? (
            <CaseDetailWorkspace
              auth={auth}
              authMode={snapshot.status?.auth_mode ?? null}
              bearerToken={bearerToken}
              caseId={selectedCaseId}
              companies={snapshot.companies}
              sites={snapshot.sites}
            />
          ) : (
            <div className="empty-panel">
              <h3>Chọn một hồ sơ</h3>
              <p>Hãy chọn hồ sơ ở bên trái để xem ngữ cảnh workflow và chuẩn bị luồng tài liệu.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function CaseRoutePage({
  auth,
  authMode,
  bearerToken,
  companies,
  sites,
}: {
  auth: StubAuthState;
  authMode: string | null;
  bearerToken: string | null;
  companies: Company[];
  sites: Site[];
}) {
  const { caseId } = useParams();
  if (!caseId) {
    return <ErrorBanner message="Thiếu mã hồ sơ." />;
  }
  return (
    <CaseDetailWorkspace
      auth={auth}
      authMode={authMode}
      bearerToken={bearerToken}
      caseId={caseId}
      companies={companies}
      sites={sites}
      standalone
    />
  );
}

function CaseDetailWorkspace({
  auth,
  authMode,
  bearerToken,
  caseId,
  companies,
  sites,
  standalone = false,
}: {
  auth: StubAuthState;
  authMode: string | null;
  bearerToken: string | null;
  caseId: string;
  companies: Company[];
  sites: Site[];
  standalone?: boolean;
}) {
  const navigate = useNavigate();
  const { detail, state } = useCaseDetail(caseId, auth, bearerToken);
  const site = sites.find((candidate) => candidate.id === detail?.site_id);
  const company = companies.find((candidate) => candidate.id === site?.company_id);

  return (
    <div className="page-stack">
      {standalone ? (
        <button className="back-link" onClick={() => navigate("/cases")} type="button">
          ← Quay lại không gian hồ sơ
        </button>
      ) : null}
      {state.error ? <ErrorBanner message={state.error} /> : null}
      {state.loading || !detail ? (
        <div className="muted-panel">Đang tải chi tiết hồ sơ…</div>
      ) : (
        <>
          <div className="detail-card">
            <div>
              <p className="eyebrow">Chi tiết hồ sơ</p>
              <h3>{formatLabel(detail.legacy_inspection_code, detail.id)}</h3>
            </div>
            <div className="detail-grid">
              <div>
                <span>Công ty</span>
                <strong>{formatLabel(company?.legal_name)}</strong>
              </div>
              <div>
                <span>Cơ sở</span>
                <strong>{formatLabel(site?.site_name)}</strong>
              </div>
              <div>
                <span>Trạng thái</span>
                <strong>{detail.state}</strong>
              </div>
              <div>
                <span>GxP</span>
                <strong>{detail.gxp_type}</strong>
              </div>
              <div>
                <span>Loại kiểm tra</span>
                <strong>{formatLabel(detail.inspection_type)}</strong>
              </div>
              <div>
                <span>Năm mở hồ sơ</span>
                <strong>{formatLabel(detail.opened_year === null ? null : String(detail.opened_year))}</strong>
              </div>
            </div>
          </div>
          <DocumentWorkbench auth={auth} authMode={authMode} bearerToken={bearerToken} caseDetail={detail} />
        </>
      )}
    </div>
  );
}

function DocumentWorkbench({
  auth,
  authMode,
  bearerToken,
  caseDetail,
}: {
  auth: StubAuthState;
  authMode: string | null;
  bearerToken: string | null;
  caseDetail: CaseDetail;
}) {
  const usesStubAuth = authMode === "header_stub";
  const [familyCode, setFamilyCode] = useState("CERTIFICATE_DECISION");
  const [storageScope, setStorageScope] = useState("inspection_folder");
  const [gxpType, setGxpType] = useState(caseDetail.gxp_type);
  const [payloadText, setPayloadText] = useState(
    JSON.stringify(
      {
        TenCty: "Cong ty A",
      },
      null,
      2,
    ),
  );
  const [outputFilename, setOutputFilename] = useState("2. Quyet dinh cap giay.docx");
  const [idempotencyKey, setIdempotencyKey] = useState("");
  const [prepareResult, setPrepareResult] = useState<DocumentPreparationResponse | null>(null);
  const [renderResult, setRenderResult] = useState<DocumentRenderResponse | null>(null);
  const [runStatus, setRunStatus] = useState<DocumentGenerationRunStatus | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [busyAction, setBusyAction] = useState<"prepare" | "render" | "run" | "document" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setGxpType(caseDetail.gxp_type);
  }, [caseDetail.gxp_type]);

  function buildRequest(): DocumentGenerationPrepareRequest {
    let parsedPayload: Record<string, string>;
    try {
      parsedPayload = JSON.parse(payloadText) as Record<string, string>;
    } catch {
      throw new Error("Payload JSON không hợp lệ.");
    }
    return {
      family_code: familyCode,
      case_id: caseDetail.id,
      gxp_type: gxpType,
      storage_scope: storageScope,
      idempotency_key: idempotencyKey.trim() || null,
      payload: parsedPayload,
      strict_payload: true,
    };
  }

  async function handlePrepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusyAction("prepare");
    setError(null);
    try {
      const result = await prepareDocument(buildRequest(), auth, usesStubAuth, bearerToken);
      setPrepareResult(result);
      setRunStatus(null);
      setDocumentDetail(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Chuẩn bị thất bại.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleRender() {
    setBusyAction("render");
    setError(null);
    try {
      const result = await renderTemplateDocx(
        {
          ...buildRequest(),
          output_filename: outputFilename,
        },
        auth,
        usesStubAuth,
        bearerToken,
      );
      setRenderResult(result);
      setPrepareResult(null);
      const [latestRun, latestDocument] = await Promise.all([
        getGenerationRun(result.generation_run_id, auth, usesStubAuth, bearerToken),
        getDocumentDetail(result.document_id, auth, usesStubAuth, bearerToken),
      ]);
      setRunStatus(latestRun);
      setDocumentDetail(latestDocument);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Kết xuất thất bại.");
    } finally {
      setBusyAction(null);
    }
  }

  async function loadRunStatus() {
    if (!prepareResult && !renderResult) {
      return;
    }
    const generationRunId = renderResult?.generation_run_id ?? prepareResult?.generation_run_id;
    if (!generationRunId) {
      return;
    }
    setBusyAction("run");
    setError(null);
    try {
      setRunStatus(await getGenerationRun(generationRunId, auth, usesStubAuth, bearerToken));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không thể tải trạng thái lượt chạy.");
    } finally {
      setBusyAction(null);
    }
  }

  async function loadDocumentLineage() {
    if (!prepareResult && !renderResult) {
      return;
    }
    const documentId = renderResult?.document_id ?? prepareResult?.document_id;
    if (!documentId) {
      return;
    }
    setBusyAction("document");
    setError(null);
    try {
      setDocumentDetail(await getDocumentDetail(documentId, auth, usesStubAuth, bearerToken));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Không thể tải chi tiết tài liệu.");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <div className="document-shell">
      <form className="document-form" onSubmit={handlePrepare}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Quy trình tài liệu</p>
            <h3>Chuẩn bị hoặc kết xuất qua các chốt an toàn của backend</h3>
          </div>
          <div className="button-row">
            <button disabled={busyAction !== null} type="submit">
              {busyAction === "prepare" ? "Đang chuẩn bị…" : "Chuẩn bị lượt chạy"}
            </button>
            <button
              className="secondary"
              disabled={busyAction !== null}
              onClick={() => void handleRender()}
              type="button"
            >
              {busyAction === "render" ? "Đang kết xuất…" : "Kết xuất DOCX"}
            </button>
          </div>
        </div>
        <div className="form-grid">
          <label>
            <span>Mã family</span>
            <input list="family-suggestions" value={familyCode} onChange={(event) => setFamilyCode(event.target.value)} />
            <datalist id="family-suggestions">
              {FAMILY_SUGGESTIONS.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </label>
          <label>
            <span>Phạm vi lưu trữ</span>
            <input value={storageScope} onChange={(event) => setStorageScope(event.target.value)} />
          </label>
          <label>
            <span>Loại GxP</span>
            <input value={gxpType} onChange={(event) => setGxpType(event.target.value)} />
          </label>
          <label>
            <span>Tên tệp đầu ra</span>
            <input value={outputFilename} onChange={(event) => setOutputFilename(event.target.value)} />
          </label>
          <label className="wide">
            <span>Khóa idempotency</span>
            <input
              placeholder="Tùy chọn cho bước chuẩn bị; nếu để trống thì bước kết xuất sẽ tự tạo"
              value={idempotencyKey}
              onChange={(event) => setIdempotencyKey(event.target.value)}
            />
          </label>
        </div>
        <label className="wide stacked">
          <span>Payload JSON</span>
          <textarea rows={10} value={payloadText} onChange={(event) => setPayloadText(event.target.value)} />
        </label>
        <div className="hint-strip">
          <span>Liên kết cha theo hồ sơ được điền sẵn từ hồ sơ đang chọn.</span>
          <span>Các family chưa được giải quyết sẽ trả về lý do bị chặn một cách tường minh.</span>
          <span>{usesStubAuth ? "Xác thực giả lập cục bộ đang hoạt động." : "Bearer token Google OIDC đang hoạt động."}</span>
        </div>
      </form>

      {error ? <ErrorBanner message={error} /> : null}

      <div className="document-results-grid">
        <ResultCard title="Kết quả chuẩn bị">
          {prepareResult ? (
            <>
              <KeyValue label="Lượt chạy" value={prepareResult.generation_run_id} />
              <KeyValue label="Trạng thái" value={prepareResult.generation_status} />
              <KeyValue label="Chế độ template" value={prepareResult.template_readiness.scalar_replacement_mode} />
              <TagList label="Lý do bị chặn" items={prepareResult.blocked_reasons} empty="không có" />
              <TagList label="Trường payload đã dùng" items={prepareResult.payload_used_fields} empty="không có" />
            </>
          ) : (
            <p className="muted-panel">Chưa có lượt chuẩn bị nào.</p>
          )}
        </ResultCard>
        <ResultCard title="Kết quả kết xuất">
          {renderResult ? (
            <>
              <KeyValue label="Phiên bản tài liệu" value={renderResult.document_version_id} />
              <KeyValue label="Checksum" value={renderResult.checksum_sha256} />
              <KeyValue label="Đường dẫn đầu ra" value={renderResult.output_storage_relative_path} />
              <TagList label="Bookmark đã thay thế" items={renderResult.replaced_bookmarks} empty="không có" />
            </>
          ) : (
            <p className="muted-panel">Chưa có kết quả kết xuất.</p>
          )}
        </ResultCard>
      </div>

      <div className="document-results-grid">
        <ResultCard title="Trạng thái lượt chạy">
          <div className="button-row compact">
            <button className="secondary" disabled={busyAction !== null} onClick={() => void loadRunStatus()} type="button">
              {busyAction === "run" ? "Đang làm mới…" : "Làm mới lượt chạy"}
            </button>
          </div>
          {runStatus ? (
            <>
              <KeyValue label="Trạng thái lượt chạy" value={runStatus.status} />
              <KeyValue label="Ứng dụng nguồn" value={runStatus.source_application} />
              <KeyValue label="Tóm tắt lỗi" value={runStatus.error_summary} />
              <TagList
                label="Trường payload"
                items={Object.entries(runStatus.input_payload_redacted ?? {}).map(([key, value]) => `${key}=${value}`)}
                empty="không có"
              />
            </>
          ) : (
            <p className="muted-panel">Chưa tải trạng thái lượt chạy.</p>
          )}
        </ResultCard>
        <ResultCard title="Dòng dõi tài liệu">
          <div className="button-row compact">
            <button
              className="secondary"
              disabled={busyAction !== null}
              onClick={() => void loadDocumentLineage()}
              type="button"
            >
              {busyAction === "document" ? "Đang làm mới…" : "Làm mới tài liệu"}
            </button>
          </div>
          {documentDetail ? (
            <>
              <KeyValue label="Family tài liệu" value={documentDetail.family_code} />
              <KeyValue label="Biến thể" value={String(documentDetail.variants.length)} />
              <KeyValue label="Lượt chạy phát sinh" value={String(documentDetail.generation_runs.length)} />
              <TagList
                label="Phiên bản hiện tại"
                items={documentDetail.variants.flatMap((variant) =>
                  variant.versions
                    .filter((version) => version.is_current)
                    .map((version) => `${variant.variant_type} v${version.version_no}`)
                )}
                empty="không có"
              />
            </>
          ) : (
            <p className="muted-panel">Chưa tải dòng dõi tài liệu.</p>
          )}
        </ResultCard>
      </div>
    </div>
  );
}

function ResultCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="result-card">
      <div className="panel-header">
        <h3>{title}</h3>
      </div>
      {children}
    </section>
  );
}

function KeyValue({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong>{formatLabel(value)}</strong>
    </div>
  );
}

function TagList({ label, items, empty }: { label: string; items: string[]; empty: string }) {
  return (
    <div className="tag-group">
      <span>{label}</span>
      <div className="tag-list">
        {items.length === 0 ? <span className="tag muted">{empty}</span> : null}
        {items.map((item) => (
          <span className="tag" key={item}>
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="error-banner">
      <strong>Yêu cầu thất bại.</strong>
      <span>{message}</span>
    </div>
  );
}

export function App() {
  const [auth, setAuth] = useState<StubAuthState>(() => loadAuthState());
  const [oidcSession, setOidcSession] = useState<OidcSession | null>(() => {
    const stored = loadOidcSession();
    return isOidcSessionValid(stored) ? stored : null;
  });
  const { snapshot, state } = useOperatorSnapshot(auth, oidcSession?.token ?? null);

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

  return (
    <div className="shell-root">
      <Header
        auth={auth}
        status={snapshot.status}
        oidcSession={oidcSession}
        onChange={setAuth}
        onOidcSession={setOidcSession}
        onOidcLogout={() => {
          window.google?.accounts?.id?.disableAutoSelect?.();
          setOidcSession(null);
        }}
      />
      <div className="shell-body">
        <Sidebar />
        <main className="main-column">
          <Routes>
            <Route path="/" element={<DashboardPage snapshot={snapshot} state={state} />} />
            <Route
              path="/cases"
              element={<CaseWorkspacePage snapshot={snapshot} auth={auth} bearerToken={oidcSession?.token ?? null} />}
            />
            <Route
              path="/cases/:caseId"
              element={
                <CaseRoutePage
                  auth={auth}
                  authMode={snapshot.status?.auth_mode ?? null}
                  bearerToken={oidcSession?.token ?? null}
                  companies={snapshot.companies}
                  sites={snapshot.sites}
                />
              }
            />
          </Routes>
        </main>
      </div>
    </div>
  );
}
