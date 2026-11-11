import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { CaseReport } from "../features/reports/CaseReport";
import { caseReportReturn } from "../features/reports/caseReportUrl";
import { CanonicalRecordReport } from "../features/reports/CanonicalRecordReport";
import { getCaseWorkspace, getChangeRequestWorkspace, getDocumentDetail, openCaseDocumentCurrentContent, openCapaCycleDocumentCurrentContent } from "../lib/api";
import type { CaseWorkspace, ContextualDocumentAction, DocumentChecklistItem, DocumentDetail } from "../types";
import { hasCurrentActiveDocumentVersion, safeDocumentDownloadName, resolveDocumentCreation } from "../features/documents/documentActions";
import { resolveDocumentWorkspace } from "../features/documents/documentNavigation";
import { EligibilitySiteDocumentBrowser } from "./EligibilitySiteDocumentBrowser";

const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Scope = "cases" | "change-requests";
type DocumentSelection = { owner: object; key: string; id: string };
type Context = {
  owner: object;
  name: string;
  subtitle: string;
  siteId: string;
  items: DocumentChecklistItem[];
  actions: ContextualDocumentAction[];
  workspace?: CaseWorkspace;
  error: string | null;
};

function documentOwnerMatches(
  document: DocumentDetail,
  item: DocumentChecklistItem,
  scope: Scope,
  id: string,
): boolean {
  if (!item.document_id || document.document_id !== item.document_id
    || (item.family_code !== null && document.family_code !== item.family_code)) return false;
  // Match the binary API's exclusive-parent contract. A document with multiple
  // business owners is ambiguous even if one UUID matches the selected row.
  const parents = [
    ["case", document.case_id],
    ["capa_cycle", document.capa_cycle_id],
    ["certificate", document.certificate_id],
    ["business_eligibility_certificate", document.business_eligibility_certificate_id],
    ["change_request", document.change_request_id],
  ].filter(([, parentId]) => parentId != null);
  if (parents.length !== 1) return false;
  if (scope === "change-requests") {
    return item.parent_scope === "change_request" && item.parent_id === id
      && parents[0][0] === "change_request" && parents[0][1] === id;
  }
  return (item.parent_scope === "case" && item.parent_id === id && parents[0][0] === "case" && parents[0][1] === id)
    || (item.parent_scope === "capa_cycle" && !!item.parent_id
      && parents[0][0] === "capa_cycle" && parents[0][1] === item.parent_id);
}

function validateChecklistOwner(items: DocumentChecklistItem[], kind: Scope, id: string, cycleIds: string[] = []): void {
  const keys = new Set<string>();
  for (const item of items) {
    const validParent = kind === "change-requests"
      ? item.parent_scope === "change_request" && item.parent_id === id
      : (item.parent_scope === "case" && item.parent_id === id)
        || (item.parent_scope === "capa_cycle" && !!item.parent_id && cycleIds.filter(cycleId => cycleId === item.parent_id).length === 1);
    if (!validParent || !item.checklist_key || keys.has(item.checklist_key)) {
      throw new Error("Checklist tài liệu có ngữ cảnh owner không khớp hoặc định danh trùng lặp.");
    }
    keys.add(item.checklist_key);
  }
}

