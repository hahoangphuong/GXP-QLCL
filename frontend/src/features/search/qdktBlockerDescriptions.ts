/** Operator-facing explanations for backend-owned QĐKT readiness blockers.
 * Unknown codes stay visible; this mapping never authorizes rendering.
 */
const DESCRIPTIONS: Record<string, { title: string; next: string }> = {
  CASE_NOT_FOUND: { title: "Không tìm thấy hồ sơ kiểm tra.", next: "Chọn lại đúng hồ sơ Case." },
  CASE_REGISTERED_SITE_NOT_FOUND: { title: "Chưa xác minh cơ sở đăng ký của hồ sơ.", next: "Kiểm tra liên kết giữa Case và cơ sở." },
  CASE_INSPECTION_PLAN_NOT_UNIQUE: { title: "Nguồn kế hoạch kiểm tra không duy nhất.", next: "Đối chiếu dữ liệu kế hoạch, không tự chọn bản gần nhất." },
  SOURCE_DECISION_CARDINALITY_UNPROVEN: { title: "Không xác định duy nhất được quyết định nguồn.", next: "Kiểm tra lịch sử các quyết định và quan hệ thay thế." },
  REGISTERED_SITE_ADDRESS_MISSING: { title: "Thiếu địa chỉ đăng ký cơ sở.", next: "Kiểm tra hồ sơ cơ sở, không tự lấy địa chỉ khác." },
  REGISTERED_PROVINCE_MISSING: { title: "Thiếu tỉnh/thành của cơ sở.", next: "Kiểm tra nguồn địa danh đăng ký." },
  LEGACY_PROVINCE_MAPPING_UNPROVEN: { title: "Chưa đối chiếu được tỉnh/thành với danh mục địa danh legacy.", next: "Cần xác minh ánh xạ địa danh trước khi tạo mẫu." },
  MANUFACTURING_CLASSIFICATION_SOURCE_UNPROVEN: { title: "Chưa xác định được nguồn phân loại sản xuất để chọn cơ quan.", next: "Cần xác nhận nguồn nghiệp vụ, không suy từ loại GxP." },
  LOCATION_BOOKMARK_FORMAT_UNPROVEN: { title: "Chưa xác minh quy tắc điền địa điểm của mẫu Word.", next: "Cần đối chiếu bookmark với VBA và mẫu gốc." },
  BLANK_ISSUANCE_DATE_BOOKMARK_UNVERIFIED: { title: "Chưa xác minh cách để trống ngày ban hành trên bản dự thảo.", next: "Cần làm rõ quy tắc ngày trước khi render." },
  INSPECTION_TEAM_BOOKMARK_CONTRACT_UNRESOLVED: { title: "Chưa xác minh đầy đủ bookmark đoàn kiểm tra.", next: "Cần đối chiếu thứ tự, vai trò và chuỗi hiển thị trong mẫu gốc." },
  QDKT_TYPED_RENDER_CONTRACT_MISSING: { title: "Chưa có hợp đồng tạo DOCX QĐKT theo Case được phê duyệt.", next: "Chức năng tạo vẫn khóa đến khi hoàn tất Issue #74." },
};

export function describeQdKtBlocker(reason: string): { code: string; title: string; next: string } {
  const known = Object.prototype.hasOwnProperty.call(DESCRIPTIONS, reason)
    ? DESCRIPTIONS[reason] : undefined;
  return {
    code: reason,
    title: known?.title ?? "Điều kiện QĐKT chưa được xác minh.",
    next: known?.next ?? "Chuyển mã lỗi này cho nhóm phụ trách nghiệp vụ/backend để xác định nguồn.",
  };
}
