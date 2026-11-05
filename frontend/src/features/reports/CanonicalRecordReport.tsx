import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { ApiAccess } from "../../App";
import { getCertificateReport, getChangeRequestReport } from "../../lib/api";
import type { CertificateReportItem, CertificateReportPage, ChangeRequestReportItem, ChangeRequestReportPage } from "../../types";
import { csvCell } from "./facilityReportExport";

type Kind = "certificates" | "change_requests";
type Filters = { gxp_type: string; expiry_days: string; state: string; q: string; number: string };
type Page = CertificateReportPage | ChangeRequestReportPage;
const EMPTY: Filters = { gxp_type: "", expiry_days: "90", state: "", q: "", number: "" };

function certificateLocation(item: CertificateReportItem): string {
  const params = new URLSearchParams({ site_id: item.site_id, result_key: item.result_key,
    gxp_type: item.gxp_type, certificate_id: item.certificate_id, facility_tab: "Giấy chứng nhận GxP" });
  if (item.production_line_id) params.set("production_line_id", item.production_line_id);
  if (item.line_code) params.set("line_code", item.line_code);
  return `/search?${params}`;
}

export function CanonicalRecordReport({ access, kind, showDocumentsLink = false }: { access: ApiAccess; kind: Kind; showDocumentsLink?: boolean }) {
  const { auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration, kind]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [active, setActive] = useState<Filters>(EMPTY);
  const [offset, setOffset] = useState(0);
  const [record, setRecord] = useState<{ owner: object; key: string; page: Page | null; error: string | null } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const guard = useRef<object | null>(null);
  const key = JSON.stringify([active, offset]);
  const current = record?.owner === owner && record.key === key ? record : null;
  const fetchPage = (filters: Filters, isExport: boolean, pageOffset: number): Promise<Page> =>
    kind === "certificates"
      ? getCertificateReport({ ...filters, export: isExport, offset: pageOffset }, auth, useStubAuth, bearerToken)
      : getChangeRequestReport({ state: filters.state, q: filters.q, export: isExport, offset: pageOffset }, auth, useStubAuth, bearerToken);

  useEffect(() => {
    guard.current = null;
    setExportError(null);
    setExporting(false);
    return () => { guard.current = null; };
  }, [owner]);

  useEffect(() => {
    if (!canLoadSecureApi) return;
    let live = true;
    void fetchPage(active, false, offset).then(
      page => { if (live) setRecord({ owner, key, page, error: null }); },
      (error: Error) => { if (live) setRecord({ owner, key, page: null, error: error.message }); },
    );
    return () => { live = false; };
  }, [active, offset, owner, key, auth, useStubAuth, bearerToken, canLoadSecureApi, kind]);

  function apply(event: FormEvent) {
    event.preventDefault();
    if (guard.current) return;
    setActive({ ...draft, q: draft.q.trim(), number: draft.number.trim() });
    setOffset(0);
    setExportError(null);
  }

  async function exportCsv() {
    if (guard.current || !canLoadSecureApi || !current?.page) return;
    const token = {};
    guard.current = token;
    setExporting(true);
    setExportError(null);
    try {
      const result = await fetchPage(active, true, 0);
      if (ownerRef.current !== owner || guard.current !== token) return;
      const ids = result.items.map(item => kind === "certificates"
        ? (item as CertificateReportItem).certificate_id
        : (item as ChangeRequestReportItem).change_request_id);
      if (result.offset !== 0 || result.total_count > 10000 || result.items.length !== result.total_count
        || ids.some(id => !id) || new Set(ids).size !== ids.length) {
        throw new Error("Dữ liệu xuất thiếu, vượt giới hạn hoặc trùng bản ghi.");
      }
      const columns: { title: string; get: (item: CertificateReportItem | ChangeRequestReportItem) => string }[] =
        kind === "certificates"
          ? [
              { title: "Certificate UUID", get: x => (x as CertificateReportItem).certificate_id },
              { title: "Số GCN", get: x => (x as CertificateReportItem).certificate_number ?? "" },
              { title: "Cơ sở", get: x => x.facility_name },
              { title: "Công ty", get: x => x.company_name },
              { title: "GxP", get: x => (x as CertificateReportItem).gxp_type },
              { title: "Ngày cấp", get: x => (x as CertificateReportItem).issue_date ?? "" },
              { title: "Ngày hết hạn", get: x => (x as CertificateReportItem).expiry_date ?? "" },
              { title: "Trạng thái version", get: x => (x as CertificateReportItem).lifecycle_state ?? "" },
              { title: "Tình trạng GCN", get: x => (x as CertificateReportItem).status },
            ]
          : [
              { title: "Change Request UUID", get: x => (x as ChangeRequestReportItem).change_request_id },
              { title: "Mã thay đổi legacy", get: x => (x as ChangeRequestReportItem).legacy_change_request_id?.toString() ?? "" },
              { title: "Cơ sở", get: x => x.facility_name },
              { title: "Công ty", get: x => x.company_name },
              { title: "Nội dung/phạm vi", get: x => (x as ChangeRequestReportItem).scope_label ?? "" },
              { title: "Ngày gửi", get: x => (x as ChangeRequestReportItem).submitted_on ?? "" },
              { title: "Trạng thái", get: x => (x as ChangeRequestReportItem).state },
            ];
      const csv = "\uFEFF" + [
        columns.map(x => csvCell(x.title)).join(","),
        ...result.items.map(item => columns.map(x => csvCell(x.get(item))).join(",")),
      ].join("\r\n") + "\r\n";
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = kind === "certificates" ? "bao-cao-gcn.csv" : "bao-cao-yeu-cau-thay-doi.csv";
        document.body.appendChild(anchor); anchor.click(); anchor.remove();
      } finally { URL.revokeObjectURL(url); }
    } catch (error) {
      if (ownerRef.current === owner) setExportError(error instanceof Error ? error.message : "Không thể xuất báo cáo.");
    } finally {
      if (guard.current === token) {
        guard.current = null;
        if (ownerRef.current === owner) setExporting(false);
      }
    }
  }

  if (!canLoadSecureApi) return <p>Cần đăng nhập để xem báo cáo.</p>;
  const isCert = kind === "certificates";
  const rows = current?.page?.items ?? [];
  const total = current?.page?.total_count ?? 0;
  return <>
    <section className="panel">
      <form onSubmit={apply}>
        <div className="report-filter-grid">
          {isCert && <label>Loại GxP<select value={draft.gxp_type} disabled={exporting} onChange={e => setDraft({ ...draft, gxp_type: e.target.value })}>
            <option value="">Tất cả</option><option>GMP</option><option>GLP</option><option>GMPbb</option>
          </select></label>}
          {isCert ? <label>GCN hết hạn trong<select value={draft.expiry_days} disabled={exporting} onChange={e => setDraft({ ...draft, expiry_days: e.target.value })}>
            <option value="90">90 ngày</option><option value="60">60 ngày</option><option value="30">30 ngày</option><option value="">Tất cả GCN hiện hành</option>
          </select></label> : <label>Trạng thái thay đổi<select value={draft.state} disabled={exporting} onChange={e => setDraft({ ...draft, state: e.target.value })}>
            <option value="">Tất cả chưa hoàn tất</option><option value="received">Đã tiếp nhận</option><option value="under_review">Đang xem xét</option>
          </select></label>}
          {isCert && <label>Số GCN<input value={draft.number} disabled={exporting} onChange={e => setDraft({ ...draft, number: e.target.value })} /></label>}
          <label>Tìm kiếm<input value={draft.q} disabled={exporting} onChange={e => setDraft({ ...draft, q: e.target.value })}
            placeholder={isCert ? "Cơ sở, công ty hoặc số GCN" : "Cơ sở, công ty hoặc nội dung thay đổi"} /></label>
        </div>
        <div className="report-actions"><button disabled={exporting}>Áp dụng bộ lọc</button>
          <button type="button" className="secondary" disabled={exporting || !current?.page} onClick={() => void exportCsv()}>
            {exporting ? "Đang xuất..." : "Xuất CSV (Excel)"}
          </button></div>
      </form>
      {exportError && <p role="alert">{exportError}</p>}
      <p className="muted-copy">{isCert ? "Mỗi dòng là một Certificate hiện hành và phiên bản mới nhất; trạng thái cấp phát được hiển thị riêng, không suy diễn từ ngày hết hạn." :
        "Mỗi dòng là một Change Request của Site; hệ thống không tự gán loại GxP."} Xuất tối đa 10.000 dòng.</p>
    </section>
    <section className="panel">
      <div className="panel-header"><h3>{isCert ? "GCN GxP hiện hành" : "Yêu cầu thay đổi chưa hoàn tất"}</h3>
        {current?.page && <span aria-live="polite">{total} {isCert ? "GCN" : "yêu cầu"}</span>}</div>
      {!current ? <p role="status">Đang tải dữ liệu...</p> : current.error ? <p role="alert">{current.error}</p>
        : rows.length === 0 ? <p>Không có kết quả phù hợp.</p>
        : <div className="table-scroll"><table className="dense-table"><thead><tr>
          <th>{isCert ? "Số GCN" : "Yêu cầu"}</th><th>Cơ sở</th><th>Công ty</th>
          {isCert ? <><th>GxP</th><th>Ngày cấp</th><th>Hạn GCN</th><th>Tình trạng GCN</th><th>Trạng thái version</th><th>Tài liệu đăng ký</th></>
            : <><th>Nội dung/phạm vi</th><th>Ngày gửi</th><th>Trạng thái</th>{showDocumentsLink && <th>Tài liệu</th>}</>}
        </tr></thead><tbody>
          {isCert ? (rows as CertificateReportItem[]).map(item => <tr key={item.certificate_id}>
            <td>{["GMP", "GLP", "GMPbb"].includes(item.gxp_type) ? <Link className="text-link" to={certificateLocation(item)}>{item.certificate_number ?? item.certificate_id}</Link> : <span>{item.certificate_number ?? item.certificate_id} (chưa hỗ trợ mở trực tiếp)</span>}</td>
            <td>{item.facility_name}</td><td>{item.company_name}</td><td>{item.gxp_type}</td>
            <td>{item.issue_date ?? "—"}</td><td>{item.expiry_date ?? "—"}</td><td>{item.status === "expired" ? "Hết hạn" : "Hiện hành"}</td><td>{item.lifecycle_state ?? "Chưa xác minh"}</td>
            <td><Link className="text-link" to={`/documents/certificates/${encodeURIComponent(item.certificate_id)}`}>Xem metadata</Link></td>
          </tr>) : (rows as ChangeRequestReportItem[]).map(item => <tr key={item.change_request_id}>
            <td><Link className="text-link" to={`/reports/change-requests/${encodeURIComponent(item.change_request_id)}`}>{item.legacy_change_request_id ?? item.change_request_id}</Link></td>
            <td>{item.facility_name}</td><td>{item.company_name}</td><td>{item.scope_label ?? "—"}</td>
            <td>{item.submitted_on ?? "—"}</td><td>{item.state}</td>
            {showDocumentsLink && <td><Link className="text-link" to={`/documents/change-requests/${encodeURIComponent(item.change_request_id)}`}>Xem tài liệu</Link></td>}
          </tr>)}
        </tbody></table></div>}
      {current?.page && total > 0 && <nav className="report-pagination" aria-label="Phân trang báo cáo">
        <button type="button" className="secondary" disabled={!offset || exporting} onClick={() => setOffset(Math.max(0, offset - 100))}>Trang trước</button>
        <span>Trang {Math.floor(offset / 100) + 1} / {Math.ceil(total / 100)}</span>
        <button type="button" className="secondary" disabled={offset + rows.length >= total || exporting} onClick={() => setOffset(offset + 100)}>Trang sau</button>
      </nav>}
    </section>
  </>;
}
