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

// Both report endpoints return a full slice at the requested default limit;
// export returns one bounded, complete snapshot with limit 10000.
function validatedPage(page: Page, kind: Kind, filters: Filters, expectedOffset: number, isExport: boolean): Page {
  const expectedLimit = isExport ? 10000 : 100;
  if (!page || !Array.isArray(page.items) || page.offset !== expectedOffset
    || !Number.isSafeInteger(page.total_count) || page.total_count < 0
    || page.limit !== expectedLimit || page.offset > page.total_count
    || page.items.length !== Math.min(expectedLimit, page.total_count - page.offset)
    || (isExport && page.total_count > expectedLimit)) {
    throw new Error("API trả về phân trang báo cáo không đầy đủ hoặc không hợp lệ.");
  }
  const ids = new Set<string>();
  const validId = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.trim() === value;
  for (const row of page.items) {
    if (!row || !validId(row.site_id)) throw new Error("Báo cáo thiếu Site canonical.");
    const item = row as CertificateReportItem & ChangeRequestReportItem;
    const id = kind === "certificates" ? item.certificate_id : item.change_request_id;
    if (!validId(id) || ids.has(id)) throw new Error("Báo cáo có định danh thiếu hoặc trùng.");
    ids.add(id);
    if (kind === "certificates") {
      if (!validId(item.certificate_version_id) || !validId(item.result_key) || !validId(item.gxp_type)
        || !["active", "expired"].includes(item.status)
        || (filters.gxp_type && filters.gxp_type !== item.gxp_type)) {
        throw new Error("Chứng nhận có version, ngữ cảnh hoặc loại GxP không nhất quán.");
      }
      // SQL ILIKE supports wildcards and database-specific Unicode collation.
      // Only check literal ASCII when JavaScript and SQL semantics agree.
      if (filters.number && (item.certificate_number === null || typeof item.certificate_number !== "string"
        || (/^[\x20-\x7e]+$/.test(filters.number) && !/[%_\\]/.test(filters.number)
          && /^[\x20-\x7e]*$/.test(item.certificate_number)
          && !item.certificate_number.toLowerCase().includes(filters.number.toLowerCase())))) {
        throw new Error("Số chứng nhận không khớp bộ lọc.");
      }
    } else if (!['received', 'under_review'].includes(item.state) || (filters.state && filters.state !== item.state)) {
      throw new Error("Trạng thái yêu cầu thay đổi không khớp bộ lọc.");
    }
  }
  return page;
}

function certificateLocation(item: CertificateReportItem): string {
  const params = new URLSearchParams({ site_id: item.site_id, result_key: item.result_key,
    gxp_type: item.gxp_type, certificate_id: item.certificate_id, facility_tab: "Giấy chứng nhận GxP" });
  if (item.production_line_id) params.set("production_line_id", item.production_line_id);
  if (item.line_code) params.set("line_code", item.line_code);
  return `/search?${params}`;
}

export function CanonicalRecordReport({ access, kind, showDocumentsLink = false, initialCertificateExpiryDays = "90" }: { access: ApiAccess; kind: Kind; showDocumentsLink?: boolean; initialCertificateExpiryDays?: "90" | "" }) {
  const { auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration } = access;
  const owner = useMemo(() => ({}), [auth, useStubAuth, bearerToken, canLoadSecureApi, accessGeneration, kind]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const [draft, setDraft] = useState<Filters>(() => ({ ...EMPTY, expiry_days: initialCertificateExpiryDays }));
  const [active, setActive] = useState<Filters>(() => ({ ...EMPTY, expiry_days: initialCertificateExpiryDays }));
  const [offset, setOffset] = useState(0);
  const requestOwner = useMemo(() => ({}), [owner, active, offset]);
  const [record, setRecord] = useState<{ owner: object; page: Page | null; error: string | null } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const guard = useRef<object | null>(null);
  const current = record?.owner === requestOwner ? record : null;
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
    void fetchPage(active, false, offset).then(page => {
      if (live) setRecord({ owner: requestOwner, page: validatedPage(page, kind, active, offset, false), error: null });
    }).catch((error: Error) => { if (live) setRecord({ owner: requestOwner, page: null, error: error.message }); });
    return () => { live = false; };
  }, [active, offset, owner, requestOwner, auth, useStubAuth, bearerToken, canLoadSecureApi, kind]);

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
      validatedPage(result, kind, active, 0, true);
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
      if (ownerRef.current === owner && guard.current === token) setExportError(error instanceof Error ? error.message : "Không thể xuất báo cáo.");
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
            <td><Link className="text-link" to={["GMP", "GLP", "GMPbb"].includes(item.gxp_type) ? certificateLocation(item) : `/reports/certificates/${encodeURIComponent(item.certificate_id)}?${new URLSearchParams({ site_id: item.site_id })}`}>{item.certificate_number ?? item.certificate_id}</Link></td>
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
