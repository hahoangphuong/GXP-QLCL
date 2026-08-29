import { formatCompactDate } from "../../lib/presentation";
import type { BusinessEligibilityDetail } from "../../types";
import { DetailValue } from "./DetailValue";

export function BusinessEligibilityDetailFields({ detail }: { detail: BusinessEligibilityDetail }) {
  return (
    <div className="detail-grid compact-grid certificate-detail-grid">
      <DetailValue label="Số GCN" value={detail.certificate_number} />
      <DetailValue label="Ngày cấp" value={formatCompactDate(detail.issued_on)} />
      <DetailValue label="QĐ cấp" value={detail.decision_reference} />
      <DetailValue label="Cấp lần" value={detail.issuance_sequence_text ? `Lần ${detail.issuance_sequence_text}` : null} />
      <DetailValue label="Tên công ty" value={detail.company_name} />
      <DetailValue label="Trụ sở" multiline value={detail.company_legal_address} />
      <DetailValue label="Tên cơ sở" value={detail.facility_name} />
      <DetailValue label="Địa chỉ cơ sở" multiline value={detail.address} />
      <DetailValue label="PT chuyên môn" value={detail.professional_responsible_person_name} />
      <DetailValue label="ĐBCL / QA" value={detail.quality_assurance_person_name} />
      <DetailValue label="Trình độ chuyên môn" value={detail.professional_qualification_text} />
      <DetailValue label="CCHN" value={detail.professional_license_number} />
      <DetailValue label="Ngày cấp CCHN" value={formatCompactDate(detail.professional_license_issued_on)} />
      <DetailValue label="Nơi cấp CCHN" value={detail.professional_license_issuer} />
      <DetailValue label="Ngày cấp CCHN - PTCM" value={formatCompactDate(detail.responsible_license_issued_on)} />
      <DetailValue label="Nơi cấp CCHN - PTCM" value={detail.responsible_license_issuer} />
      <DetailValue label="Hoạt động kinh doanh" multiline value={detail.business_activity_text} />
      <DetailValue label="Tình trạng" value={detail.current_status_text} />
      <DetailValue label="Thay thế" value={detail.replaces_certificate_number} />
      <DetailValue label="Bị thay thế bởi" value={detail.replaced_by_certificate_number} />
      <DetailValue label="Người xử lý" value={detail.handled_by_name} />
      <DetailValue label="Hồ sơ đề nghị" value={detail.application_dossier_reference} />
      <DetailValue label="Lịch sử cấp" multiline value={detail.issuance_history_text} />
      <div className="summary-span certificate-basis-section">
        <span>Chứng nhận GxP làm căn cứ</span>
        {detail.linked_gxp_certificates.length > 0 ? (
          <ul className="inline-linked-list">
            {detail.linked_gxp_certificates.map((item) => (
              <li key={`${item.certificate_id}:${item.link_role}`}>
                {item.certificate_type}
                {item.line_code ? ` ${item.line_code}` : ""}
                {item.certificate_number ? ` · ${item.certificate_number}` : ""}
                {item.issue_date ? ` · ${formatCompactDate(item.issue_date)}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <strong>Chưa có</strong>
        )}
      </div>
    </div>
  );
}
