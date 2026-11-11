import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../../App";
import { StatusBadge } from "../../components/StatusBadge";
import { getCaseReport } from "../../lib/api";
import { formatStatusLabel } from "../../lib/presentation";
import type { CaseReportItem, CaseReportPage } from "../../types";
import { csvCell } from "./facilityReportExport";
import type { CaseWorkflowQueue } from "../search/caseNavigation";
import { caseReportParams, parseCaseReportUrl, caseStates as states, inspectionStates, type CaseReportFilters as Filters } from "./caseReportUrl";


function target(item: CaseReportItem, queue?: CaseWorkflowQueue) {
  // Resolve this canonical Case through the guarded CaseDirectOpen owner.
  // Never select Site/GxP/line from a potentially stale report projection.
  return `/cases/${encodeURIComponent(item.case_id)}` + (queue ? `?return_queue=${queue}` : "");
}

// Validate every read at the Case report owner boundary, not only CSV exports.
// A mismatched or duplicate projection must not create clickable Case/document rows.
function validatedCaseReportPage(
  page: CaseReportPage,
  expectedOffset: number,
  filters: Filters,
  isExport: boolean,
): CaseReportPage {
  if (!Array.isArray(page.items) || !Number.isSafeInteger(page.offset) || page.offset !== expectedOffset
    || !Number.isSafeInteger(page.total_count) || page.total_count < 0
    || !Number.isSafeInteger(page.limit) || page.limit < 1 || page.limit > (isExport ? 10000 : 200)
    || page.items.length > page.limit || page.items.length > Math.max(0, page.total_count - page.offset)
    || (!isExport && (page.limit !== 100 || page.offset > page.total_count
      || page.items.length !== Math.min(100, page.total_count - page.offset)))
    || (isExport && (page.total_count > 10000 || page.items.length !== page.total_count))) {
    throw new Error("API trả về phân trang Case không đầy đủ hoặc không hợp lệ.");
  }
  const ids = new Set<string>();
  for (const item of page.items) {
    if (!item || typeof item.case_id !== "string" || !item.case_id.trim()
      || typeof item.site_id !== "string" || !item.site_id.trim()
      || ids.has(item.case_id)
      || (filters.inspection_queue && !inspectionStates.includes(item.state))
      || (filters.state && item.state !== filters.state)
      || (filters.gxp_type && item.gxp_type !== filters.gxp_type)
      || (filters.opened_year && String(item.opened_year ?? "") !== filters.opened_year)) {
      throw new Error("Báo cáo Case có UUID, Site, bộ lọc hoặc danh sách bản ghi không nhất quán.");
    }
    ids.add(item.case_id);
  }
  return page;
}

