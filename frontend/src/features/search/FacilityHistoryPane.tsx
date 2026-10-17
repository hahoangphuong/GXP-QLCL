import type { FacilityHistoryItem } from "../../types";
import { HistoryTable } from "./HistoryTable";

export function FacilityHistoryPane({
  rows,
  selectedHistoryId,
  onSelect,
  loading,
  error,
  hasSelection,
}: {
  rows: FacilityHistoryItem[];
  selectedHistoryId: string | null;
  onSelect: (historyId: string) => void;
  loading: boolean;
  error: string | null;
  hasSelection: boolean;
}) {
  if (hasSelection && !loading && !error) {
    return <HistoryTable rows={rows} selectedHistoryId={selectedHistoryId} onSelect={onSelect} />;
  }

  return (
    <section className="panel panel-tight history-panel" aria-label="Lịch sử kiểm tra & thay đổi" aria-busy={loading && !error}>
      <div className="panel-header"><h3>Lịch sử kiểm tra & thay đổi</h3></div>
      {error ? (
        <p className="history-pane-message form-error" role="alert">{error}</p>
      ) : (
        <p className="history-pane-message" role="status">
          {loading ? "Đang tải lịch sử của ngữ cảnh đang chọn..." : "Chọn cơ sở hoặc dây chuyền để xem lịch sử."}
        </p>
      )}
    </section>
  );
}