export function DocumentsPage({ access, statusError }: { access: ApiAccess; statusError: string | null }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawKind = searchParams.get("kind");
  const kind = rawKind === "change_requests" || rawKind === "certificates" || rawKind === "business_eligibility"
    ? rawKind : "cases";
  const [directId, setDirectId] = useState("");
  const [lookupError, setLookupError] = useState<string | null>(null);
  const navigate = useNavigate();
  function selectKind(next: typeof kind) {
    if (next === kind) return;
    setSearchParams(previous => {
      const params = new URLSearchParams(previous);
      if (next === "cases") params.delete("kind");
      else params.set("kind", next);
      // Site belongs exclusively to the eligibility browse context.
      params.delete("site_id");
      return params;
    });
    setDirectId("");
    setLookupError(null);
  }
  function openById(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = directId.trim();
    if (!CANONICAL_UUID.test(id)) {
      setLookupError("Nhập UUID hợp lệ của loại hồ sơ hoặc chứng nhận đã chọn.");
      return;
    }
    setLookupError(null);
    const segment = kind === "cases" ? "cases" : kind === "change_requests" ? "change-requests"
      : kind === "certificates" ? "certificates" : "business-eligibility-certificates";
    navigate(`/documents/${segment}/${encodeURIComponent(id)}`);
  }
  if (statusError) return <ErrorState message={statusError} />;
  if (!access.canLoadSecureApi) return <EmptyState title="Cần đăng nhập" description="Đăng nhập để tra cứu danh mục tài liệu trong hồ sơ có phân quyền." />;
  return <section className="page-section">
    <header className="section-title"><div>
      <p className="eyebrow">Tài liệu</p><h2>Danh mục tài liệu theo hồ sơ</h2>
    </div><p className="section-copy">Tài liệu gắn với Case, Change Request hoặc chứng nhận được phân quyền, không phải thư mục tệp dùng chung.
      Chọn Case hoặc Change Request để xem checklist; với chứng nhận, xem metadata tài liệu đã đăng ký theo UUID.</p></header>
    <section className="panel">
      <div className="report-actions" role="group" aria-label="Loại hồ sơ tài liệu">
        <button type="button" aria-pressed={kind === "cases"} className={kind === "cases" ? "" : "secondary"} onClick={() => selectKind("cases")}>Hồ sơ kiểm tra</button>
        <button type="button" aria-pressed={kind === "change_requests"} className={kind === "change_requests" ? "" : "secondary"} onClick={() => selectKind("change_requests")}>Yêu cầu thay đổi</button>
        <button type="button" aria-pressed={kind === "certificates"} className={kind === "certificates" ? "" : "secondary"} onClick={() => selectKind("certificates")}>GCN GxP</button>
        <button type="button" aria-pressed={kind === "business_eligibility"} className={kind === "business_eligibility" ? "" : "secondary"} onClick={() => selectKind("business_eligibility")}>Giấy đủ điều kiện kinh doanh dược</button>
      </div>
      <form onSubmit={openById}>
        <label htmlFor="document-direct-uuid">Mở danh mục tài liệu theo UUID</label>
        <div className="report-actions">
          <input id="document-direct-uuid" value={directId} onChange={event => { setDirectId(event.target.value); setLookupError(null); }}
            placeholder={kind === "cases" ? "UUID của Case" : kind === "change_requests" ? "UUID của Change Request" : "UUID chứng nhận"} aria-invalid={Boolean(lookupError)} />
          <button type="submit">Mở hồ sơ</button>
        </div>
        {lookupError && <p role="alert">{lookupError}</p>}
        <p className="muted-copy">Có thể mở cả hồ sơ không còn trong hàng đợi hiện hành. UUID chỉ dùng để điều hướng; nội dung luôn được xác thực và kiểm tra quyền từ API.</p>
      </form>
      <p className="muted-copy">Chỉ đọc. Tạo, chỉnh sửa và ban hành tài liệu tiếp tục thực hiện trong workspace theo quyền và readiness hiện có. Không bật tạo QĐKT đang bị chặn.</p>
    </section>
    {kind === "cases"
      ? <CaseReport key={kind} access={access} inspectionQueue={false} showDocumentsLink />
      : kind === "change_requests" ? <CanonicalRecordReport key={kind} access={access} kind="change_requests" showDocumentsLink />
      : kind === "certificates"
        ? <><p className="muted-copy">Chọn GCN từ danh sách hiện hành để xem metadata tài liệu đã đăng ký theo Certificate UUID. Không xác minh bản gốc, chữ ký hoặc mở tải binary.</p>
            <CanonicalRecordReport key={kind} access={access} kind="certificates" initialCertificateExpiryDays="" /></>
        : <EligibilitySiteDocumentBrowser key={kind} access={access} />}
  </section>;
}

