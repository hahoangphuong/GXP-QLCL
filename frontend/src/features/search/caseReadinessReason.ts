// Text explains backend-provided reason codes; it does not decide readiness.
const REASONS: Record<string, string> = {
  missing_permission: "Tài khoản không có quyền thực hiện thao tác này.",
  latest_capa_not_accepted: "Vòng khắc phục gần nhất chưa được chấp nhận.",
  case_state_not_eligible: "Trạng thái hồ sơ chưa cho phép cấp chứng nhận.",
  gmp_case_already_issued: "Hồ sơ GMP đã có chứng nhận được cấp; không thể cấp thêm từ hồ sơ này.",
  completed_pct_required: "Cần hoàn tất một lần trình PCT trước khi tạo trình CT.",
  terminal_case: "Hồ sơ đã kết thúc; thao tác không còn khả dụng.",
  already_completed: "Lần trình này đã hoàn tất.",
  outcome_missing: "Cần ghi nhận kết quả kiểm tra trước khi chốt đánh giá cuối.",
  already_finalized: "Đánh giá cuối đã được chốt.",
  invalid_case_state: "Trạng thái hồ sơ hiện tại chưa cho phép thao tác này.",
  latest_cycle_not_rejected: "Chỉ mở thêm vòng khắc phục khi vòng gần nhất bị từ chối.",
  historical_cycle: "Đây là vòng khắc phục lịch sử; chỉ vòng hiện tại được xử lý.",
  invalid_cycle_state: "Trạng thái vòng khắc phục chưa cho phép thao tác này.",
};

export function caseReadinessReason(code: string): string {
  return Object.prototype.hasOwnProperty.call(REASONS, code) ? `${REASONS[code]} (${code})` : code;
}
