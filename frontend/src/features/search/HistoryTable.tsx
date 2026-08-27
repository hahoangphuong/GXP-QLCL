import { StatusBadge } from "../../components/StatusBadge";
import type { FacilityHistoryItem } from "../../types";

function formatDate(value: string | null): string {
  if (!value) {
    return "Chưa có";
  }
  return new Intl.DateTimeFormat("vi-VN").format(new Date(value));
}

export function HistoryTable({
  rows,
  selectedHistoryId,
  onSelect,
}: {
  rows: FacilityHistoryItem[];
  selectedHistoryId: string | null;
  onSelect: (historyId: string) => void;
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Lịch sử</p>
          <h3>Kiểm tra và thay đổi</h3>
        </div>
        <span className="panel-meta">{rows.length} sự kiện</span>
      </div>
      <div className="table-scroll">
        <table className="dense-table">
          <thead>
            <tr>
              <th>Loại sự kiện</th>
              <th>Tiêu chuẩn</th>
              <th>Ngày</th>
              <th>Trạng thái</th>
              <th>Mã hồ sơ</th>
              <th>GxP</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                aria-selected={selectedHistoryId === row.id}
                className={selectedHistoryId === row.id ? "selected" : ""}
                key={row.id}
                onClick={() => onSelect(row.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.id);
                  }
                }}
                tabIndex={0}
              >
                <td>{row.event_type}</td>
                <td title={row.standard ?? ""}>{row.standard ?? "Chưa có"}</td>
                <td>{formatDate(row.occurred_on)}</td>
                <td>
                  <StatusBadge value={row.state} />
                </td>
                <td>{row.reference_code ?? "Chưa có"}</td>
                <td>{row.gxp_type ?? "Chưa có"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