export function CaseReport({ access, inspectionQueue, initialState = "", showDocumentsLink = false, returnQueue, urlState = false }: { access: ApiAccess; inspectionQueue: boolean; initialState?: string; showDocumentsLink?: boolean; returnQueue?: CaseWorkflowQueue; urlState?: boolean }) {
  const [params, setParams] = useSearchParams();
  const query = params.toString();
  const parsed = useMemo(() => parseCaseReportUrl(new URLSearchParams(query), inspectionQueue, initialState, returnQueue), [query, inspectionQueue, initialState, returnQueue]);
  const filterSignature = JSON.stringify(parsed.filters);
  const urlFilters = useMemo(() => JSON.parse(filterSignature) as Filters, [filterSignature]);
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration, inspectionQueue]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const initial: Filters = { gxp_type: "", state: initialState, q: "", opened_year: "", inspection_queue: inspectionQueue };
  const [draft, setDraft] = useState(urlState && parsed.valid ? urlFilters : initial);
  const [localActive, setActive] = useState(initial);
  const [localOffset, setOffset] = useState(0);
  const active = urlState ? urlFilters : localActive;
  const offset = urlState ? parsed.offset : localOffset;
  useEffect(() => { if (urlState && parsed.valid) setDraft(urlFilters); }, [urlState, urlFilters, parsed.valid]);
  const requestOwner = useMemo(() => ({}), [owner, active, offset]);
  const requestOwnerRef = useRef(requestOwner);
  requestOwnerRef.current = requestOwner;
  const [result, setResult] = useState<{ owner: object; data: CaseReportPage | null; error: string | null } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const guard = useRef<object | null>(null);
  const current = result?.owner === requestOwner ? result : null;
  useEffect(() => {
    guard.current = null;
    setExporting(false);
    setExportError(null);
    return () => { guard.current = null; };
  }, [owner]);
  useEffect(() => {
    guard.current = null; setExporting(false); setExportError(null);
    return () => { guard.current = null; };
  }, [requestOwner]);
  useEffect(() => {
    if (!canLoadSecureApi || (urlState && !parsed.valid)) return;
    let live = true;
    void getCaseReport({ ...active, offset }, auth, useStubAuth, bearerToken).then(
      data => {
        if (!live) return;
        try {
          setResult({ owner: requestOwner, data: validatedCaseReportPage(data, offset, active, false), error: null });
        } catch (error) {
          setResult({ owner: requestOwner, data: null, error: error instanceof Error ? error.message : "Báo cáo Case không hợp lệ." });
        }
      },
      (error: Error) => { if (live) setResult({ owner: requestOwner, data: null, error: error.message }); },
    );
    return () => { live = false; };
  }, [active, offset, owner, requestOwner, auth, useStubAuth, bearerToken, canLoadSecureApi, urlState, parsed.valid]);
  function apply(event: FormEvent) {
    event.preventDefault();
    if (guard.current) return;
    const next = { ...draft, q: draft.q.trim() };
    if (urlState) {
      const nextParams = caseReportParams(next, 0, returnQueue);
      if (!parseCaseReportUrl(nextParams, inspectionQueue, initialState, returnQueue).valid) { setExportError("Bộ lọc hồ sơ không hợp lệ."); return; }
      setParams(nextParams);
    } else { setActive(next); setOffset(0); }
    setExportError(null);
  }
  async function exportCsv() {
    if (guard.current || !canLoadSecureApi) return;
    const token = {};
    guard.current = token;
    setExporting(true);
    setExportError(null);
    try {
      const page = await getCaseReport({ ...active, export: true }, auth, useStubAuth, bearerToken);
      if (ownerRef.current !== owner || requestOwnerRef.current !== requestOwner || guard.current !== token) return;
      validatedCaseReportPage(page, 0, active, true);
      const fields = [(item: CaseReportItem) => item.reference_code ?? item.case_id, (item: CaseReportItem) => item.facility_name, (item: CaseReportItem) => item.company_name, (item: CaseReportItem) => item.gxp_type, (item: CaseReportItem) => formatStatusLabel(item.state), (item: CaseReportItem) => item.opened_year?.toString() ?? ""];
      const lines = [["Hồ sơ", "Cơ sở", "Công ty", "GxP", "Trạng thái", "Năm"].map(csvCell).join(","), ...page.items.map(item => fields.map(field => csvCell(field(item))).join(","))];
      const url = URL.createObjectURL(new Blob(["\uFEFF" + lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" }));
      try { const a = document.createElement("a"); a.href = url; a.download = "bao-cao-ho-so.csv"; document.body.appendChild(a); a.click(); a.remove(); } finally { URL.revokeObjectURL(url); }
    } catch (error) { if (ownerRef.current === owner && requestOwnerRef.current === requestOwner && guard.current === token) setExportError(error instanceof Error ? error.message : "Không thể xuất báo cáo."); }
    finally { if (guard.current === token) { guard.current = null; if (ownerRef.current === owner) setExporting(false); } }
  }
  if (!canLoadSecureApi) return <p>Cần đăng nhập để xem báo cáo.</p>;
  if (urlState && !parsed.valid) return <p role="alert">Tham số báo cáo hồ sơ không hợp lệ.</p>;
  const rows = current?.data?.items ?? [];
  const total = current?.data?.total_count ?? 0;
  return <>
    <section className="panel"><form onSubmit={apply}>
      <div className="report-filter-grid">
        <label>Loại GxP<select value={draft.gxp_type} disabled={exporting} onChange={e => setDraft({ ...draft, gxp_type: e.target.value })}><option value="">Tất cả</option><option>GMP</option><option>GLP</option><option>GMPbb</option></select></label>
        <label>Trạng thái hồ sơ<select value={draft.state} disabled={exporting} onChange={e => setDraft({ ...draft, state: e.target.value })}><option value="">Tất cả</option>{(inspectionQueue ? inspectionStates : states).map(state => <option key={state} value={state}>{formatStatusLabel(state)}</option>)}</select></label>
        <label>Cơ sở, công ty hoặc mã hồ sơ<input value={draft.q} disabled={exporting} onChange={e => setDraft({ ...draft, q: e.target.value })} /></label>
        <label>Năm hồ sơ<input type="number" min="1900" max="9999" value={draft.opened_year} disabled={exporting} onChange={e => setDraft({ ...draft, opened_year: e.target.value })} /></label>
      </div>
      <div className="report-actions"><button disabled={exporting}>Áp dụng bộ lọc</button><button type="button" className="secondary" disabled={exporting || !current || !!current.error} onClick={() => void exportCsv()}>{exporting ? "Đang xuất..." : "Xuất CSV (Excel)"}</button></div>
    </form>{exportError && <p role="alert">{exportError}</p>}<p className="muted-copy">CSV UTF-8 xuất toàn bộ kết quả hiện hành, tối đa 10.000 hồ sơ; vượt giới hạn sẽ không tạo tệp.</p></section>
    <section className="panel"><div className="panel-header"><h3>{inspectionQueue ? "Hồ sơ chuẩn bị và đang kiểm tra" : "Hồ sơ đang xử lý"}</h3>{current?.data && <span aria-live="polite">{total} hồ sơ</span>}</div>
      {!current ? <p role="status">Đang tải dữ liệu...</p> : current.error ? <p role="alert">{current.error}</p> : !rows.length ? <p>Không có hồ sơ phù hợp.</p> : <div className="table-scroll"><table className="dense-table"><thead><tr><th>Hồ sơ</th><th>Cơ sở</th><th>Công ty</th><th>GxP</th><th>Trạng thái</th><th>Năm</th>{showDocumentsLink && <th>Tài liệu</th>}</tr></thead><tbody>{rows.map(item => <tr key={item.case_id}><td><Link className="text-link" state={urlState ? { caseReportReturn: `${returnQueue ? "/workflow" : "/reports"}?${caseReportParams(active, offset, returnQueue)}` } : undefined} to={target(item, returnQueue)}>{item.reference_code ?? item.case_id}</Link></td><td>{item.facility_name}</td><td>{item.company_name}</td><td>{item.gxp_type}</td><td><StatusBadge value={item.state} /></td><td>{item.opened_year ?? "—"}</td>{showDocumentsLink && <td><Link className="text-link" state={urlState ? { caseReportReturn: `/reports?${caseReportParams(active, offset)}` } : undefined} to={`/documents/cases/${encodeURIComponent(item.case_id)}`}>Xem tài liệu</Link></td>}</tr>)}</tbody></table></div>}
      {current?.data && total > 0 && <nav className="report-pagination" aria-label="Phân trang báo cáo"><button type="button" className="secondary" disabled={!offset || exporting} onClick={() => urlState ? setParams(caseReportParams(active, Math.max(0, offset - 100), returnQueue)) : setOffset(Math.max(0, offset - 100))}>Trang trước</button><span>Trang {Math.floor(offset / 100) + 1} / {Math.ceil(total / 100)}</span><button type="button" className="secondary" disabled={offset + rows.length >= total || exporting} onClick={() => urlState ? setParams(caseReportParams(active, offset + 100, returnQueue)) : setOffset(offset + 100)}>Trang sau</button></nav>}
    </section>
  </>;
}
