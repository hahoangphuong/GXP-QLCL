import { StatusBadge } from "../../components/StatusBadge";
import type { FacilityWorkspaceSummary } from "../../types";

function formatDate(value: string | null): string {
  if (!value) {
    return "Chưa có";
  }
  return new Intl.DateTimeFormat("vi-VN").format(new Date(value));
}

export function FacilitySummary({ summary }: { summary: FacilityWorkspaceSummary }) {
  return (
    <div className="summary-panel summary-panel-embedded">
      <div className="summary-head">
        <div className="summary-identity">
          <p className="eyebrow">Thông tin chung</p>
          <h3>{summary.facility_name}</h3>
          <p className="summary-subtitle">{summary.company_name}</p>
        </div>
        <StatusBadge value={summary.current_state} />
      </div>
      <dl className="summary-grid summary-grid-compact">
        <div>
          <dt>Mã cơ sở/dây chuyền</dt>
          <dd>{summary.context_code ?? summary.facility_code ?? "Chưa có"}</dd>
        </div>
        <div>
          <dt>GxP</dt>
          <dd>{summary.selected_gxp_type ?? (summary.gxp_types.join(", ") || "Chưa có")}</dd>
        </div>
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
          <dd>{formatDate(summary.current_certificate_expiry)}</dd>
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
      <div className="action-strip action-strip-compact">
        <button disabled type="button">Công ty</button>
        <button disabled type="button">Cơ sở</button>
        <button disabled type="button">Dây chuyền</button>
        <button disabled type="button">Tái đánh giá</button>
        <button disabled type="button">Thay đổi</button>
      </div>
    </div>
  );
}
