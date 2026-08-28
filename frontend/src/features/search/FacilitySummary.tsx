import { StatusBadge } from "../../components/StatusBadge";
import { formatCompactDate } from "../../lib/presentation";
import type { FacilityWorkspaceSummary } from "../../types";

export function FacilitySummary({ summary }: { summary: FacilityWorkspaceSummary }) {
  return (
    <div className="summary-panel summary-panel-embedded">
      <dl className="summary-grid summary-grid-compact">
        <div>
          <dt>Grain</dt>
          <dd>{summary.context_grain === "production_line" ? "Dây chuyền" : "Cơ sở"}</dd>
        </div>
        <div>
          <dt>Dây chuyền</dt>
          <dd>{summary.selected_line_code ?? "Ngữ cảnh cơ sở"}</dd>
        </div>
        <div>
          <dt>Trạng thái hồ sơ gần nhất</dt>
          <dd>{summary.current_state ? <StatusBadge value={summary.current_state} /> : "Chưa có"}</dd>
        </div>
        <div>
          <dt>Tiêu chuẩn hồ sơ gần nhất</dt>
          <dd>{summary.primary_standard ?? "Chưa có"}</dd>
        </div>
        <div>
          <dt>GCN hiện hành</dt>
          <dd>{summary.current_certificate_number ?? "Chưa có"}</dd>
        </div>
        <div>
          <dt>Hết hạn</dt>
          <dd>{formatCompactDate(summary.current_certificate_expiry)}</dd>
        </div>
        <div className="summary-span">
          <dt>Phạm vi chứng nhận</dt>
          <dd className="multiline-value">{summary.certificate_scope_summary ?? "Chưa có dữ liệu scope hiện hành."}</dd>
        </div>
        <div className="summary-span">
          <dt>Tỉnh/thành</dt>
          <dd>{summary.province_name ?? "Chưa có"}</dd>
        </div>
        <div className="summary-span">
          <dt>Địa chỉ</dt>
          <dd>{summary.address ?? "Chưa có"}</dd>
        </div>
      </dl>
    </div>
  );
}
