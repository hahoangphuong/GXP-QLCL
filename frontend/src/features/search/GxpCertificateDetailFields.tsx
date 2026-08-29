import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate } from "../../lib/presentation";
import type { GxpCertificateDetail } from "../../types";
import { DetailValue } from "./DetailValue";

export function GxpCertificateDetailFields({ detail }: { detail: GxpCertificateDetail }) {
  return (
    <div className="detail-grid compact-grid certificate-detail-grid">
      <DetailValue label="Số GCN" value={detail.certificate_number} />
      <DetailValue label="Ngày cấp" value={formatCompactDate(detail.issue_date)} />
      <DetailValue label="Hết hạn" value={formatCompactDate(detail.expiry_date)} />
      <DetailValue label="Tiêu chuẩn" value={detail.applicable_standard} />
      <DetailValue label="Tên cơ sở" value={detail.facility_name} />
      <DetailValue label="Địa chỉ cơ sở" multiline value={detail.address} />
      <DetailValue label="Tên công ty" value={detail.company_name} />
      <DetailValue label="Trụ sở" multiline value={detail.company_legal_address} />
      <DetailValue label="Phạm vi chứng nhận" multiline value={detail.scope_summary} />
      <DetailValue label="Giới hạn" multiline value={detail.limitation_text} />
      <DetailValue label="Cơ quan cấp" value={detail.issuing_authority} />
      <div>
        <span>Tình trạng</span>
        <strong>{detail.status ? <StatusBadge value={detail.status} /> : "Chưa có"}</strong>
      </div>
      <DetailValue label="Nguồn gốc" multiline value={detail.source_description} />
    </div>
  );
}
