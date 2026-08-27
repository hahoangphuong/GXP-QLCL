import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { formatStatusLabel } from "../../lib/presentation";
import type { CaseDetail, FacilityHistoryItem } from "../../types";

const EVENT_TABS = ["Hồ sơ", "Kiểm tra", "Khắc phục", "Xử lý", "Chứng nhận GPs", "Chứng nhận khác"] as const;

export function EventWorkspace({
  selectedHistory,
  caseDetail,
  caseDetailLoading,
  caseDetailError,
  activeTab,
  onTabChange,
}: {
  selectedHistory: FacilityHistoryItem | null;
  caseDetail: CaseDetail | null;
  caseDetailLoading: boolean;
  caseDetailError: string | null;
  activeTab: string;
  onTabChange: (tab: string) => void;
}) {
  if (!selectedHistory) {
    return (
      <EmptyState
        title="Chưa chọn sự kiện"
        description="Chọn một dòng lịch sử để xem vùng detail nghiệp vụ bên dưới."
      />
    );
  }

  return (
    <section className="event-workspace">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Các đợt kiểm tra & thay đổi</p>
          <h3>{selectedHistory.reference_code ?? selectedHistory.event_type}</h3>
        </div>
        <StatusBadge value={selectedHistory.state} />
      </div>
      <div className="workspace-tabs" role="tablist" aria-label="Vùng detail sự kiện">
        {EVENT_TABS.map((tab) => (
          <button
            className={activeTab === tab ? "workspace-tab active" : "workspace-tab"}
            key={tab}
            onClick={() => onTabChange(tab)}
            type="button"
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="workspace-body">
      {selectedHistory.source_type === "change_request" ? (
        <div className="detail-grid compact-grid">
          <div>
            <span>Loại</span>
            <strong>Thay đổi cơ sở</strong>
          </div>
          <div>
            <span>Mã tham chiếu</span>
            <strong>{selectedHistory.reference_code ?? "Chưa có"}</strong>
          </div>
          <div className="summary-span">
            <span>Phạm vi</span>
            <strong>{selectedHistory.standard ?? "Chưa có dữ liệu chi tiết từ backend"}</strong>
          </div>
        </div>
      ) : caseDetail ? (
        <div className="detail-grid compact-grid">
          <div>
            <span>Mã hồ sơ</span>
            <strong>{caseDetail.legacy_inspection_code ?? caseDetail.id}</strong>
          </div>
          <div>
            <span>GxP</span>
            <strong>{caseDetail.gxp_type}</strong>
          </div>
          <div>
            <span>Tiêu chuẩn</span>
            <strong>{caseDetail.applicable_standard ?? caseDetail.scope_code ?? "Chưa có"}</strong>
          </div>
          <div>
            <span>Trạng thái</span>
            <strong>{formatStatusLabel(caseDetail.state)}</strong>
          </div>
          <div>
            <span>Loại kiểm tra</span>
            <strong>{caseDetail.inspection_type ?? "Chưa có"}</strong>
          </div>
          <div>
            <span>Năm mở hồ sơ</span>
            <strong>{caseDetail.opened_year ?? "Chưa có"}</strong>
          </div>
          <div className="summary-span">
            <span>{activeTab}</span>
            <strong>
              {activeTab === "Hồ sơ"
                ? "Slice A hiển thị detail nền và giữ ngữ cảnh chọn sự kiện; các form nghiệp vụ sâu hơn sẽ nối ở Slice B."
                : "Tab này đã được giữ đúng vị trí trong workflow, nhưng hành vi chi tiết chỉ mở khi backend/read model tương ứng sẵn sàng."}
            </strong>
          </div>
        </div>
      ) : caseDetailLoading ? (
        <EmptyState title="Đang tải chi tiết hồ sơ" description="Đang lấy thông tin hồ sơ được chọn từ API có xác thực." />
      ) : caseDetailError ? (
        <EmptyState
          title="Không tải được chi tiết hồ sơ"
          description="Chi tiết hồ sơ hiện không sẵn sàng cho lựa chọn đang mở. Vui lòng chọn lại hoặc thử sau."
        />
      ) : (
        <EmptyState title="Chưa có chi tiết hồ sơ" description="Backend chưa trả dữ liệu chi tiết cho lựa chọn hiện tại." />
      )}
      </div>
    </section>
  );
}
