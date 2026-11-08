// Text explains backend-provided reason codes; it does not decide readiness.
const REASONS: Record<string, string> = {
  missing_permission: "Tài khoản không có quyền thực hiện thao tác này.",
  latest_capa_not_accepted: "Vòng khắc phục gần nhất chưa được chấp nhận.",
  case_state_not_eligible: "Trạng thái hồ sơ chưa cho phép cấp chứng nhận.",
  gmp_case_already_issued: "Hồ sơ GMP đã có chứng nhận được cấp; không thể cấp thêm từ hồ sơ này.",
  completed_pct_required: "Cần hoàn tất một lần trình PCT trước khi tạo trình CT.",
  terminal_case: "Hồ sơ đã kết thúc; thao tác không còn khả dụng.",
  already_completed: "Lần trình này đã hoàn tất.",
};

export function caseReadinessReason(code: string): string {
  return Object.prototype.hasOwnProperty.call(REASONS, code) ? `${REASONS[code]} (${code})` : code;
}
