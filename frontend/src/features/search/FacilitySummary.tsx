import type { ReactNode } from "react";

import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate } from "../../lib/presentation";
import type { FacilityWorkspaceSummary } from "../../types";

function SummaryValue({
  value,
  multiline = false,
}: {
  value: string | null | undefined;
  multiline?: boolean;
}) {
  if (!value) {
    return <dd>Chưa có</dd>;
  }
  return <dd className={multiline ? "multiline-value" : undefined}>{value}</dd>;
}

function SummaryGroup({
  title,
  context,
  children,
}: {
  title: string;
  context?: string | null;
  children: ReactNode;
}) {
  return (
    <section className="summary-group">
      <div className="summary-group-header">
        <h3>{title}</h3>
        {context ? <span className="panel-meta">{context}</span> : null}
      </div>
      <dl className="summary-grid summary-grid-grouped">{children}</dl>
    </section>
  );
}

export function FacilitySummary({ summary }: { summary: FacilityWorkspaceSummary }) {
  const gxpContext = [summary.selected_gxp_type, summary.selected_line_code ? `Dây chuyền ${summary.selected_line_code}` : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="summary-panel summary-panel-grouped">
      <SummaryGroup title="Thông tin về công ty">
        <div>
          <dt>Tên Công ty</dt>
          <SummaryValue value={summary.company_name} />
        </div>
        <div className="summary-span">
          <dt>Địa chỉ trụ sở chính</dt>
          <SummaryValue multiline value={summary.company_legal_address} />
        </div>
        <div>
          <dt>Lãnh đạo</dt>
          <SummaryValue value={summary.company_leader} />
        </div>
        <div>
          <dt>Công ty vốn nước ngoài</dt>
          <SummaryValue value={summary.company_foreign_investment} />
        </div>
        <div>
          <dt>Chuyên viên phụ trách</dt>
          <SummaryValue value={summary.assigned_specialist} />
        </div>
      </SummaryGroup>

      <SummaryGroup title="Thông tin về cơ sở">
        <div>
          <dt>Tên cơ sở</dt>
          <SummaryValue value={summary.facility_name} />
        </div>
        <div>
          <dt>Tỉnh/thành</dt>
          <SummaryValue value={summary.province_name} />
        </div>
        <div className="summary-span">
          <dt>Địa chỉ cơ sở</dt>
          <SummaryValue multiline value={summary.address} />
        </div>
        <div className="summary-span">
          <dt>Thông tin liên hệ</dt>
          <SummaryValue multiline value={summary.contact_information} />
        </div>
        <div>
          <dt>Người Phụ trách chuyên môn</dt>
          <SummaryValue value={summary.professional_responsible_person} />
        </div>
        <div>
          <dt>Người Đảm bảo chất lượng</dt>
          <SummaryValue value={summary.quality_assurance_person} />
        </div>
        <div>
          <dt>Tình trạng hiện tại của cơ sở</dt>
          <SummaryValue value={summary.facility_current_status} />
        </div>
      </SummaryGroup>

      <SummaryGroup title="Thông tin về GxP" context={gxpContext || null}>
        <div>
          <dt>Số giấy chứng nhận gần nhất</dt>
          <SummaryValue value={summary.current_certificate_number} />
        </div>
        <div>
          <dt>Ngày cấp</dt>
          <SummaryValue value={formatCompactDate(summary.current_certificate_issue_date)} />
        </div>
        <div>
          <dt>Ngày hết hạn</dt>
          <SummaryValue value={formatCompactDate(summary.current_certificate_expiry)} />
        </div>
        <div>
          <dt>Tiêu chuẩn GxP</dt>
          <SummaryValue value={summary.current_certificate_standard} />
        </div>
        <div className="summary-span">
          <dt>Phạm vi chứng nhận</dt>
          <SummaryValue multiline value={summary.certificate_scope_summary} />
        </div>
        <div>
          <dt>Tình trạng chứng nhận</dt>
          <dd>{summary.current_certificate_status ? <StatusBadge value={summary.current_certificate_status} /> : "Chưa có"}</dd>
        </div>
      </SummaryGroup>
    </div>
  );
}
