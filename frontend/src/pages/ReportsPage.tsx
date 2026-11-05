import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import "./reports.css";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { collectFacilityReport, facilityReportCsv, REPORT_PAGE_SIZE } from "../features/reports/facilityReportExport";
import { buildOperationalReportQuery, INITIAL_REPORT_FILTERS, REPORT_DESCRIPTIONS, reportExportFilename, type ReportFilters } from "../features/reports/reportCatalog";
import { searchFacilities } from "../lib/api";
import type { FacilitySearchPage, FacilitySearchResult } from "../types";

type PageState = { owner: object; key: string; data: FacilitySearchPage | null; error: string | null };

function searchLink(row: FacilitySearchResult) {
  const params = new URLSearchParams({
    site_id: row.site_id,
    result_key: row.result_key,
    gxp_type: row.gxp_type ?? "GMP",
  });
  if (row.production_line_id) params.set("production_line_id", row.production_line_id);
  if (row.line_code) params.set("line_code", row.line_code);
  return "/search?" + params.toString();
}

export function ReportsPage({
  access,
  statusError,
}: {
  access: ApiAccess;
  statusError: string | null;
}) {
  const { auth, bearerToken, canLoadSecureApi, useStubAuth, accessGeneration } = access;
  const owner = useMemo(() => ({}), [auth, bearerToken, canLoadSecureApi, useStubAuth, accessGeneration]);
  const ownerRef = useRef(owner);
  ownerRef.current = owner;
  const [draft, setDraft] = useState<ReportFilters>(INITIAL_REPORT_FILTERS);
  const [active, setActive] = useState<ReportFilters>(INITIAL_REPORT_FILTERS);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<PageState | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const exportGuard = useRef<object | null>(null);
  useEffect(() => {
    // A new authenticated owner must not inherit an unfinished download lock.
    exportGuard.current = null;
    setExporting(false);
    setExportError(null);
  }, [owner]);
  const key = JSON.stringify([active, offset]);
  const current = page?.owner === owner && page.key === key ? page : null;

  useEffect(() => {
    if (!canLoadSecureApi) return;
    let cancelled = false;
    void searchFacilities({ ...buildOperationalReportQuery(active), offset, limit: REPORT_PAGE_SIZE }, auth, useStubAuth, bearerToken)
      .then(data => {
        if (!cancelled) setPage({ owner, key, data, error: null });
      })
      .catch((error: Error) => {
        if (!cancelled) setPage({ owner, key, data: null, error: error.message });
      });
    return () => { cancelled = true; };
  }, [active, offset, auth, bearerToken, canLoadSecureApi, useStubAuth, owner, key]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (exportGuard.current) return;
    setActive({ ...draft, q: draft.q.trim(), province: draft.province.trim() });
    setOffset(0);
    setExportError(null);
  }

  async function exportReport() {
    if (exportGuard.current || !canLoadSecureApi) return;
    const token = {};
    exportGuard.current = token;
    setExporting(true);
    setExportError(null);
    const requestedOwner = owner;
    const filters = { ...active };
    try {
      const rows = await collectFacilityReport(
        (pageOffset, limit) =>
          searchFacilities({ ...buildOperationalReportQuery(filters), offset: pageOffset, limit }, auth, useStubAuth, bearerToken),
        () => ownerRef.current === requestedOwner && exportGuard.current === token,
      );
      if (ownerRef.current !== requestedOwner) return;
      const blob = new Blob([facilityReportCsv(rows, { omitCertificateProjection: filters.kind === "expiring_certificates" })], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = reportExportFilename(filters);
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      if (ownerRef.current === requestedOwner) {
        setExportError(error instanceof Error ? error.message : "Không thể xuất báo cáo.");
      }
    } finally {
      if (exportGuard.current === token) {
        exportGuard.current = null;
        if (ownerRef.current === requestedOwner) setExporting(false);
      }
    }
  }

  if (statusError) return <ErrorState message={statusError} />;
  if (!canLoadSecureApi) {
    return <EmptyState title="Cần đăng nhập" description="Đăng nhập để xem và xuất danh sách cơ sở được phân quyền." />;
  }

  const loading = current === null;
  const rows = current?.data?.items ?? [];
  const total = current?.data?.total_count ?? 0;

  return (
    <section className="page-section">
      <header className="section-title">
        <div>
          <p className="eyebrow">Báo cáo</p>
          <h2>Báo cáo nghiệp vụ GxP</h2>
        </div>
        <p className="section-copy">
          Các báo cáo sử dụng bộ lọc của API Tra cứu. Mỗi dòng là một ngữ cảnh cơ sở hoặc dây chuyền,
          không phải một Case, Change Request hay GCN duy nhất; không phải danh sách công bố chính thức.
        </p>
      </header>

      <section className="panel">
        <form onSubmit={applyFilters}>
          <div className="report-filter-grid">
            <label>Loại báo cáo
              <select value={draft.kind} disabled={exporting} onChange={event => setDraft({ ...draft, kind: event.target.value as ReportFilters["kind"] })}>
                {Object.entries(REPORT_DESCRIPTIONS).map(([kind, detail]) => <option key={kind} value={kind}>{detail.title}</option>)}
              </select>
            </label>
            <label>Loại GxP
              <select value={draft.gxp_type} disabled={exporting} onChange={event => setDraft({ ...draft, gxp_type: event.target.value as ReportFilters["gxp_type"] })}>
                <option value="GMP">GMP</option>
                <option value="GLP">GLP</option>
                <option value="GMPbb">GMPbb</option>
              </select>
            </label>
            <label>Từ khóa
              <input value={draft.q} disabled={exporting} onChange={event => setDraft({ ...draft, q: event.target.value })} placeholder="Tên hoặc mã cơ sở" />
            </label>
            <label>Tỉnh/thành
              <input value={draft.province} disabled={exporting} onChange={event => setDraft({ ...draft, province: event.target.value })} placeholder="Nhập tên tỉnh/thành" />
            </label>
            {draft.kind === "inspection" && <label>Giai đoạn kiểm tra
              <select value={draft.inspection_state} disabled={exporting} onChange={event => setDraft({ ...draft, inspection_state: event.target.value as ReportFilters["inspection_state"] })}>
                <option value="all">Tất cả các giai đoạn</option>
                <option value="planned">Đã lập kế hoạch</option>
                <option value="decision_issued">Đã có quyết định kiểm tra</option>
                <option value="inspection_in_progress">Đang kiểm tra</option>
              </select>
            </label>}
            {draft.kind === "expiring_certificates" && <label>Hết hạn trong
              <select value={draft.expiry_days} disabled={exporting} onChange={event => setDraft({ ...draft, expiry_days: Number(event.target.value) as ReportFilters["expiry_days"] })}>
                <option value={30}>30 ngày</option><option value={60}>60 ngày</option><option value={90}>90 ngày</option>
              </select>
            </label>}
          </div>
          <div className="report-actions">
            <button type="submit" disabled={exporting}>Áp dụng bộ lọc</button>
            <button type="button" className="secondary" onClick={() => void exportReport()} disabled={exporting || loading || Boolean(current?.error)}>
              {exporting ? "Đang xuất toàn bộ..." : "Xuất CSV (Excel)"}
            </button>
          </div>
        </form>
        {exportError && <p role="alert" className="auth-error">{exportError}</p>}
        <p className="muted-copy">
          CSV UTF-8 dùng được với Excel. Xuất toàn bộ các trang theo bộ lọc đang áp dụng,
          tối đa 10.000 dòng; nếu dữ liệu thay đổi trong lúc tải, hệ thống từ chối xuất thay vì tạo báo cáo thiếu.
        </p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div><h3>{REPORT_DESCRIPTIONS[active.kind].title} — {active.gxp_type}</h3>
            <p className="muted-copy">{REPORT_DESCRIPTIONS[active.kind].detail}</p></div>
          {!loading && !current?.error && <span aria-live="polite">{total} dòng kết quả</span>}
        </div>
        {loading ? <p role="status">Đang tải dữ liệu...</p>
          : current.error ? <p role="alert">{current.error}</p>
          : rows.length === 0 ? <p>Không có cơ sở phù hợp.</p>
          : (
            <div className="table-scroll">
              <table className="dense-table">
                <thead><tr>
                  <th>Cơ sở</th><th>Công ty</th><th>GxP</th><th>Tỉnh/thành</th><th>Dây chuyền</th>
                  {active.kind !== "expiring_certificates" && <><th>GCN hiện hành (ngữ cảnh)</th><th>Hạn GCN (ngữ cảnh)</th></>}
                </tr></thead>
                <tbody>
                  {rows.map(row => (
                    <tr key={row.result_key}>
                      <td><Link className="text-link" to={searchLink(row)}>{row.facility_name}</Link></td>
                      <td>{row.company_name}</td>
                      <td>{row.gxp_type ?? row.gxp_types.join(", ")}</td>
                      <td>{row.province_name ?? "—"}</td>
                      <td>{row.production_line_code ?? row.line_code ?? "—"}</td>
                      {active.kind !== "expiring_certificates" && <><td>{row.current_certificate_number ?? "—"}</td>
                      <td>{row.current_certificate_expiry ?? "—"}</td></>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {!loading && !current?.error && total > 0 &&
          <nav className="report-pagination" aria-label="Phân trang báo cáo">
            <button className="secondary" type="button" disabled={offset === 0 || exporting} onClick={() => setOffset(Math.max(0, offset - REPORT_PAGE_SIZE))}>Trang trước</button>
            <span>Trang {Math.floor(offset / REPORT_PAGE_SIZE) + 1} / {Math.ceil(total / REPORT_PAGE_SIZE)}</span>
            <button className="secondary" type="button" disabled={offset + rows.length >= total || exporting} onClick={() => setOffset(offset + REPORT_PAGE_SIZE)}>Trang sau</button>
          </nav>
        }
      </section>
    </section>
  );
}
