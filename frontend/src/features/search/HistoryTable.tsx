import { formatCompactDate, formatHistoryEventType, formatStatusLabel } from "../../lib/presentation";
import type { FacilityHistoryItem } from "../../types";

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
          <colgroup>
            <col className="col-event-type" />
            <col className="col-standard" />
            <col className="col-date" />
          </colgroup>
          <thead>
            <tr>
              <th className="col-event-type">Loại</th>
              <th className="col-standard">Tiêu chuẩn</th>
              <th className="col-date">Ngày</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                aria-selected={selectedHistoryId === row.id}
                aria-label={`${formatHistoryEventType(row.event_type)}. ${formatStatusLabel(row.state)}`}
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
                <td>{formatCompactDate(row.occurred_on)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
