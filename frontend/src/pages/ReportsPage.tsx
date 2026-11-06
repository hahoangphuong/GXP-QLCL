import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import "./reports.css";

import type { ApiAccess } from "../App";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { collectFacilityReport, facilityReportCsv, REPORT_PAGE_SIZE } from "../features/reports/facilityReportExport";
import { CaseReport } from "../features/reports/CaseReport";
import { CanonicalRecordReport } from "../features/reports/CanonicalRecordReport";
import { searchFacilities } from "../lib/api";
import type { FacilitySearchPage, FacilitySearchResult } from "../types";

type Filters = { gxp_type: "GMP" | "GLP" | "GMPbb"; q: string; province: string };
type PageState = { owner: object; key: string; data: FacilitySearchPage | null; error: string | null };
const INITIAL_FILTERS: Filters = { gxp_type: "GMP", q: "", province: "" };

// Refuse a malformed read page before exposing links based on potentially
// wrong Site/result_key projections. CSV export validates its own full walk.
function validatedFacilityReportPage(page: FacilitySearchPage, requestedOffset: number): FacilitySearchPage {
  if (!Array.isArray(page.items) || !Number.isSafeInteger(page.total_count) || page.total_count < 0
    || !Number.isSafeInteger(page.offset) || page.offset !== requestedOffset
    || !Number.isSafeInteger(page.limit) || page.limit !== REPORT_PAGE_SIZE
    || page.offset > page.total_count
    || page.items.length > REPORT_PAGE_SIZE
    || page.items.length !== Math.min(REPORT_PAGE_SIZE, page.total_count - page.offset)) {
    throw new Error("API trả về phân trang cơ sở không hợp lệ.");
  }
  const seen = new Set<string>();
  for (const item of page.items) {
    if (!item || typeof item.result_key !== "string" || !item.result_key.trim()
      || typeof item.site_id !== "string" || !item.site_id.trim()
      || seen.has(item.result_key)) {
      throw new Error("Trang cơ sở có định danh kết quả trùng, thiếu hoặc không có Site canonical.");
    }
    seen.add(item.result_key);
  }
  return page;
}

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

type ReportKind = "facilities" | "cases" | "inspection" | "certificates" | "change_requests";
const REPORT_KINDS = new Set<ReportKind>(["facilities", "cases", "inspection", "certificates", "change_requests"]);

function selectedReport(value: string | null): ReportKind {
  return value && REPORT_KINDS.has(value as ReportKind) ? value as ReportKind : "facilities";
}

export function ReportsPage({ access, statusError }: { access: ApiAccess; statusError: string | null }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const report = selectedReport(searchParams.get("report"));
  const initialCaseState = report === "cases" && searchParams.get("case_state") === "awaiting_certificate_decision"
    ? "awaiting_certificate_decision" : "";
  function selectReport(next: ReportKind) {
    setSearchParams(params => {
      const updated = new URLSearchParams(params);
      for (const key of ["gxp_type", "expiry_days", "number", "q", "state", "offset"]) updated.delete(key);
      updated.set("report", next);
      // A report-kind change starts a fresh filter context, not a stale Case queue.
      updated.delete("case_state");
      return updated;
    });
  }
  if (statusError) return <ErrorState message={statusError} />;
  return <>
    <section className="panel"><label>Loại báo cáo <select value={report} onChange={event => selectReport(event.target.value as ReportKind)}>
      <option value="facilities">Danh sách cơ sở</option>
      <option value="cases">Hồ sơ đang xử lý</option>
      <option value="inspection">Hồ sơ chuẩn bị và đang kiểm tra</option>
      <option value="certificates">GCN GxP hiện hành / sắp hết hạn</option>
      <option value="change_requests">Yêu cầu thay đổi chưa hoàn tất</option>
    </select></label></section>
    {report === "facilities" ? <FacilityReport access={access} statusError={null} /> :
      (report === "certificates" || report === "change_requests") ?
        <section className="page-section"><h2>{report === "certificates" ? "GCN GxP hiện hành" : "Yêu cầu thay đổi chưa hoàn tất"}</h2>
          <CanonicalRecordReport key={report} access={access} kind={report} urlState showDocumentsLink={report === "change_requests"} /></section> :
      <section className="page-section"><h2>{report === "inspection" ? "Hồ sơ chuẩn bị và đang kiểm tra" : "Hồ sơ đang xử lý"}</h2><CaseReport key={report + ":" + initialCaseState} access={access}
        inspectionQueue={report === "inspection"} showDocumentsLink initialState={initialCaseState} /></section>}
  </>;
}

function FacilityReport({
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
  const [draft, setDraft] = useState<Filters>(INITIAL_FILTERS);
  const [active, setActive] = useState<Filters>(INITIAL_FILTERS);
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
    void searchFacilities({ ...active, offset, limit: REPORT_PAGE_SIZE }, auth, useStubAuth, bearerToken)
      .then(data => {
        if (cancelled) return;
        try {
          setPage({ owner, key, data: validatedFacilityReportPage(data, offset), error: null });
        } catch (error) {
          setPage({ owner, key, data: null, error: error instanceof Error ? error.message : "Trang báo cáo cơ sở không hợp lệ." });
        }
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
          searchFacilities({ ...filters, offset: pageOffset, limit }, auth, useStubAuth, bearerToken),
        () => ownerRef.current === requestedOwner && exportGuard.current === token,
      );
      if (ownerRef.current !== requestedOwner) return;
      const blob = new Blob([facilityReportCsv(rows)], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = "danh-sach-co-so-" + filters.gxp_type + ".csv";
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
          <h2>Danh sách cơ sở theo GxP</h2>
        </div>
        <p className="section-copy">
          Dữ liệu trực tiếp từ Tra cứu; một cơ sở có thể có nhiều dòng theo dây chuyền sản xuất.
          Đây là danh sách tra cứu, không phải danh sách cơ sở được công bố hoặc giấy chứng nhận đã cấp.
        </p>
      </header>

      <section className="panel">
        <form onSubmit={applyFilters}>
          <div className="report-filter-grid">
            <label>Loại GxP
              <select value={draft.gxp_type} disabled={exporting} onChange={event => setDraft({ ...draft, gxp_type: event.target.value as Filters["gxp_type"] })}>
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
          <h3>Kết quả {active.gxp_type}</h3>
          {!loading && !current?.error && <span aria-live="polite">{total} dòng kết quả</span>}
        </div>
        {loading ? <p role="status">Đang tải dữ liệu...</p>
          : current.error ? <p role="alert">{current.error}</p>
          : rows.length === 0 ? <p>Không có cơ sở phù hợp.</p>
          : (
            <div className="table-scroll">
              <table className="dense-table">
                <thead><tr>
                  <th>Cơ sở</th><th>Công ty</th><th>GxP</th><th>Tỉnh/thành</th><th>Dây chuyền</th><th>GCN hiện hành</th><th>Hạn GCN</th>
                </tr></thead>
                <tbody>
                  {rows.map(row => (
                    <tr key={row.result_key}>
                      <td><Link className="text-link" to={searchLink(row)}>{row.facility_name}</Link></td>
                      <td>{row.company_name}</td>
                      <td>{row.gxp_type ?? row.gxp_types.join(", ")}</td>
                      <td>{row.province_name ?? "—"}</td>
                      <td>{row.production_line_code ?? row.line_code ?? "—"}</td>
                      <td>{row.current_certificate_number ?? "—"}</td>
                      <td>{row.current_certificate_expiry ?? "—"}</td>
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
