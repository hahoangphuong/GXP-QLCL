import { useId, useRef } from "react";

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
  const headingId = useId();
  const instructionsId = useId();
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const entryId = rows.some((row) => row.id === selectedHistoryId) ? selectedHistoryId : rows[0]?.id;

  return (
    <section className="panel panel-tight history-panel" aria-labelledby={headingId}>
      <div className="panel-header">
        <h3 id={headingId}>Lịch sử kiểm tra & thay đổi</h3>
        <span className="panel-meta">{rows.length} sự kiện</span>
      </div>
      <p className="sr-only" id={instructionsId}>
        Dùng phím mũi tên lên hoặc xuống, Home hoặc End để di chuyển. Nhấn Enter hoặc phím cách để chọn sự kiện.
      </p>
      <div className="table-scroll table-scroll-history">
        <table className="dense-table history-table" aria-labelledby={headingId} aria-describedby={instructionsId}>
          <colgroup>
            <col className="col-event-type" />
            <col className="col-standard" />
            <col className="col-date" />
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className="col-event-type">Loại</th>
              <th scope="col" className="col-standard">Tiêu chuẩn</th>
              <th scope="col" className="col-date">Ngày</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td className="history-empty" colSpan={3}>Chưa có lịch sử kiểm tra hoặc thay đổi trong ngữ cảnh đang chọn.</td></tr>
            ) : null}
            {rows.map((row, index) => (
              <tr
                aria-selected={selectedHistoryId === row.id}
                aria-label={`${formatHistoryEventType(row.event_type)}. ${row.standard ?? "Chưa có tiêu chuẩn"}. ${formatCompactDate(row.occurred_on)}. ${formatStatusLabel(row.state)}`}
                className={selectedHistoryId === row.id ? "selected" : ""}
                title={formatStatusLabel(row.state)}
                key={row.id}
                ref={(element) => {
                  if (element) rowRefs.current.set(row.id, element);
                  else rowRefs.current.delete(row.id);
                }}
                onClick={() => onSelect(row.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.id);
                    return;
                  }
                  const targetIndex = event.key === "ArrowDown" ? Math.min(index + 1, rows.length - 1)
                    : event.key === "ArrowUp" ? Math.max(index - 1, 0)
                    : event.key === "Home" ? 0
                    : event.key === "End" ? rows.length - 1
                    : null;
                  if (targetIndex !== null) {
                    event.preventDefault();
                    rowRefs.current.get(rows[targetIndex].id)?.focus();
                  }
                }}
                tabIndex={entryId === row.id ? 0 : -1}
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
