import { formatStatusLabel } from "../../lib/presentation";
import type { CaseWorkspace, LifecycleActionReadiness } from "../../types";
import { caseReadinessReason } from "./caseReadinessReason";

export type CaseGuidanceTarget = "application" | "assessment" | "inspection" | "plan" | "team" | "period" | "capa" | "final" | "approval" | "certificate" | "lifecycle";

type Guidance = { key: string; label: string; available: boolean; reason: string | null; target: CaseGuidanceTarget; cycleId?: string };

/** Lists only backend-provided readiness. Navigation never performs a write. */
export function CaseNextActions({ workspace, onNavigate }: {
  workspace: CaseWorkspace;
  onNavigate: (target: CaseGuidanceTarget, cycleId?: string) => void;
}) {
  const actions: Guidance[] = [];
  const add = (action: LifecycleActionReadiness | null | undefined, target: CaseGuidanceTarget, label?: string, cycleId?: string) => {
    if (action) actions.push({ key: `${target}:${action.action_key}`, label: label ?? action.label, available: action.available === true, reason: action.reason_code, target, cycleId });
  };
  for (const action of workspace.stage_edit_actions ?? []) {
    if (action.action_key === "edit_case_application") add(action, "application");
    else if (action.action_key === "edit_case_assessment") add(action, "assessment");
    else if (action.action_key === "edit_inspection_plan") add(action, "plan");
  }
  const team = workspace.inspection?.team_edit_readiness;
  if (team) actions.push({ key: "team", label: team.label, available: team.available === true, reason: team.reason_code, target: "team" });
  const periods = workspace.inspection?.inspection_period_edit_readiness;
  if (periods) actions.push({ key: "periods", label: periods.label, available: periods.available === true, reason: periods.reason_code, target: "period" });
  for (const action of workspace.remediation?.actions ?? []) {
    const [kind, cycleId] = action.action_key.split(":");
    const labels: Record<string, string> = { create_capa_cycle: "Thêm vòng khắc phục", update_capa_cycle: "Cập nhật vòng khắc phục", submit_capa_cycle: "Ghi nhận tiếp nhận khắc phục", assess_capa_cycle: "Đánh giá khắc phục" };
    if (!labels[kind]) continue;
    const cycle = cycleId ? workspace.remediation?.cycles?.find(item => item.capa_cycle_id === cycleId) : undefined;
    if (cycleId && !cycle) continue;
    add(action, "capa", `${labels[kind]}${cycle ? ` — lần ${cycle.round_no}` : ""}`, cycleId);
  }
  add(workspace.inspection?.final_evaluation_readiness, "final");
  for (const action of workspace.inspection?.approval_actions ?? []) add(action, "approval");
  const issue = workspace.certificate_issue_readiness;
  if (issue?.action_key === "issue_certificate" && issue.certificate_type === workspace.case_summary.gxp_type) actions.push({ key: "certificate", label: issue.label, available: issue.available === true, reason: issue.reason_code, target: "certificate" });
  for (const action of workspace.transition_actions ?? []) {
    add(action, "lifecycle", action.target_state && action.label === action.target_state ? `Chuyển: ${formatStatusLabel(action.target_state)}` : action.label);
  }
  const available = actions.filter(item => item.available);
  const blocked = actions.filter(item => !item.available);
  const missingStages = ([["edit_case_application", "hồ sơ đăng ký"], ["edit_case_assessment", "thẩm định"], ["edit_inspection_plan", "kế hoạch kiểm tra"]] as const)
    .filter(([key]) => !(workspace.stage_edit_actions ?? []).some(action => action.action_key === key))
    .map(([, label]) => label);
  const evidence = workspace.business_evidence;
  const certificateRecordLabels = { none: "chưa có bản ghi chứng nhận liên kết", incomplete: "có bản ghi chứng nhận chưa đủ thông tin", recorded_not_current: "có bản ghi chứng nhận đầy đủ chưa hiện hành", current: "có bản ghi chứng nhận hiện hành" } as const;
  const location: Record<CaseGuidanceTarget, string> = { application: "Hồ sơ đăng ký", assessment: "Thẩm định hồ sơ", inspection: "Kiểm tra thực tế", plan: "Kế hoạch kiểm tra", team: "Đoàn kiểm tra", period: "Các đợt kiểm tra", capa: "Báo cáo khắc phục", final: "Đánh giá cuối trong Kiểm tra thực tế", approval: "Trình PCT / CT trong Kiểm tra thực tế", certificate: "Cấp chứng nhận GPs", lifecycle: "Chuyển trạng thái trong Kiểm tra thực tế" };
  return <section aria-label="Bước xử lý tiếp theo" className="case-next-actions">
    <div className="case-next-actions-heading"><strong>Bước xử lý tiếp theo</strong><span>Trạng thái hồ sơ: {formatStatusLabel(workspace.case_summary.state)}</span></div>
    {evidence ? <div className="workspace-note">Dữ kiện hồ sơ: {evidence.final_evaluation_recorded ? "đã ghi nhận đánh giá cuối" : "chưa ghi nhận đánh giá cuối"}; {evidence.latest_capa_status ? `khắc phục gần nhất: ${formatStatusLabel(evidence.latest_capa_status)}; ` : ""}PCT hoàn tất: {evidence.completed_pct_count}; CT hoàn tất: {evidence.completed_ct_count}; {certificateRecordLabels[evidence.certificate_record_state] ?? "chưa xác định tình trạng bản ghi chứng nhận"}.
      {evidence.certified_case_without_complete_certificate_record ? <strong> Cần đối chiếu: hồ sơ đã chuyển trạng thái nhưng chưa có bản ghi chứng nhận đầy đủ.</strong> : null}
    </div> : <p className="workspace-note">Chưa có dữ kiện nghiệp vụ tổng hợp từ backend.</p>}
    <p className="workspace-note">Backend báo điều kiện thao tác bên dưới. Chọn để đến khu vực xử lý; thao tác này không lưu hoặc chuyển trạng thái. Khóa chờ xác minh tại editor vẫn được áp dụng.</p>
    {available.length ? <div className="case-next-actions-list">{available.map(item => <button className="secondary" key={item.key} onClick={() => onNavigate(item.target, item.cycleId)} type="button">Đến: {item.label}</button>)}</div> : <p className="workspace-note">Backend chưa cung cấp thao tác sẵn sàng trong hồ sơ này.</p>}
    {blocked.length ? <details><summary>Chưa đủ điều kiện ({blocked.length})</summary><ul>{blocked.map(item => <li key={item.key}><strong>{item.label}:</strong> {item.reason ? caseReadinessReason(item.reason) : "Backend chưa cung cấp lý do."} Khu vực: {location[item.target]}.</li>)}</ul></details> : null}
    {missingStages.length ? <p className="workspace-note">Backend chưa cung cấp readiness riêng cho {missingStages.join(", ")}.</p> : null}
    <p className="workspace-note">Ghi nhận kết quả kiểm tra và promote chứng nhận: xem điều kiện tại khu vực xử lý; Case workspace chưa cung cấp readiness riêng cho các thao tác này.</p>
    <div className="case-next-actions-list"><button className="secondary" onClick={() => onNavigate("application")} type="button">Xem hồ sơ đăng ký và thẩm định</button><button className="secondary" onClick={() => onNavigate("inspection")} type="button">Xem kế hoạch và kết quả kiểm tra</button></div>
  </section>;
}
