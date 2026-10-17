import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate } from "../../lib/presentation";
import type { GxpCertificateDetail } from "../../types";
import { DetailValue } from "./DetailValue";

export function GxpCertificateDetailFields({ detail, presentation = "facility" }: { detail: GxpCertificateDetail; presentation?: "case" | "facility" }) {
  if (presentation === "facility") return <FacilityGxpCertificateFields detail={detail} />;
  return (
    <div className="detail-grid compact-grid detail-form-matrix certificate-detail-grid legacy-certificate-fields">
      <div className="legacy-certificate-heading">
        <DetailValue label={presentation === "case" ? "Mã số Chứng chỉ" : "Số GCN"} value={detail.certificate_number} />
        <DetailValue label="Ngày cấp" value={formatCompactDate(detail.issue_date)} />
        <DetailValue label={presentation === "case" ? "Ngày hết hạn" : "Hết hạn"} value={formatCompactDate(detail.expiry_date)} />
        <DetailValue label="Tiêu chuẩn" value={detail.applicable_standard} />
      </div>
      <div className="legacy-certificate-body">
        <DetailValue label="Tên cơ sở" value={detail.facility_name} />
        <DetailValue label="Địa chỉ cơ sở" multiline value={detail.address} />
        <DetailValue label="Tên công ty" value={detail.company_name} />
        <DetailValue label="Trụ sở" multiline value={detail.company_legal_address} />
        <DetailValue label="Phạm vi chứng nhận" multiline value={detail.scope_summary} />
        <DetailValue label="Giới hạn" multiline value={detail.limitation_text} />
        <DetailValue label="Cơ quan cấp" value={detail.issuing_authority} />
        <DetailValue label="Tình trạng" value={detail.status ? <StatusBadge value={detail.status} /> : "Chưa có"} />
        <DetailValue label="Nguồn gốc" multiline value={detail.source_description} />
      </div>
    </div>
  );
}

function FacilityGxpCertificateFields({ detail }: { detail: GxpCertificateDetail }) {
  return <div className="detail-grid compact-grid certificate-detail-grid legacy-certificate-fields facility-gxp-fields">
    <div className="legacy-certificate-heading">
      <DetailValue label="Số GCN" value={detail.certificate_number} />
      <DetailValue label="Ngày cấp" value={formatCompactDate(detail.issue_date)} />
      <DetailValue label="Hết hạn" value={formatCompactDate(detail.expiry_date)} />
      <DetailValue label="Tiêu chuẩn" value={detail.applicable_standard} />
    </div>
    <div className="facility-gxp-identity">
      <DetailValue label="Tên cơ sở" value={detail.facility_name} />
      <DetailValue label="Địa chỉ cơ sở" multiline value={detail.address} />
      <DetailValue label="Tên công ty" value={detail.company_name} />
      <DetailValue label="Trụ sở" multiline value={detail.company_legal_address} />
    </div>
    <div className="facility-gxp-scope"><DetailValue label="Phạm vi chứng nhận" multiline value={detail.scope_summary} /></div>
    <div className="facility-gxp-limitation"><DetailValue label="Giới hạn" multiline value={detail.limitation_text} /></div>
    <div className="facility-gxp-footer">
      <div className="facility-gxp-issuer"><DetailValue label="Cơ quan cấp" multiline value={detail.issuing_authority} /></div>
      <div className="facility-gxp-status-source">
        <DetailValue label="Tình trạng" value={detail.status ? <StatusBadge value={detail.status} /> : "Chưa có"} />
        <DetailValue label="Nguồn gốc" multiline value={detail.source_description} />
      </div>
    </div>
    <section className="facility-gxp-scope-records" aria-label="Bản ghi phạm vi chứng nhận">
      <h4>Bản ghi phạm vi chứng nhận</h4>
      {detail.scopes?.length ? <ul className="inline-linked-list">
        {detail.scopes.map(scope => <li key={scope.id}>
          <strong className="multiline-value">{scope.scope_text ?? "Chưa có"}</strong>
          <span>{scope.language_code}{scope.scope_key ? ` · ${scope.scope_key}` : ""}</span>
        </li>)}
      </ul> : <p>Chưa có bản ghi phạm vi canonical.</p>}
    </section>
  </div>;
}
