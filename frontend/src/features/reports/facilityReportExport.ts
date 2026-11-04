import type { FacilitySearchPage, FacilitySearchResult } from "../../types";

export const REPORT_PAGE_SIZE = 100;
export const REPORT_MAX_ROWS = 10000;

// A bounded export must never silently turn one incomplete page into a full report.
export async function collectFacilityReport(
  fetchPage: (offset: number, limit: number) => Promise<FacilitySearchPage>,
  isCurrent: () => boolean = () => true,
): Promise<FacilitySearchResult[]> {
  const results: FacilitySearchResult[] = [];
  const seen = new Set<string>();
  let expectedTotal: number | null = null;
  while (true) {
    if (!isCurrent()) throw new Error("Phiên truy cập đã thay đổi; báo cáo bị hủy.");
    const page = await fetchPage(results.length, REPORT_PAGE_SIZE);
    if (!isCurrent()) throw new Error("Phiên truy cập đã thay đổi; báo cáo bị hủy.");
    if (!Number.isSafeInteger(page.total_count) || page.total_count < 0
      || !Number.isSafeInteger(page.offset) || page.offset !== results.length
      || page.items.length > REPORT_PAGE_SIZE) {
      throw new Error("API trả về phân trang báo cáo không hợp lệ.");
    }
    if (expectedTotal === null) {
      expectedTotal = page.total_count;
      if (expectedTotal > REPORT_MAX_ROWS) {
        throw new Error("Danh sách quá lớn để xuất trực tiếp; hãy thu hẹp bộ lọc.");
      }
    }
    if (page.total_count !== expectedTotal || results.length + page.items.length > expectedTotal) {
      throw new Error("Danh sách đã thay đổi trong lúc xuất; hãy thử lại để tránh thiếu dữ liệu.");
    }
    for (const item of page.items) {
      if (!item.result_key || seen.has(item.result_key)) {
        throw new Error("Phân trang có kết quả trùng hoặc thiếu định danh; không thể xuất đầy đủ.");
      }
      seen.add(item.result_key);
      results.push(item);
    }
    if (results.length === expectedTotal) return results;
    if (page.items.length === 0) {
      throw new Error("API trả về trang rỗng khi danh sách còn bản ghi.");
    }
  }
}

export const REPORT_COLUMNS: { label: string; value: (row: FacilitySearchResult) => string }[] = [
  { label: "ID cơ sở (legacy)", value: row => row.legacy_site_id?.toString() ?? "" },
  { label: "Mã cơ sở", value: row => row.facility_code ?? "" },
  { label: "Cơ sở", value: row => row.facility_name },
  { label: "Công ty", value: row => row.company_name },
  { label: "GxP", value: row => row.gxp_type ?? row.gxp_types.join(", ") },
  { label: "Tỉnh/thành", value: row => row.province_name ?? "" },
  { label: "Dây chuyền", value: row => row.production_line_code ?? row.line_code ?? "" },
  { label: "Phạm vi GCN", value: row => row.certificate_scope_summary ?? "" },
  { label: "Ngày kiểm tra gần nhất", value: row => row.last_inspection_on ?? "" },
  { label: "Trạng thái hồ sơ", value: row => row.current_state ?? "" },
  { label: "Số GCN hiện hành", value: row => row.current_certificate_number ?? "" },
  { label: "Hạn GCN", value: row => row.current_certificate_expiry ?? "" },
];

// Prevent spreadsheet formula execution for text returned by an external catalogue.
// Quoting CSV alone does not neutralize formula injection in spreadsheet programs.
function csvCell(value: string): string {
  let first = 0;
  while (first < value.length && value.charCodeAt(first) <= 32) first += 1;
  const safe = first < value.length && "=+-@".includes(value[first])
    ? "'" + value : value;
  return '"' + safe.replace(/"/g, '""') + '"';
}

export function facilityReportCsv(rows: FacilitySearchResult[]): string {
  const lines = [
    REPORT_COLUMNS.map(column => csvCell(column.label)).join(","),
    ...rows.map(row => REPORT_COLUMNS.map(column => csvCell(column.value(row))).join(",")),
  ];
  return "\uFEFF" + lines.join("\r\n") + "\r\n";
}
