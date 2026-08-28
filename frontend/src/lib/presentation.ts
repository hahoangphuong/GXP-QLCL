const CASE_STATE_LABELS: Record<string, string> = {
  draft: "Nháp",
  application_received: "Đã tiếp nhận hồ sơ",
  under_assessment: "Đang thẩm định",
  planned: "Đã lập kế hoạch",
  decision_issued: "Đã ban hành quyết định",
  inspection_in_progress: "Đang kiểm tra",
  inspection_completed: "Đã hoàn tất kiểm tra",
  awaiting_certificate_decision: "Chờ cấp chứng nhận",
  certified: "Đã cấp chứng nhận",
  closed: "Đã đóng hồ sơ",
  cancelled: "Đã hủy",
};

const CHANGE_REQUEST_STATE_LABELS: Record<string, string> = {
  received: "Đã tiếp nhận",
  under_review: "Đang xem xét",
  accepted: "Đã chấp thuận",
  rejected: "Đã từ chối",
  effective: "Đã có hiệu lực",
  superseded: "Đã được thay thế",
};

const STATUS_TONES: Record<string, string> = {
  draft: "info",
  application_received: "warning",
  under_assessment: "warning",
  planned: "warning",
  decision_issued: "warning",
  inspection_in_progress: "warning",
  inspection_completed: "info",
  awaiting_certificate_decision: "warning",
  certified: "success",
  closed: "muted",
  cancelled: "danger",
  received: "warning",
  under_review: "warning",
  accepted: "success",
  rejected: "danger",
  effective: "success",
  superseded: "muted",
  active: "success",
};

const FACILITY_NAME_ABBREVIATIONS: Array<[RegExp, string]> = [
  [/\bCông ty\b/g, "Cty"],
  [/\bcổ phần\b/gi, "CP"],
];

export const CASE_STATE_OPTIONS = [
  "application_received",
  "under_assessment",
  "planned",
  "decision_issued",
  "inspection_in_progress",
  "inspection_completed",
  "awaiting_certificate_decision",
  "certified",
] as const;

export function formatStatusLabel(value: string | null | undefined): string {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return "Chưa có";
  }
  return CASE_STATE_LABELS[normalized] ?? CHANGE_REQUEST_STATE_LABELS[normalized] ?? normalized;
}

export function getStatusTone(value: string | null | undefined): string {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return "muted";
  }
  return STATUS_TONES[normalized] ?? "info";
}

export function formatFacilityNameForGrid(value: string): string {
  return FACILITY_NAME_ABBREVIATIONS.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), value);
}

export function formatHistoryEventType(value: string | null | undefined): string {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return "Chưa có";
  }
  if (normalized === "Thay đổi cơ sở") {
    return "Thay đổi";
  }
  return normalized;
}
