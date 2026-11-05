import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { CaseReport } from "../features/reports/CaseReport";
import { CanonicalRecordReport } from "../features/reports/CanonicalRecordReport";
import { getCaseWorkspace, getChangeRequestWorkspace, getDocumentDetail, openCaseDocumentCurrentContent, openCapaCycleDocumentCurrentContent } from "../lib/api";
import type { ContextualDocumentAction, DocumentChecklistItem, DocumentDetail } from "../types";
import { hasCurrentActiveDocumentVersion, safeDocumentDownloadName, resolveDocumentCreation } from "../features/documents/documentActions";

type Scope = "cases" | "change-requests";
type Context = {
  owner: object;
  name: string;
  subtitle: string;
  siteId: string;
  items: DocumentChecklistItem[];
  actions: ContextualDocumentAction[];
  error: string | null;
};

function documentOwnerMatches(
  document: DocumentDetail,
  item: DocumentChecklistItem,
  scope: Scope,
  id: string,
): boolean {
  if (document.document_id !== item.document_id) return false;
  if (scope === "change-requests") {
    return item.parent_scope === "change_request" && item.parent_id === id && document.change_request_id === id;
  }
  if (item.parent_scope === "case") {
    return item.parent_id === id && document.case_id === id;
  }
  return item.parent_scope === "capa_cycle" && document.capa_cycle_id === item.parent_id;
}

export function DocumentsPage({ access, statusError }: { access: ApiAccess; statusError: string | null }) {
  const [kind, setKind] = useState<"cases" | "change_requests">("cases");
  if (statusError) return <ErrorState message={statusError} />;
  if (!access.canLoadSecureApi) return <EmptyState title="Cần đăng nhập" description="Đăng nhập để tra cứu danh mục tài liệu trong hồ sơ có phân quyền." />;
  return <section className="page-section">
    <header className="section-title"><div>
      <p className="eyebrow">Tài liệu</p><h2>Danh mục tài liệu theo hồ sơ</h2>
    </div><p className="section-copy">Tài liệu gắn với Case hoặc Change Request thực, không phải thư mục tệp dùng chung.
      Chọn một hồ sơ để xem các tài liệu đang có và những mục còn thiếu.</p></header>
    <section className="panel">
      <div className="report-actions" role="group" aria-label="Loại hồ sơ tài liệu">
        <button type="button" aria-pressed={kind === "cases"} className={kind === "cases" ? "" : "secondary"} onClick={() => setKind("cases")}>Hồ sơ kiểm tra</button>
        <button type="button" aria-pressed={kind === "change_requests"} className={kind === "change_requests" ? "" : "secondary"} onClick={() => setKind("change_requests")}>Yêu cầu thay đổi</button>
      </div>
      <p className="muted-copy">Chỉ đọc. Tạo, chỉnh sửa và ban hành tài liệu tiếp tục thực hiện trong workspace theo quyền và readiness hiện có. Không bật tạo QĐKT đang bị chặn.</p>
    </section>
    {kind === "cases"
      ? <CaseReport key={kind} access={access} inspectionQueue={false} showDocumentsLink />
      : <CanonicalRecordReport key={kind} access={access} kind="change_requests" showDocumentsLink />}
  </section>;
}

