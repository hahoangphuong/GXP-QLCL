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
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Kết quả</p>
          <h3>Danh sách cơ sở</h3>
        </div>
        <span className="panel-meta">{rows.length} dòng</span>
      </div>
      <div className="table-scroll table-scroll-tall">
        <table className="dense-table facility-table">
          <thead>
            <tr>
              <th>Mã cơ sở</th>
              <th>Tên cơ sở</th>
              <th>Công ty</th>
              <th>GxP</th>
              <th>Phạm vi/tiêu chuẩn</th>
              <th>Tỉnh/thành</th>
              <th>Kiểm tra gần nhất</th>
              <th>Trạng thái</th>
              <th>Chứng nhận</th>
              <th>Hết hạn</th>
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
