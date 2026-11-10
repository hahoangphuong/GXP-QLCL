import type {
  BusinessEligibilityDetail, BusinessEligibilityListItem,
  GxpCertificateDetail, GxpCertificateListItem,
} from "../../types";

// A successful write response is not enough to call a Certificate verified.
// Both independently reloaded canonical sources must agree on the selected
// identity before the editor or master search is allowed to advance.
export function assertGxpCertificateMutationReadback(
  certificateId: string,
  siteId: string,
  gxpType: string | null,
  detail: GxpCertificateDetail,
  rows: GxpCertificateListItem[],
  requireCurrent = false,
): void {
  const listed = rows.find(row => row.certificate_id === certificateId);
  if (!listed || detail.certificate_id !== certificateId
    || detail.site_id !== siteId || listed.site_id !== siteId
    || (gxpType && (detail.certificate_type !== gxpType || listed.certificate_type !== gxpType))
    || detail.certificate_type !== listed.certificate_type
    || detail.case_id !== listed.case_id
    || detail.production_line_id !== listed.production_line_id
    || detail.production_line_identity_state !== listed.production_line_identity_state) {
    throw new Error("Đọc lại GCN GxP không khớp Certificate UUID, cơ sở, loại GxP hoặc dây chuyền canonical.");
  }
  if (requireCurrent && (!detail.latest_flag || !listed.latest_flag)) {
    throw new Error("Backend chưa xác nhận chứng nhận GxP đang chọn là chứng nhận hiện hành.");
  }
}

export function assertEligibilityCertificateMutationReadback(
  certificateId: string,
  siteId: string,
  detail: BusinessEligibilityDetail,
  rows: BusinessEligibilityListItem[],
  requireCurrent = false,
): void {
  const listed = rows.find(row => row.business_eligibility_certificate_id === certificateId);
  if (!listed || detail.business_eligibility_certificate_id !== certificateId
    || detail.site_id !== siteId || listed.site_id !== siteId
    || detail.company_id !== listed.company_id) {
    throw new Error("Đọc lại GCN đủ điều kiện không khớp Certificate UUID, cơ sở hoặc doanh nghiệp canonical.");
  }
  if (requireCurrent && (!detail.latest_flag || !listed.latest_flag)) {
    throw new Error("Backend chưa xác nhận GCN đủ điều kiện đang chọn là chứng nhận hiện hành.");
  }
}