export function DocumentRegister({ access, kind }: { access: ApiAccess; kind: Scope }) {
  const { caseId, changeRequestId } = useParams();
  const id = kind === "cases" ? caseId : changeRequestId;
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [id, kind, auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration]);
  const [source, setSource] = useState<Context | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<{ owner: object; id: string; value: DocumentDetail | null; error: string | null } | null>(null);
  const [filter, setFilter] = useState<"all" | "available" | "missing">("all");
  const [query, setQuery] = useState("");
  const [downloadPending, setDownloadPending] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const downloadToken = useRef<object | null>(null);
  const currentOwnerRef = useRef(owner);
  const selectedIdRef = useRef(selectedId);
  currentOwnerRef.current = owner;
  selectedIdRef.current = selectedId;
  useEffect(() => { downloadToken.current = null; setDownloadPending(false); setDownloadError(null); }, [owner]);

  const context = source?.owner === owner ? source : null;
  const currentItem = context?.items.find(item => item.document_id === selectedId) ?? null;
  const visibleDetail = detail?.owner === owner && detail.id === selectedId ? detail : null;

  useEffect(() => {
    if (!canLoadSecureApi || !id) return;
    let live = true;
    const lookup = kind === "cases"
      ? getCaseWorkspace(id, auth, useStubAuth, bearerToken).then(workspace => {
          if (workspace.case_summary.id !== id) throw new Error("Case UUID không khớp phản hồi.");
          return {
            name: workspace.case_summary.facility_name,
            subtitle: `Case ${id} • ${workspace.case_summary.gxp_type}`,
            siteId: workspace.case_summary.site_id,
            items: workspace.documents.items,
            actions: workspace.contextual_document_actions ?? [],
          };
        })
      : getChangeRequestWorkspace(id, auth, useStubAuth, bearerToken).then(workspace => {
          if (workspace.id !== id) throw new Error("Change Request UUID không khớp phản hồi.");
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
    if (!canLoadSecureApi || !id || !currentItem?.document_id || !currentItem.detail_available) return;
    const item = currentItem;
    let live = true;
    void getDocumentDetail(item.document_id!, auth, useStubAuth, bearerToken).then(value => {
      if (!documentOwnerMatches(value, item, kind, id)) throw new Error("Tài liệu không thuộc ngữ cảnh hồ sơ đã chọn.");
      if (live) setDetail({ owner, id: item.document_id!, value, error: null });
    }).catch((error: Error) => {
      if (live) setDetail({ owner, id: item.document_id!, value: null, error: error.message });
    });
    return () => { live = false; };
  }, [auth, bearerToken, canLoadSecureApi, currentItem, id, kind, owner, useStubAuth]);

  async function downloadCurrentFile() {
    const item = currentItem;
    const documentId = selectedId;
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
        || selectedIdRef.current !== documentId || downloadToken.current !== token) return;
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
      if (currentOwnerRef.current === owner && selectedIdRef.current === documentId
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

  return <section className="page-section">
    <header className="section-title"><div>
      <p className="eyebrow">Tài liệu / {kind === "cases" ? "Case" : "Change Request"}</p>
      <h2>Danh mục tài liệu</h2>
    </div><Link className="text-link" to="/documents">Quay lại danh sách hồ sơ</Link></header>
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
            <div className="table-scroll"><table className="dense-table">
              <thead><tr><th>Tài liệu</th><th>Nhóm</th><th>Trạng thái</th><th>Tệp hiện có</th><th>Ngày ban hành</th><th>Chi tiết</th><th>Hành động</th></tr></thead>
              <tbody>{items.map(item => <tr key={item.checklist_key}>
                <td>{item.label}</td>
                <td>{item.family_code ?? "—"}</td>
                <td>{item.status === "available" ? "Đã có" : "Chưa có"}</td>
                <td>{item.original_filename ?? "—"}</td>
                <td>{item.issued_on ?? "—"}</td>
                <td>{item.status === "available" && item.document_id && item.detail_available ?
                  <button type="button" className="secondary" aria-pressed={selectedId === item.document_id}
                    onClick={() => { setSelectedId(item.document_id); setDownloadError(null); }}>Xem chi tiết</button> : "—"}</td>
                <td>{item.status === "missing" && kind === "cases" ? (() => {
                  const readiness = resolveDocumentCreation(context.actions, item);
                  if (!readiness) return "Chưa có thao tác tạo được xác nhận";
                  return readiness.available && readiness.create_input_readiness !== "CANONICAL_INPUT_BLOCKED"
                    ? <Link className="text-link" to={`/cases/${encodeURIComponent(id)}`}>Đến workspace để tạo</Link>
                    : <span title={readiness.disabled_reason ?? undefined}>Chưa sẵn sàng{readiness.disabled_reason ? `: ${readiness.disabled_reason}` : ""}</span>;
                })() : "—"}</td>
              </tr>)}</tbody>
            </table></div>}
        </section>
        {selectedId && currentItem && <section className="panel">
          <div className="panel-header"><h3>Chi tiết: {currentItem.label}</h3>
            <button type="button" className="secondary" onClick={() => setSelectedId(null)}>Đóng</button>
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
