// These are facility-search predicates already used by the Dashboard links.
// One result is a facility/production-line context, NOT a unique Case/GCN/Change Request.
export const REPORT_KINDS = [
  "facilities", "active_cases", "inspection", "certificate_decision", "expiring_certificates", "open_changes",
] as const;
export type ReportKind = typeof REPORT_KINDS[number];
export type ReportFilters = {
  gxp_type: "GMP" | "GLP" | "GMPbb";
  q: string;
  province: string;
  kind: ReportKind;
  expiry_days: 30 | 60 | 90;
};
export const INITIAL_REPORT_FILTERS: ReportFilters = {
  gxp_type: "GMP", q: "", province: "", kind: "facilities", expiry_days: 90,
};

const ACTIVE_CASE_STATES = [
  "draft", "application_received", "under_assessment", "planned",
  "decision_issued", "inspection_in_progress", "inspection_completed",
  "awaiting_certificate_decision",
] as const;
const INSPECTION_STATES = ["planned", "decision_issued", "inspection_in_progress"] as const;
const OPEN_CHANGE_STATES = ["received", "under_review"] as const;

export const REPORT_DESCRIPTIONS: Record<ReportKind, { title: string; detail: string }> = {
  facilities: {
    title: "Danh sách cơ sở theo GxP",
    detail: "Danh sách cơ sở/dây chuyền theo kết quả tra cứu có phân quyền.",
  },
  active_cases: {
    title: "Cơ sở có hồ sơ đang xử lý",
    detail: "Cơ sở có ít nhất một Case ở trạng thái chưa kết thúc. Không phải danh sách từng Case.",
  },
  inspection: {
    title: "Cơ sở có hồ sơ đang ở giai đoạn kiểm tra",
    detail: "Hồ sơ có trạng thái planned, decision_issued hoặc inspection_in_progress. Không suy ra lịch kiểm tra hay số QĐKT.",
  },
  certificate_decision: {
    title: "Cơ sở có hồ sơ chờ quyết định chứng nhận",
    detail: "Cơ sở có ít nhất một Case đang awaiting_certificate_decision; chưa đồng nghĩa đủ điều kiện cấp GCN.",
  },
  expiring_certificates: {
    title: "Cơ sở có GCN hiện hành sắp hết hạn",
    detail: "Lọc ngữ cảnh có ít nhất một GCN hiện hành sắp hết hạn. API không định danh GCN khớp nên phải mở cơ sở để xem số GCN và ngày hết hạn cụ thể.",
  },
  open_changes: {
    title: "Cơ sở có yêu cầu thay đổi chưa hoàn tất",
    detail: "Change Request lọc ở cấp Site (không phân loại GxP). GxP là ngữ cảnh hiển thị; đây không phải danh sách từng yêu cầu.",
  },
};

export function buildOperationalReportQuery(filters: ReportFilters) {
  const common = {
    gxp_type: filters.gxp_type,
    q: filters.q.trim(),
    province: filters.province.trim(),
  };
  switch (filters.kind) {
    case "active_cases":
      return { ...common, case_state: [...ACTIVE_CASE_STATES] };
    case "inspection":
      return { ...common, case_state: [...INSPECTION_STATES] };
    case "certificate_decision":
      return { ...common, case_state: ["awaiting_certificate_decision"] };
    case "expiring_certificates":
      return { ...common, certificate_state: "active", certificate_expiring_within_days: filters.expiry_days };
    case "open_changes":
      return { ...common, change_request_state: [...OPEN_CHANGE_STATES] };
    default:
      return common;
  }
}

export function reportExportFilename(filters: ReportFilters): string {
  return `bao-cao-${filters.kind}-${filters.gxp_type}${filters.kind === "expiring_certificates" ? `-${filters.expiry_days}ngay` : ""}.csv`;
}
