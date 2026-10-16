import type { ReactNode } from "react";
import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate } from "../../lib/presentation";
import type { FacilityWorkspaceSummary } from "../../types";

function SummaryField({ label, value, className = "" }: { label: string; value: ReactNode; className?: string }) {
  return <div className={`general-field ${className}`}><dt>{label}</dt><dd>{value || "Chưa có"}</dd></div>;
}

export function FacilitySummary({ summary }: { summary: FacilityWorkspaceSummary }) {
  const gxpContext = [summary.selected_gxp_type, summary.selected_line_code ? `Dây chuyền ${summary.selected_line_code}` : null].filter(Boolean).join(" · ");
  return <div className="summary-panel general-legacy-layout">
    <section className="general-certificate-pane" aria-label="Thông tin về GxP">
      <h3 className="sr-only">Thông tin về GxP</h3>
      <dl className="general-certificate-grid">
        <div className="general-scope-field">
          <dt>Phạm vi chứng nhận<span className="general-standard">{summary.current_certificate_standard || "Chưa có"}</span><span className="general-context">{gxpContext}</span></dt>
          <dd>{summary.certificate_scope_summary || "Chưa có"}</dd>
        </div>
        <SummaryField label="Giới hạn" value="Chưa có dữ liệu giới hạn." className="general-limits" />
      </dl>
        <div className="general-certificate-footer">
          <dl>
            <SummaryField label="Số chứng nhận" value={summary.current_certificate_number} />
            <SummaryField label="Ngày cấp" value={formatCompactDate(summary.current_certificate_issue_date)} />
            <SummaryField label="Hết hạn" value={formatCompactDate(summary.current_certificate_expiry)} />
          </dl>
          <dl>
            <SummaryField label="Tình trạng chứng nhận" value={summary.current_certificate_status ? <StatusBadge value={summary.current_certificate_status} /> : null} />
            <SummaryField label="Tình trạng cơ sở" value={summary.facility_current_status} />
          </dl>
        </div>
    </section>
    <section className="general-identity-pane" aria-label="Thông tin về cơ sở và công ty">
      <h3 className="sr-only">Thông tin về cơ sở và công ty</h3>
      <dl>
        <SummaryField label="Tên cơ sở" value={summary.facility_name} />
        <SummaryField label="Địa chỉ cơ sở" value={summary.address} className="general-address" />
        <SummaryField label="Tên công ty" value={summary.company_name} />
        <SummaryField label="Trụ sở" value={summary.company_legal_address} className="general-address" />
        <SummaryField label="Lãnh đạo" value={summary.company_leader} className="general-highlight" />
        <SummaryField label="PT chuyên môn" value={summary.professional_responsible_person} />
        <SummaryField label="ĐBCL" value={summary.quality_assurance_person} />
        <SummaryField label="Thông tin liên hệ" value={summary.contact_information} className="general-contact" />
        <SummaryField label="Chuyên viên" value={summary.assigned_specialist} />
        <SummaryField label="Nước ngoài" value={summary.company_foreign_investment} className="general-highlight" />
        <SummaryField label="Tỉnh/thành" value={summary.province_name} />
      </dl>
    </section>
  </div>;
}
