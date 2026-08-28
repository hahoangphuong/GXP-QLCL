import { StatusBadge } from "../../components/StatusBadge";
import { formatFacilityNameForGrid } from "../../lib/presentation";
import type { FacilitySearchResult } from "../../types";

function formatDate(value: string | null): string {
  if (!value) {
    return "Chưa có";
  }
  return new Intl.DateTimeFormat("vi-VN").format(new Date(value));
}

export function FacilityTable({
  rows,
  selectedResultKey,
  totalCount,
  offset,
  loading,
  onPrevPage,
  onNextPage,
  onSelect,
}: {
  rows: FacilitySearchResult[];
  selectedResultKey: string | null;
  totalCount: number;
  offset: number;
  loading: boolean;
  onPrevPage: () => void;
  onNextPage: () => void;
  onSelect: (resultKey: string) => void;
}) {
  const startRow = totalCount === 0 ? 0 : offset + 1;
  const endRow = Math.min(offset + rows.length, totalCount);

  return (
    <section className="panel panel-tight results-panel">
      <div className="panel-header">
        <div className="panel-heading-inline">
          <h3>Cơ sở/dây chuyền</h3>
          {loading ? <span className="panel-subtle-loading">Đang tải...</span> : null}
        </div>
        <div className="panel-actions panel-actions-tight">
          <span className="panel-meta">{`${startRow}-${endRow} / ${totalCount} dòng`}</span>
          <button className="secondary" disabled={offset === 0} onClick={onPrevPage} type="button">
            Prev
          </button>
          <button className="secondary" disabled={endRow >= totalCount} onClick={onNextPage} type="button">
            Next
          </button>
        </div>
      </div>
      <div className="table-scroll table-scroll-fill">
        <table className="dense-table facility-table">
          <thead>
            <tr>
              <th className="col-code">#</th>
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
                <td title={row.facility_name}>{formatFacilityNameForGrid(row.facility_name)}</td>
                <td>{row.gxp_type ?? "Chưa có"}</td>
                <td className="multiline-cell" title={row.certificate_scope_summary ?? ""}>
                  {row.certificate_scope_summary ?? "Chưa có"}
                </td>
                <td>{row.province_name ?? "Chưa có"}</td>
                <td title={row.last_inspection_on ?? ""}>{formatDate(row.last_inspection_on)}</td>
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
