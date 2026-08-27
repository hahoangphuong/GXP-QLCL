import { StatusBadge } from "../../components/StatusBadge";
import type { FacilitySearchResult } from "../../types";

function formatDate(value: string | null): string {
  if (!value) {
    return "Chưa có";
  }
  return new Intl.DateTimeFormat("vi-VN").format(new Date(value));
}

export function FacilityTable({
  rows,
  selectedSiteId,
  onSelect,
}: {
  rows: FacilitySearchResult[];
  selectedSiteId: string | null;
  onSelect: (siteId: string) => void;
}) {
  return (
    <section className="panel panel-tight results-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Kết quả</p>
          <h3>Danh sách cơ sở</h3>
        </div>
        <span className="panel-meta">{rows.length} dòng</span>
      </div>
      <div className="table-scroll table-scroll-fill">
        <table className="dense-table facility-table">
          <thead>
            <tr>
              <th className="col-code">Mã cơ sở</th>
              <th className="col-facility">Tên cơ sở</th>
              <th className="col-company">Công ty</th>
              <th className="col-gxp">GxP</th>
              <th className="col-standard">Phạm vi/tiêu chuẩn</th>
              <th className="col-province">Tỉnh/thành</th>
              <th className="col-reference">Kiểm tra gần nhất</th>
              <th className="col-status">Trạng thái hồ sơ</th>
              <th className="col-certificate">GCN hiện hành</th>
              <th className="col-expiry">Hết hạn</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                aria-selected={selectedSiteId === row.site_id}
                className={selectedSiteId === row.site_id ? "selected" : ""}
                key={row.site_id}
                onClick={() => onSelect(row.site_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.site_id);
                  }
                }}
                tabIndex={0}
              >
                <td title={row.facility_code ?? ""}>{row.facility_code ?? "Chưa có"}</td>
                <td title={row.facility_name}>{row.facility_name}</td>
                <td title={row.company_name}>{row.company_name}</td>
                <td>{row.gxp_types.join(", ") || "Chưa có"}</td>
                <td title={row.primary_standard ?? ""}>{row.primary_standard ?? "Chưa có"}</td>
                <td>{row.province_name ?? "Chưa có"}</td>
                <td title={row.last_inspection_code ?? ""}>{row.last_inspection_code ?? "Chưa có"}</td>
                <td>
                  <StatusBadge value={row.current_state} />
                </td>
                <td title={row.current_certificate_number ?? ""}>{row.current_certificate_number ?? "Chưa có"}</td>
                <td>{formatDate(row.current_certificate_expiry)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