export function DocumentRegister({ access, kind }: { access: ApiAccess; kind: Scope }) {
  const location = useLocation();
  const reportReturn = kind === "cases" ? caseReportReturn(location.state) : null;
  const { caseId, changeRequestId } = useParams();
  const id = kind === "cases" ? caseId : changeRequestId;
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [id, kind, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [source, setSource] = useState<Context | null>(null);
  const [selection, setSelection] = useState<DocumentSelection | null>(null);
  const [detail, setDetail] = useState<{ owner: object; selection: DocumentSelection; value: DocumentDetail | null; error: string | null } | null>(null);
  const [filter, setFilter] = useState<"all" | "available" | "missing">("all");
  const [query, setQuery] = useState("");
  const [downloadPending, setDownloadPending] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const downloadToken = useRef<object | null>(null);
  const currentOwnerRef = useRef(owner);
  const selectedRef = useRef(selection);
  currentOwnerRef.current = owner;
  selectedRef.current = selection;
  useEffect(() => {
    downloadToken.current = null; setDownloadPending(false); setDownloadError(null);
    return () => { downloadToken.current = null; };
  }, [owner]);
  useEffect(() => { downloadToken.current = null; setDownloadPending(false); setDownloadError(null); }, [selection]);

  const context = source?.owner === owner ? source : null;
  const currentItem = selection?.owner === owner ? context?.items.find(item => item.checklist_key === selection.key && item.document_id === selection.id) ?? null : null;
  const visibleDetail = detail?.owner === owner && detail.selection === selection ? detail : null;

  useEffect(() => {
    if (!canLoadSecureApi || !id) return;
    let live = true;
    const lookup = kind === "cases"
      ? getCaseWorkspace(id, auth, useStubAuth, bearerToken).then(workspace => {
          if (workspace.case_summary.id !== id || !workspace.case_summary.site_id) throw new Error("Case UUID không khớp phản hồi hoặc thiếu Site canonical.");
          validateChecklistOwner(workspace.documents.items, kind, id, (workspace.remediation?.cycles ?? []).map(cycle => cycle.capa_cycle_id));
          return {
            name: workspace.case_summary.facility_name,
            subtitle: `Case ${id} • ${workspace.case_summary.gxp_type}`,
            siteId: workspace.case_summary.site_id,
            items: workspace.documents.items,
            actions: workspace.contextual_document_actions ?? [],
            workspace,
          };
        })
      : getChangeRequestWorkspace(id, auth, useStubAuth, bearerToken).then(workspace => {
          if (workspace.id !== id || !workspace.site_id) throw new Error("Change Request UUID không khớp phản hồi hoặc thiếu Site canonical.");
          validateChecklistOwner(workspace.documents.items, kind, id);
          return {
            name: workspace.facility_name,
            subtitle: `Yêu cầu thay đổi ${id}`,
            siteId: workspace.site_id,
            items: workspace.documents.items,
            actions: [],
          };
        });
    void lookup.then(value => {
      if (live) setSource({ owner, ...value, error: null });
    }).catch((error: Error) => {
      if (live) setSource({ owner, name: "", subtitle: "", siteId: "", items: [], actions: [], error: error.message });
    });
    return () => { live = false; };
  }, [id, owner, kind, auth, useStubAuth, bearerToken, canLoadSecureApi]);

  useEffect(() => {
    if (!canLoadSecureApi || !id || !selection || !currentItem?.document_id || !currentItem.detail_available) return;
    const item = currentItem;
    let live = true;
    void getDocumentDetail(item.document_id!, auth, useStubAuth, bearerToken).then(value => {
      if (!documentOwnerMatches(value, item, kind, id)) throw new Error("Tài liệu không thuộc ngữ cảnh hồ sơ đã chọn.");
      if (live) setDetail({ owner, selection, value, error: null });
    }).catch((error: Error) => {
      if (live) setDetail({ owner, selection, value: null, error: error.message });
    });
    return () => { live = false; };
  }, [auth, bearerToken, canLoadSecureApi, currentItem, id, kind, owner, selection, useStubAuth]);

  async function downloadCurrentFile() {
    const item = currentItem;
    const target = selection;
    const documentId = target?.id;
    if (kind !== "cases" || !canLoadSecureApi || !id || !documentId
      || !item || !item.detail_available || !visibleDetail?.value
      || !documentOwnerMatches(visibleDetail.value, item, kind, id)
      || !hasCurrentActiveDocumentVersion(visibleDetail.value) || downloadToken.current) return;
    const token = {};
    downloadToken.current = token;
    setDownloadPending(true);
    setDownloadError(null);
    try {
      const result = item.parent_scope === "case"
        ? await openCaseDocumentCurrentContent(id, documentId, auth, useStubAuth, bearerToken)
        : item.parent_scope === "capa_cycle"
          ? await openCapaCycleDocumentCurrentContent(id, item.parent_id, documentId, auth, useStubAuth, bearerToken)
          : null;
      if (!result || currentOwnerRef.current !== owner
        || selectedRef.current !== target || downloadToken.current !== token) return;
      const name = safeDocumentDownloadName(result.filename, item.original_filename);
      const url = URL.createObjectURL(result.blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
    } catch (error) {
      if (currentOwnerRef.current === owner && selectedRef.current === target
        && downloadToken.current === token) {
        setDownloadError(error instanceof Error ? error.message : "Không thể tải tệp hiện hành.");
      }
    } finally {
      if (downloadToken.current === token) {
        downloadToken.current = null;
        if (currentOwnerRef.current === owner) setDownloadPending(false);
      }
    }
  }

  if (!canLoadSecureApi) return <EmptyState title="Cần đăng nhập" description="Đăng nhập để đọc checklist tài liệu theo hồ sơ." />;
  if (!id) return <p role="alert">Thiếu định danh hồ sơ.</p>;
  const items = (context?.items ?? []).filter(item =>
    (filter === "all" || item.status === filter)
    && [item.label, item.title ?? "", item.family_code ?? "", item.original_filename ?? ""]
      .some(value => value.toLocaleLowerCase("vi").includes(query.trim().toLocaleLowerCase("vi"))),
  );
  const available = context?.items.filter(item => item.status === "available").length ?? 0;
  const missing = context?.items.filter(item => item.status === "missing").length ?? 0;

  return <section className="page-section document-register">
    <header className="section-title"><div>
      <p className="eyebrow">Tài liệu / {kind === "cases" ? "Case" : "Change Request"}</p>
      <h2>Danh mục tài liệu</h2>
    </div><Link className="text-link" to={reportReturn ?? "/documents"}>{reportReturn ? "Quay lại báo cáo hồ sơ" : "Quay lại danh sách hồ sơ"}</Link></header>
    {!context ? <p role="status">Đang tải checklist tài liệu...</p>
      : context.error ? <ErrorState message={context.error} />
      : <><section className="panel">
          <h3>{context.name}</h3>
          <p className="muted-copy">{context.subtitle}</p>
          <p>{context.items.length} mục trong checklist · {available} đã có · {missing} chưa có</p>
          {kind === "cases" && <Link className="text-link" to={`/cases/${encodeURIComponent(id)}`}>Mở Case trong workspace</Link>}
          {kind === "change-requests" && <Link className="text-link" to={`/reports/change-requests/${encodeURIComponent(id)}`}>Xem yêu cầu thay đổi</Link>}
          <div className="report-filter-grid">
            <label>Trạng thái tài liệu
              <select value={filter} onChange={event => setFilter(event.target.value as typeof filter)}>
                <option value="all">Tất cả</option><option value="available">Đã có</option><option value="missing">Chưa có</option>
              </select>
            </label>
            <label>Tìm tài liệu
              <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Tên, loại hoặc tệp" />
            </label>
          </div>
        </section>
        <section className="panel">
          <h3>Danh mục tài liệu</h3>
          {items.length === 0 ? <p>Không có mục tài liệu phù hợp.</p> :
            <div className="table-scroll"><table className="dense-table document-register-table">
              <thead><tr><th>Tài liệu</th><th>Nhóm</th><th>Trạng thái</th><th>Tệp hiện có</th><th>Ngày ban hành</th><th>Chi tiết</th><th>Hành động</th></tr></thead>
              <tbody>{items.map(item => <tr key={item.checklist_key}>
                <td>{item.label}</td>
                <td>{item.family_code ?? "—"}</td>
                <td>{item.status === "available" ? "Đã có" : "Chưa có"}</td>
                <td>{item.original_filename ?? "—"}</td>
                <td>{item.issued_on ?? "—"}</td>
                <td>{item.status === "available" && item.document_id && item.detail_available ?
                  <button type="button" className="secondary" aria-pressed={selection?.owner === owner && selection.key === item.checklist_key && selection.id === item.document_id}
                    onClick={() => { setSelection(current => current?.owner === owner && current.key === item.checklist_key && current.id === item.document_id ? current : { owner, key: item.checklist_key, id: item.document_id! }); setDownloadError(null); }}>Xem chi tiết</button> : "—"}</td>
                <td>{kind === "cases" && context.workspace ? (() => {
                  const target = resolveDocumentWorkspace(context.workspace!, id, item.checklist_key);
                  const location = target ? `/cases/${encodeURIComponent(id)}?${new URLSearchParams({ document_key: target.checklist_key })}` : `/cases/${encodeURIComponent(id)}`;
                  if (item.status === "available") return target ? <Link className="text-link" to={location}>Đến workspace tài liệu</Link> : "—";
                  const readiness = resolveDocumentCreation(context.actions, item);
                  if (!readiness) return "Chưa có thao tác tạo được xác nhận";
                  return readiness.available && readiness.create_input_readiness !== "CANONICAL_INPUT_BLOCKED"
                    ? <Link className="text-link" to={location}>Đến workspace để tạo</Link>
                    : <span title={readiness.disabled_reason ?? undefined}>Chưa sẵn sàng{readiness.disabled_reason ? `: ${readiness.disabled_reason}` : ""}</span>;
                })() : "—"}</td>
              </tr>)}</tbody>
            </table></div>}
        </section>
        {selection && currentItem && <section className="panel">
          <div className="panel-header"><h3>Chi tiết: {currentItem.label}</h3>
            <button type="button" className="secondary" onClick={() => setSelection(null)}>Đóng</button>
          </div>
          {!visibleDetail ? <p role="status">Đang tải chi tiết tài liệu...</p> :
            visibleDetail.error ? <p role="alert">{visibleDetail.error}</p> :
            visibleDetail.value && <div>
              <p>Tên: {visibleDetail.value.title ?? "Chưa có"}</p>
              <p>Loại: {visibleDetail.value.document_type_code} · Nhóm: {visibleDetail.value.family_code}</p>
              {kind === "cases" && <div className="report-actions">
                <button type="button" className="secondary"
                  disabled={downloadPending || !hasCurrentActiveDocumentVersion(visibleDetail.value)}
                  onClick={() => void downloadCurrentFile()}>
                  {downloadPending ? "Đang tải tệp..." : "Tải tệp hiện hành"}
                </button>
                {!hasCurrentActiveDocumentVersion(visibleDetail.value) &&
                  <p className="muted-copy">Chưa xác nhận phiên bản hiện hành đang hoạt động để tải.</p>}
              </div>}
              {kind === "change-requests" &&
                <p className="muted-copy">Chưa có API tải binary Change Request được xác nhận; chỉ xem metadata.</p>}
              {downloadError && <p role="alert">{downloadError}</p>}
              <h4>Biến thể và phiên bản</h4>
              {visibleDetail.value.variants.length === 0 ? <p>Chưa có biến thể tài liệu.</p> :
                <ul>{visibleDetail.value.variants.map(variant => <li key={variant.id}>
                  {variant.variant_type} ({variant.language_code}) — {variant.is_active ? "Đang sử dụng" : "Không hoạt động"}
                  <ul>{variant.versions.map(version => <li key={version.id}>
                    Phiên bản {version.version_no}: {version.original_filename ?? "Chưa có tên tệp"}
                    {version.is_current ? " (Hiện hành)" : " (Lịch sử)"}
                    {version.issued_on ? ` — ${version.issued_on}` : ""}
                  </li>)}</ul>
                </li>)}</ul>}
              <p className="muted-copy">Lịch sử phiên bản hiện chỉ có metadata; không có API tải binary lịch sử được xác nhận. Mọi thao tác tạo/ban hành vẫn ở workspace theo readiness hiện hành.</p>
            </div>}
        </section>}
      </>}
  </section>;
}
