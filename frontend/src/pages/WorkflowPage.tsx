import { useState } from "react";
import { Link } from "react-router-dom";
import type { ApiAccess } from "../App";
import { CaseReport } from "../features/reports/CaseReport";
import { CanonicalRecordReport } from "../features/reports/CanonicalRecordReport";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";

type Queue = "active" | "inspection" | "certificate_decision" | "change_requests" | "expiring";
const QUEUES: { id: Queue; title: string; hint: string }[] = [
  { id: "active", title: "Hồ sơ đang xử lý", hint: "Tất cả Case chưa kết thúc; mở đúng hồ sơ để tiếp tục công việc" },
  { id: "inspection", title: "Chuẩn bị và đang kiểm tra", hint: "Các Case ở trạng thái lập kế hoạch, đã có quyết định hoặc đang kiểm tra" },
  { id: "certificate_decision", title: "Chờ quyết định cấp GCN", hint: "Case đang awaiting_certificate_decision; không đồng nghĩa đã đủ điều kiện cấp giấy" },
  { id: "change_requests", title: "Yêu cầu thay đổi đang mở", hint: "Các Change Request tiếp nhận hoặc đang xem xét, theo UUID của yêu cầu" },
  { id: "expiring", title: "GCN sắp hết hạn", hint: "Các Certificate hiện hành có ngày hết hạn theo cửa sổ 30/60/90 ngày" },
];

export function WorkflowPage({ access, statusError }: { access: ApiAccess; statusError: string | null }) {
  const [queue, setQueue] = useState<Queue>("active");
  if (statusError) return <ErrorState message={statusError} />;
  if (!access.canLoadSecureApi) {
    return <EmptyState title="Cần đăng nhập" description="Đăng nhập để tiếp tục xử lý hồ sơ và các yêu cầu thay đổi có phân quyền." />;
  }
  const selected = QUEUES.find(item => item.id === queue)!;
  return <section className="page-section">
    <header className="section-title"><div>
      <p className="eyebrow">Nghiệp vụ</p><h2>Bàn công việc GxP</h2>
    </div><p className="section-copy">Danh sách công việc đọc trực tiếp từ Case, Certificate và Change Request.
      Chọn từng bản ghi để xem đúng hồ sơ; mọi thao tác chỉnh sửa và phê duyệt tiếp tục được kiểm soát tại workspace nghiệp vụ.</p></header>
    <section className="panel">
      <div className="workflow-queue-options" role="group" aria-label="Nhóm công việc">
        {QUEUES.map(item => <button type="button" key={item.id}
          className={queue === item.id ? "nav-item active" : "nav-item"}
          aria-pressed={queue === item.id} onClick={() => setQueue(item.id)}>
          {item.title}
        </button>)}
      </div>
      <p className="muted-copy">{selected.hint}. <Link className="text-link" to="/reports">Mở Báo cáo đầy đủ</Link></p>
    </section>
    {queue === "change_requests" ? <CanonicalRecordReport key={queue} access={access} kind="change_requests" showDocumentsLink /> :
      queue === "expiring" ? <CanonicalRecordReport key={queue} access={access} kind="certificates" /> :
        <CaseReport key={queue} access={access} inspectionQueue={queue === "inspection"} showDocumentsLink
          initialState={queue === "certificate_decision" ? "awaiting_certificate_decision" : ""} />}
  </section>;
}
