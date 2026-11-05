import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { ApiAccess } from "../../App";
import { StatusBadge } from "../../components/StatusBadge";
import { getCaseReport } from "../../lib/api";
import { formatStatusLabel } from "../../lib/presentation";
import type { CaseReportItem, CaseReportPage } from "../../types";
import { csvCell } from "./facilityReportExport";

type Filters = { gxp_type: string; state: string; q: string; opened_year: string; inspection_queue: boolean };
const states = ["draft", "application_received", "under_assessment", "planned", "decision_issued", "inspection_in_progress", "inspection_completed", "awaiting_certificate_decision"];
const inspectionStates = ["planned", "decision_issued", "inspection_in_progress"];

function target(item: CaseReportItem) {
  const params = new URLSearchParams({ site_id: item.site_id, result_key: item.result_key, gxp_type: item.gxp_type, history_id: item.case_id });
  if (item.production_line_id) params.set("production_line_id", item.production_line_id);
  return `/search?${params}`;
}

export function CaseReport({ access, inspectionQueue }: { access: ApiAccess; inspectionQueue: boolean }) {
  const { auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [auth, bearerToken, useStubAuth, canLoadSecureApi, accessGeneration, inspectionQueue]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const initial: Filters = { gxp_type: "", state: "", q: "", opened_year: "", inspection_queue: inspectionQueue };
  const [draft, setDraft] = useState(initial);
  const [active, setActive] = useState(initial);
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<{ owner: object; key: string; data: CaseReportPage | null; error: string | null } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const guard = useRef<object | null>(null);
  const key = JSON.stringify([active, offset]);
  const current = result?.owner === owner && result.key === key ? result : null;
  useEffect(() => {
    guard.current = null;
    setExporting(false);
    setExportError(null);
    return () => { guard.current = null; };
  }, [owner]);
  useEffect(() => {
    if (!canLoadSecureApi) return;
    let live = true;
    void getCaseReport({ ...active, offset }, auth, useStubAuth, bearerToken).then(
      data => { if (live) setResult({ owner, key, data, error: null }); },
      (error: Error) => { if (live) setResult({ owner, key, data: null, error: error.message }); },
    );
    return () => { live = false; };
  }, [active, offset, owner, key, auth, useStubAuth, bearerToken, canLoadSecureApi]);
  function apply(event: FormEvent) {
    event.preventDefault();
    if (guard.current) return;
    setActive({ ...draft, q: draft.q.trim() });
    setOffset(0);
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
      if (ownerRef.current !== owner || guard.current !== token) return;
      if (page.offset !== 0 || page.items.length !== page.total_count || page.total_count > 10000 || page.items.some(item => !item.case_id) || new Set(page.items.map(item => item.case_id)).size !== page.items.length) throw new Error("Dữ liệu xuất không đầy đủ hoặc trùng hồ sơ.");
      const fields = [(item: CaseReportItem) => item.reference_code ?? item.case_id, (item: CaseReportItem) => item.facility_name, (item: CaseReportItem) => item.company_name, (item: CaseReportItem) => item.gxp_type, (item: CaseReportItem) => formatStatusLabel(item.state), (item: CaseReportItem) => item.opened_year?.toString() ?? ""];
      const lines = [["Hồ sơ", "Cơ sở", "Công ty", "GxP", "Trạng thái", "Năm"].map(csvCell).join(","), ...page.items.map(item => fields.map(field => csvCell(field(item))).join(","))];
      const url = URL.createObjectURL(new Blob(["\uFEFF" + lines.join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" }));
      try { const a = document.createElement("a"); a.href = url; a.download = "bao-cao-ho-so.csv"; document.body.appendChild(a); a.click(); a.remove(); } finally { URL.revokeObjectURL(url); }
    } catch (error) { if (ownerRef.current === owner) setExportError(error instanceof Error ? error.message : "Không thể xuất báo cáo."); }
    finally { if (guard.current === token) { guard.current = null; if (ownerRef.current === owner) setExporting(false); } }
  }
  if (!canLoadSecureApi) return <p>Cần đăng nhập để xem báo cáo.</p>;
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
      {!current ? <p role="status">Đang tải dữ liệu...</p> : current.error ? <p role="alert">{current.error}</p> : !rows.length ? <p>Không có hồ sơ phù hợp.</p> : <div className="table-scroll"><table className="dense-table"><thead><tr><th>Hồ sơ</th><th>Cơ sở</th><th>Công ty</th><th>GxP</th><th>Trạng thái</th><th>Năm</th></tr></thead><tbody>{rows.map(item => <tr key={item.case_id}><td><Link className="text-link" to={target(item)}>{item.reference_code ?? item.case_id}</Link></td><td>{item.facility_name}</td><td>{item.company_name}</td><td>{item.gxp_type}</td><td><StatusBadge value={item.state} /></td><td>{item.opened_year ?? "—"}</td></tr>)}</tbody></table></div>}
      {current?.data && total > 0 && <nav className="report-pagination" aria-label="Phân trang báo cáo"><button type="button" className="secondary" disabled={!offset || exporting} onClick={() => setOffset(Math.max(0, offset - 100))}>Trang trước</button><span>Trang {Math.floor(offset / 100) + 1} / {Math.ceil(total / 100)}</span><button type="button" className="secondary" disabled={offset + rows.length >= total || exporting} onClick={() => setOffset(offset + 100)}>Trang sau</button></nav>}
    </section>
  </>;
}
