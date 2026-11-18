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
  certificate_data_incomplete: "Chứng nhận còn thiếu thông tin bắt buộc để đưa vào trạng thái hiện hành.",
  already_current: "Chứng nhận này đã là bản hiện hành.",
  candidate_issue_date_precedes_current: "Ngày cấp của chứng nhận dự kiến không được sớm hơn chứng nhận hiện hành.",
  site_company_owner_mismatch: "Dữ liệu Công ty hoặc Cơ sở đã thay đổi. Tải lại Cơ sở để kiểm tra dữ liệu canonical trước khi thao tác.",
  structured_read_unavailable: "Dữ liệu đoàn kiểm tra chưa ở dạng cấu trúc để chỉnh sửa an toàn.",
  source_owned_period_state: "Dữ liệu các đợt kiểm tra đang do nguồn legacy quản lý; chưa thể chỉnh sửa an toàn.",
  legacy_period_state_unclassified: "Chưa phân loại được trạng thái legacy của các đợt kiểm tra; chưa thể chỉnh sửa an toàn.",
  final_evaluation_missing: "Cần ghi nhận đánh giá cuối cùng trước khi thực hiện thao tác này.",
  nonissuance_already_recorded: "Hồ sơ đã có quyết định không cấp được ghi nhận.",
  linked_certificate_exists: "Hồ sơ đã liên kết với giấy chứng nhận; không thể ghi nhận quyết định không cấp.",
  no_eligible_documents: "Chưa có tài liệu phù hợp để liên kết.",
  readiness_unavailable: "Backend chưa cung cấp trạng thái sẵn sàng cho thao tác này.",
};

export function caseReadinessReason(code: string): string {
  const message = Object.prototype.hasOwnProperty.call(REASONS, code)
    ? REASONS[code]
    : "Backend chưa có diễn giải cho điều kiện này.";
  return `${message} (${code})`;
}
