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
    <section className="panel panel-tight summary-panel">
      <div className="summary-head">
        <div className="summary-identity">
          <p className="eyebrow">Ngữ cảnh cơ sở</p>
          <h3>{summary.facility_name}</h3>
          <p className="summary-subtitle">{summary.company_name}</p>
        </div>
        <StatusBadge value={summary.current_state} />
      </div>
      <dl className="summary-grid summary-grid-compact">
        <div>
          <dt>Mã cơ sở</dt>
          <dd>{summary.facility_code ?? "Chưa có"}</dd>
        </div>
        <div>
          <dt>GxP</dt>
          <dd>{summary.gxp_types.join(", ") || "Chưa có"}</dd>
        </div>
        <div>
          <dt>Ngữ cảnh GxP</dt>
          <dd>{summary.selected_gxp_type ?? "Toàn bộ"}</dd>
        </div>
        <div>
          <dt>Tỉnh/thành</dt>
          <dd>{summary.province_name ?? "Chưa có"}</dd>
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
    </section>
  );
}
