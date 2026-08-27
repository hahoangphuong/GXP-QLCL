import { StatusBadge } from "../../components/StatusBadge";
import type { FacilitySearchResult } from "../../types";

export function FacilityTable({
  rows,
  selectedResultKey,
  onSelect,
}: {
  rows: FacilitySearchResult[];
  selectedResultKey: string | null;
  onSelect: (resultKey: string) => void;
}) {
  return (
    <section className="panel panel-tight results-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Kết quả</p>
          <h3>Cơ sở / dây chuyền</h3>
        </div>
        <span className="panel-meta">{rows.length} dòng</span>
      </div>
      <div className="table-scroll table-scroll-fill">
        <table className="dense-table facility-table">
          <thead>
            <tr>
              <th className="col-code">Mã cơ sở/dây chuyền</th>
              <th className="col-facility">Tên cơ sở</th>
              <th className="col-gxp">GxP</th>
              <th className="col-scope">Phạm vi chứng nhận</th>
              <th className="col-province">Tỉnh/thành</th>
              <th className="col-reference">Kiểm tra gần nhất</th>
              <th className="col-status">Trạng thái hồ sơ gần nhất</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                aria-selected={selectedResultKey === row.result_key}
                className={selectedResultKey === row.result_key ? "selected" : ""}
                key={row.result_key}
                onClick={() => onSelect(row.result_key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.result_key);
                  }
                }}
                tabIndex={0}
              >
                <td title={row.context_code ?? row.facility_code ?? ""}>{row.context_code ?? row.facility_code ?? "Chưa có"}</td>
                <td title={row.facility_name}>{row.facility_name}</td>
                <td>{row.gxp_type ?? "Chưa có"}</td>
                <td className="multiline-cell" title={row.certificate_scope_summary ?? ""}>
                  {row.certificate_scope_summary ?? "Chưa có"}
                </td>
                <td>{row.province_name ?? "Chưa có"}</td>
                <td title={row.last_inspection_code ?? ""}>{row.last_inspection_code ?? "Chưa có"}</td>
                <td>
                  <StatusBadge value={row.current_state} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
