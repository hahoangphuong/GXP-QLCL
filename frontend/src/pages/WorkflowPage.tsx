import { Link, useSearchParams } from "react-router-dom";
import type { ApiAccess } from "../App";
import { CaseReport } from "../features/reports/CaseReport";
import { CanonicalRecordReport } from "../features/reports/CanonicalRecordReport";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";

export type Queue = "active" | "inspection" | "certificate_decision" | "change_requests" | "expiring";
const QUEUES: { id: Queue; title: string; hint: string }[] = [
  { id: "active", title: "Hồ sơ đang xử lý", hint: "Tất cả Case chưa kết thúc; mở đúng hồ sơ để tiếp tục công việc" },
  { id: "inspection", title: "Chuẩn bị và đang kiểm tra", hint: "Các Case ở trạng thái lập kế hoạch, đã có quyết định hoặc đang kiểm tra" },
  { id: "certificate_decision", title: "Chờ quyết định cấp GCN", hint: "Case đang awaiting_certificate_decision; không đồng nghĩa đã đủ điều kiện cấp giấy" },
  { id: "change_requests", title: "Yêu cầu thay đổi đang mở", hint: "Các Change Request tiếp nhận hoặc đang xem xét, theo UUID của yêu cầu" },
  { id: "expiring", title: "GCN sắp hết hạn", hint: "Các Certificate hiện hành có ngày hết hạn theo cửa sổ 30/60/90 ngày" },
];

const QUEUE_REPORT: Record<Queue, string> = {
  active: "/reports?report=cases",
  inspection: "/reports?report=inspection",
  certificate_decision: "/reports?report=cases&case_state=awaiting_certificate_decision",
  change_requests: "/reports?report=change_requests",
  expiring: "/reports?report=certificates",
};

function selectedQueue(value: string | null): Queue {
  // URL state is an operator navigation hint, never a backend filter or an authority.
  return QUEUES.find(item => item.id === value)?.id ?? "active";
}

export function WorkflowPage({ access, statusError }: { access: ApiAccess; statusError: string | null }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const queue = selectedQueue(searchParams.get("queue"));
  function selectQueue(next: Queue) {
    setSearchParams(params => {
      const nextParams = new URLSearchParams(params);
      for (const key of ["gxp_type", "state", "case_state", "q", "opened_year", "offset", "expiry_days", "number"]) nextParams.delete(key);
      nextParams.set("queue", next);
      return nextParams;
    });
  }
  if (statusError) return <ErrorState message={statusError} />;
  if (searchParams.getAll("queue").length > 1 || (searchParams.has("queue") && !QUEUES.some(item => item.id === searchParams.get("queue")))) return <p role="alert">Nhóm công việc không hợp lệ.</p>;
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
          aria-pressed={queue === item.id} onClick={() => selectQueue(item.id)}>
          {item.title}
        </button>)}
      </div>
      <p className="muted-copy">{selected.hint}. <Link className="text-link" to={QUEUE_REPORT[queue]}>Mở Báo cáo đầy đủ</Link></p>
    </section>
    {queue === "change_requests" ? <CanonicalRecordReport key={queue} access={access} kind="change_requests" showDocumentsLink urlState returnQueue="change_requests" /> :
      queue === "expiring" ? <CanonicalRecordReport key={queue} access={access} kind="certificates" /> :
        <CaseReport key={queue} access={access} inspectionQueue={queue === "inspection"} showDocumentsLink returnQueue={queue} urlState
          initialState={queue === "certificate_decision" ? "awaiting_certificate_decision" : ""} />}
  </section>;
}
