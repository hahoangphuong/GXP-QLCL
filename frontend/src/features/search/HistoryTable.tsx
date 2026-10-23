import { useId, useLayoutEffect, useRef, useState } from "react";

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
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const previousRowIdsRef = useRef(rows.map((row) => row.id));
  const rowFocusOwnedRef = useRef(false);
  const [focusedHistoryId, setFocusedHistoryId] = useState<string | null>(null);
  const entryId = rows.some((row) => row.id === focusedHistoryId)
    ? focusedHistoryId
    : rows.some((row) => row.id === selectedHistoryId)
      ? selectedHistoryId
      : rows[0]?.id;

  useLayoutEffect(() => {
    const previousIds = previousRowIdsRef.current;
    previousRowIdsRef.current = rows.map((row) => row.id);
    if (!focusedHistoryId || rows.some((row) => row.id === focusedHistoryId)) {
      return;
    }

    const activeElement = document.activeElement;
    const shouldRestoreFocus = rowFocusOwnedRef.current
      && (activeElement === document.body || activeElement === scrollRef.current);
    if (!shouldRestoreFocus) {
      setFocusedHistoryId(null);
      return;
    }

    const previousIndex = Math.max(previousIds.indexOf(focusedHistoryId), 0);
    const nextRow = rows[Math.min(previousIndex, rows.length - 1)];
    if (nextRow) {
      rowRefs.current.get(nextRow.id)?.focus();
    } else {
      setFocusedHistoryId(null);
      scrollRef.current?.focus();
    }
  }, [focusedHistoryId, rows]);

  return (
    <section className="panel panel-tight history-panel" aria-labelledby={headingId}>
      <div className="panel-header">
        <h3 id={headingId}>Lịch sử kiểm tra & thay đổi</h3>
        <span className="panel-meta">{rows.length} sự kiện</span>
      </div>
      <p className="sr-only" id={instructionsId}>
        Dùng phím mũi tên lên hoặc xuống, Home hoặc End để di chuyển. Nhấn Enter hoặc phím cách để chọn sự kiện.
      </p>
      <div
        aria-label="Danh sách lịch sử kiểm tra và thay đổi"
        className="table-scroll table-scroll-history"
        ref={scrollRef}
        role="region"
        tabIndex={-1}
      >
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
                onBlur={(event) => {
                  const nextTarget = event.relatedTarget;
                  if (nextTarget && !Array.from(rowRefs.current.values()).some((element) => element.contains(nextTarget))) {
                    rowFocusOwnedRef.current = false;
                  }
                }}
                onFocus={() => {
                  rowFocusOwnedRef.current = true;
                  setFocusedHistoryId(row.id);
                }}
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
