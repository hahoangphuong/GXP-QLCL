import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { formatCompactDate } from "../../lib/presentation";
import type { BusinessEligibilityDetail, BusinessEligibilityListItem } from "../../types";

function DetailValue({
  label,
  value,
  multiline = false,
}: {
  label: string;
  value: string | null | undefined;
  multiline?: boolean;
}) {
  return (
    <div className={multiline ? "summary-span" : undefined}>
      <span>{label}</span>
      <strong className={multiline ? "multiline-value" : undefined}>{value || "Chưa có"}</strong>
    </div>
  );
}

export function BusinessEligibilityWorkspace({
  items,
  listLoading,
  listError,
  selectedCertificateId,
  onSelectCertificate,
  detail,
  detailLoading,
  detailError,
}: {
  items: BusinessEligibilityListItem[];
  listLoading: boolean;
  listError: string | null;
  selectedCertificateId: string | null;
  onSelectCertificate: (certificateId: string) => void;
  detail: BusinessEligibilityDetail | null;
  detailLoading: boolean;
  detailError: string | null;
}) {
  if (listError) {
    return <ErrorState message={listError} />;
  }

  if (listLoading && items.length === 0) {
    return <EmptyState title="Đang tải giấy chứng nhận đủ điều kiện" description="Đang đồng bộ danh mục giấy chứng nhận đủ điều kiện của cơ sở đang chọn." />;
  }

  if (!listLoading && items.length === 0) {
    return <EmptyState title="Chưa có giấy chứng nhận đủ điều kiện" description="Cơ sở đang chọn chưa có giấy chứng nhận đủ điều kiện trong dữ liệu hiện có." />;
  }

  return (
    <div className="certificate-workspace-split">
      <section className="panel panel-tight certificate-list-panel">
        <div className="panel-header">
          <h3>Danh mục GCN đủ điều kiện</h3>
          <span className="panel-meta">{items.length} giấy</span>
        </div>
        <div className="table-scroll table-scroll-history">
          <table className="dense-table eligibility-history-table">
            <thead>
              <tr>
                <th className="col-cert-number">Số GCN</th>
                <th className="col-date">Ngày cấp</th>
                <th className="col-sequence">Lần</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  aria-selected={selectedCertificateId === item.business_eligibility_certificate_id}
                  className={selectedCertificateId === item.business_eligibility_certificate_id ? "selected" : ""}
                  key={item.business_eligibility_certificate_id}
                  onClick={() => onSelectCertificate(item.business_eligibility_certificate_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectCertificate(item.business_eligibility_certificate_id);
                    }
                  }}
                  tabIndex={0}
                >
                  <td title={item.certificate_number ?? ""}>
                    <div className="cell-stack">
                      <strong>{item.certificate_number ?? "Chưa có"}</strong>
                      {item.latest_flag ? <span>Hiện hành</span> : null}
                    </div>
                  </td>
                  <td>{formatCompactDate(item.issued_on)}</td>
                  <td>{item.issuance_sequence_text ? `Lần ${item.issuance_sequence_text}` : "Chưa có"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel panel-tight certificate-detail-panel">
        {detailError ? (
          <ErrorState message={detailError} />
        ) : detailLoading || !detail ? (
          <EmptyState title="Đang tải chi tiết ĐĐK" description="Đang lấy chi tiết giấy chứng nhận đủ điều kiện đang chọn." />
        ) : (
          <>
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
          </>
        )}
      </section>
    </div>
  );
}
