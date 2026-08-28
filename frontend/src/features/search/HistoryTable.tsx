import { StatusBadge } from "../../components/StatusBadge";
import { formatHistoryEventType } from "../../lib/presentation";
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
    <section className="panel panel-tight history-panel">
      <div className="panel-header">
        <h3>Lịch sử kiểm tra & thay đổi</h3>
        <span className="panel-meta">{rows.length} sự kiện</span>
      </div>
      <div className="table-scroll table-scroll-history">
        <table className="dense-table history-table">
          <thead>
            <tr>
              <th className="col-event-type">Loại sự kiện</th>
              <th className="col-standard">Tiêu chuẩn</th>
              <th className="col-date">Ngày</th>
              <th className="col-state">Trạng thái</th>
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
                <td title={row.event_type}>{formatHistoryEventType(row.event_type)}</td>
                <td title={row.standard ?? ""}>{row.standard ?? "Chưa có"}</td>
                <td>{formatDate(row.occurred_on)}</td>
                <td>
                  <StatusBadge value={row.state} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
