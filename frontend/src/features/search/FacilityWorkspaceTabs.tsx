import { EmptyState } from "../../components/EmptyState";
import type { CaseDetail, FacilityHistoryItem, FacilityWorkspaceSummary } from "../../types";
import { formatCompactDate, formatStatusLabel } from "../../lib/presentation";
import { EventWorkspace } from "./EventWorkspace";
import { FacilitySummary } from "./FacilitySummary";
import { HistoryTable } from "./HistoryTable";

const FACILITY_TABS = [
  "Thông tin chung",
  "Các đợt kiểm tra & thay đổi",
  "Giấy chứng nhận GxP",
  "Giấy chứng nhận đủ điều kiện",
] as const;

export function FacilityWorkspaceTabs({
  summary,
  history,
  selectedFacilityTab,
  onFacilityTabChange,
  selectedHistory,
  selectedHistoryId,
  onHistorySelect,
  caseDetail,
  caseDetailLoading,
  caseDetailError,
  activeEventTab,
  onEventTabChange,
}: {
  summary: FacilityWorkspaceSummary;
  history: FacilityHistoryItem[];
  selectedFacilityTab: string;
  onFacilityTabChange: (tab: string) => void;
  selectedHistory: FacilityHistoryItem | null;
  selectedHistoryId: string | null;
  onHistorySelect: (historyId: string) => void;
  caseDetail: CaseDetail | null;
  caseDetailLoading: boolean;
  caseDetailError: string | null;
  activeEventTab: string;
  onEventTabChange: (tab: string) => void;
}) {
  return (
    <section className="panel panel-tight facility-workspace-panel">
      <div className="workspace-tabs facility-tabs tab-strip tab-strip-primary" role="tablist" aria-label="Tab nghiệp vụ cơ sở">
        {FACILITY_TABS.map((tab) => (
          <button
            aria-selected={selectedFacilityTab === tab}
            className={selectedFacilityTab === tab ? "workspace-tab active" : "workspace-tab"}
            key={tab}
            onClick={() => onFacilityTabChange(tab)}
            role="tab"
            type="button"
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="facility-tab-body">
        {selectedFacilityTab === "Thông tin chung" ? (
          <FacilitySummary summary={summary} />
        ) : null}

        {selectedFacilityTab === "Các đợt kiểm tra & thay đổi" ? (
          <div className="event-workspace-split">
            <div className="event-workspace-history-pane">
              <HistoryTable rows={history} selectedHistoryId={selectedHistoryId} onSelect={onHistorySelect} />
            </div>
            <div className="event-workspace-detail-pane">
              <EventWorkspace
                activeTab={activeEventTab}
                caseDetail={caseDetail}
                caseDetailError={caseDetailError}
                caseDetailLoading={caseDetailLoading}
                onTabChange={onEventTabChange}
                selectedHistory={selectedHistory}
              />
            </div>
          </div>
        ) : null}

        {selectedFacilityTab === "Giấy chứng nhận GxP" ? (
          summary.current_certificate_number ||
          summary.current_certificate_issue_date ||
          summary.current_certificate_expiry ||
          summary.current_certificate_standard ||
          summary.certificate_scope_summary ||
          summary.current_certificate_status ? (
            <div className="certificate-shell">
              <div className="detail-grid compact-grid">
                <div>
                  <span>Số GCN hiện hành</span>
                  <strong>{summary.current_certificate_number ?? "Chưa có"}</strong>
                </div>
                <div>
                  <span>Ngày cấp</span>
                  <strong>{formatCompactDate(summary.current_certificate_issue_date)}</strong>
                </div>
                <div>
                  <span>Hết hạn</span>
                  <strong>{formatCompactDate(summary.current_certificate_expiry)}</strong>
                </div>
                <div>
                  <span>GxP</span>
                  <strong>{summary.selected_gxp_type ?? "Chưa xác định"}</strong>
                </div>
                <div>
                  <span>Tiêu chuẩn</span>
                  <strong>{summary.current_certificate_standard ?? "Chưa có"}</strong>
                </div>
                <div>
                  <span>Tình trạng</span>
                  <strong>{formatStatusLabel(summary.current_certificate_status)}</strong>
                </div>
                <div className="summary-span">
                  <span>Phạm vi chứng nhận</span>
                  <strong className="multiline-value">{summary.certificate_scope_summary ?? "Chưa có dữ liệu scope hiện hành."}</strong>
                </div>
              </div>
              <EmptyState
                title="Lịch sử chứng nhận chưa mở ở Slice A.2"
                description="Owner layer hiện mới trả current certificate projection đủ an toàn cho ngữ cảnh đang chọn. History/detail API cho chứng nhận GxP sẽ nối ở Slice B."
              />
            </div>
          ) : (
            <EmptyState
              title="Chưa có dữ liệu chứng nhận GxP"
              description="Current certificate projection chưa có dữ liệu cho facility/line/GxP đang chọn hoặc certificate scope lịch sử chưa được backend read model mở ra."
            />
          )
        ) : null}

        {selectedFacilityTab === "Giấy chứng nhận đủ điều kiện" ? (
          <EmptyState
            title="Workspace ĐĐKKDD chưa mở ở Slice A.2"
            description="Top-level tab đã được đặt đúng hierarchy. History/detail read API cho giấy chứng nhận đủ điều kiện vẫn là khoảng trống backend cần nối ở Slice B."
          />
        ) : null}
      </div>
    </section>
  );
}
