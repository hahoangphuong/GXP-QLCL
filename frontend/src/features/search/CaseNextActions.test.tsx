import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CaseWorkspace, LifecycleActionReadiness } from "../../types";
import { CaseNextActions } from "./CaseNextActions";

const action = (action_key: string, available: boolean, reason_code: string | null = null, label = action_key): LifecycleActionReadiness => ({ action_key, label, available, reason_code, required_permissions: [], expected_version: 1 });
function workspace(): CaseWorkspace {
  return {
    case_summary: { id: "case-A", state: "inspection_completed", gxp_type: "GMP" },
    stage_edit_actions: [action("edit_case_application", true), action("edit_case_assessment", false, "missing_permission"), action("edit_inspection_plan", true)],
    inspection: { outcome_edit_readiness: action("edit_inspection_outcome", true, null, "Cập nhật kết quả kiểm tra"), final_evaluation_readiness: action("finalize_inspection_outcome", false, "latest_capa_not_accepted"), approval_actions: [action("create_approval_pct", true), action("create_approval_ct", false, "completed_pct_required")] },
    remediation: { cycles: [{ capa_cycle_id: "cycle-A", round_no: 2 }], actions: [action("assess_capa_cycle:cycle-A", true)] },
    certificate_issue_readiness: { action_key: "issue_certificate", label: "Cấp GCN", certificate_type: "GMP", available: false, reason_code: "missing_permission" },
    transition_actions: [],
    linked_gxp_certificates: [{ certificate_id: "certificate-A", certificate_type: "GMP", certificate_number: "GCN-A", action_readiness: [action("edit_latest_version", true, null, "Cập nhật chứng nhận"), action("promote_current", false, "certificate_data_incomplete", "Đặt làm chứng nhận hiện hành")] }],
  } as unknown as CaseWorkspace;
}

describe("Case next-action guidance", () => {
  it("navigates using backend readiness and exact CAPA identity, without performing writes", () => {
    const navigate = vi.fn();
    render(<CaseNextActions workspace={workspace()} onNavigate={navigate} />);
    const panel = screen.getByRole("region", { name: "Bước xử lý tiếp theo" });
    fireEvent.click(within(panel).getByRole("button", { name: "Đến: Đánh giá khắc phục — lần 2" }));
    expect(navigate).toHaveBeenCalledWith("capa", "cycle-A");
    fireEvent.click(within(panel).getByRole("button", { name: "Đến: create_approval_pct" }));
    expect(navigate).toHaveBeenLastCalledWith("approval", undefined);
    fireEvent.click(within(panel).getByRole("button", { name: "Đến: edit_case_application" }));
    expect(navigate).toHaveBeenLastCalledWith("application", undefined);
    fireEvent.click(within(panel).getByRole("button", { name: "Đến: edit_inspection_plan" }));
    expect(navigate).toHaveBeenLastCalledWith("plan", undefined);
    fireEvent.click(within(panel).getByRole("button", { name: "Đến: Cập nhật kết quả kiểm tra" }));
    expect(navigate).toHaveBeenLastCalledWith("outcome", undefined);
    fireEvent.click(within(panel).getByRole("button", { name: "Đến: Hoàn thiện chứng nhận GCN-A (certificate-A)" }));
    expect(navigate).toHaveBeenLastCalledWith("certificate_edit", "certificate-A");
    expect(within(panel).queryByRole("button", { name: /Cấp GCN/ })).not.toBeInTheDocument();
    fireEvent.click(within(panel).getByText(/Chưa đủ điều kiện/));
    expect(within(panel).getByText(/Cần hoàn tất một lần trình PCT/)).toBeVisible();
    expect(within(panel).getAllByText(/Tài khoản không có quyền/)).toHaveLength(2);
    expect(within(panel).getByText(/Chứng nhận còn thiếu thông tin bắt buộc/)).toBeVisible();
  });

  it("replaces Case A readiness when canonical Case B or terminal data arrives", () => {
    const first = workspace();
    const next = workspace();
    next.case_summary = { ...next.case_summary, id: "case-B", state: "closed" };
    next.remediation = { cycles: [], actions: [] };
    next.stage_edit_actions = [];
    next.inspection = { ...next.inspection, outcome_edit_readiness: action("edit_inspection_outcome", false, "terminal_case", "Cập nhật kết quả kiểm tra"), approval_actions: [], final_evaluation_readiness: action("finalize_inspection_outcome", false, "terminal_case") };
    next.certificate_issue_readiness = { ...next.certificate_issue_readiness, reason_code: "terminal_case" };
    next.linked_gxp_certificates = [];
    const { rerender } = render(<CaseNextActions workspace={first} onNavigate={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Đánh giá khắc phục/ })).toBeInTheDocument();
    rerender(<CaseNextActions workspace={next} onNavigate={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Đánh giá khắc phục/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Backend chưa cung cấp thao tác sẵn sàng/)).toBeInTheDocument();
  });

  it("does not invent readiness for a missing or mismatched certificate contract", () => {
    const value = workspace();
    value.certificate_issue_readiness = { ...value.certificate_issue_readiness, available: true, certificate_type: "GSP" };
    value.stage_edit_actions = undefined;
    value.remediation.actions = [action("unknown_future_action", true)];
    render(<CaseNextActions workspace={value} onNavigate={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Cấp GCN/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /unknown_future_action/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Backend chưa cung cấp readiness riêng cho hồ sơ đăng ký/)).toBeInTheDocument();
  });

  it("keeps per-certificate readiness and navigation bound to the exact Certificate UUID", () => {
    const value = workspace();
    value.linked_gxp_certificates = [
      { certificate_id: "certificate-A", certificate_type: "GMP", certificate_number: "DUPLICATE", action_readiness: [action("edit_latest_version", false, "missing_permission", "Cập nhật chứng nhận")] },
      { certificate_id: "certificate-B", certificate_type: "GMP", certificate_number: "DUPLICATE", action_readiness: [action("edit_latest_version", true, null, "Cập nhật chứng nhận"), action("promote_current", true, null, "Đặt làm chứng nhận hiện hành")] },
    ] as never;
    const navigate = vi.fn();
    render(<CaseNextActions workspace={value} onNavigate={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "Đến: Xử lý hiện hành chứng nhận DUPLICATE (certificate-B)" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith("certificate_promote", "certificate-B");
    fireEvent.click(screen.getByText(/Chưa đủ điều kiện/));
    expect(screen.getByText(/certificate-A/)).toBeVisible();
    expect(screen.getAllByText(/certificate-B/)).toHaveLength(2);
  });

  it("shows canonical evidence without equating a closed Case with certificate issuance", () => {
    const value = workspace();
    value.case_summary = { ...value.case_summary, state: "closed" };
    value.business_evidence = { final_evaluation_recorded: true, latest_capa_status: "accepted", completed_pct_count: 1, completed_ct_count: 1, completed_ct_with_pct_count: 1, linked_certificate_count: 0, complete_certificate_record_count: 0, current_certificate_record_count: 0, certificate_record_state: "none", certified_case_without_complete_certificate_record: true };
    render(<CaseNextActions workspace={value} onNavigate={vi.fn()} />);
    expect(screen.getByText(/chưa có bản ghi chứng nhận liên kết/)).toBeInTheDocument();
    expect(screen.getByText(/Cần đối chiếu/)).toBeInTheDocument();
  });
});
