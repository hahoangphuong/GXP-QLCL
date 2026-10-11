import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseWorkspace } from "../../types";
import { CaseInspectionWorkspace } from "./CaseInspectionWorkspace";

const workspace = {
  case_summary: { id: "case-uuid", site_id: "site-uuid", production_line_id: "line-uuid", applicable_standard: "WHO-GMP" },
  inspection: { plan_row_version: 3, outcome_row_version: 6, plan_start_on: null, plan_end_on: null,
    plan_decision_reference: "QD-01", plan_decision_date: "2026-08-01", decision_document_hint: null,
    inspected_on: "2026-08-05", executed_on: "2026-08-06", minutes_recorded_on: "2026-08-07",
    minutes_recorded_time: null, compliance_due_on: null, outcome_result: "C", team_display_text: "Inspector A",
    team: null, inspection_period_segments: [], final_evaluation: null },
} as unknown as CaseWorkspace;

afterEach(cleanup);
function inspection(planSave = vi.fn(), outcomeSave = vi.fn(), value = workspace) {
  return <CaseInspectionWorkspace caseWorkspace={value} onInspectionPlanSave={planSave} onInspectionOutcomeSave={outcomeSave}
    onInspectionPeriodSegmentsSave={vi.fn()} onInspectionTeamSave={vi.fn()} onLoadInspectionTeamIdentityOptions={vi.fn()}
    onCreateApprovalSubmission={vi.fn()} onCompleteApprovalSubmission={vi.fn()} onTransitionCase={vi.fn()} />;
}

describe("inspection presentation preserves canonical owners", () => {
  it("groups the decision before dates, team at right, and keeps canonical extras distinct", () => {
    const { container } = render(inspection());
    expect(Array.from(container.querySelectorAll(".inspection-decision-fields .detail-label")).map(node => node.textContent))
      .toEqual(["Số/Tham chiếu QĐKT", "Ngày QĐKT"]);
    expect(container.querySelector(".inspection-team-section")).toContainElement(screen.getByText("Thanh tra viên"));
    expect(container.querySelector(".inspection-date-fields")).toContainElement(screen.getByText("Ngày kiểm tra"));
    expect(container.querySelector(".inspection-date-fields")).toContainElement(screen.getByText("05-08-2026"));
    expect(container.querySelector(".inspection-date-fields")).toContainElement(screen.getByText("Ngày biên bản/report"));
    expect(container.querySelector(".inspection-result-fields")).toContainElement(screen.getByText("Tiêu chuẩn áp dụng"));
    expect(container.querySelector(".inspection-result-fields")).toContainElement(screen.getByText("Đánh giá kết quả"));
    expect(container.querySelector(".inspection-result-fields")).toContainElement(screen.getByRole("button", { name: "Sửa Kết quả kiểm tra" }));
    expect(screen.getByText("Thời điểm thực hiện")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" })).toBeDisabled();
    expect(screen.queryByText("Kết quả thẩm định")).not.toBeInTheDocument();
  });

  it.each([403, 409, 422])("keeps outcome draft and version after %s without retry", async status => {
    const save = vi.fn().mockRejectedValue(Object.assign(new Error("fixture rejection"), { status }));
    render(inspection(vi.fn(), save));
    fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Kết quả kiểm tra" }), { key: "F2" });
    fireEvent.change(screen.getByLabelText("Kết quả kiểm tra"), { target: { value: "draft outcome" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Lưu Đánh giá kết quả" })));
    expect(save).toHaveBeenCalledExactlyOnceWith({ expected_version: 6, outcome_result: "draft outcome" });
    expect(screen.getByRole("alert")).toHaveTextContent(status === 403 ? "không có quyền" : status === 409 ? "đã bị thay đổi" : "chưa hợp lệ");
    expect(screen.getByLabelText("Kết quả kiểm tra")).toHaveValue("draft outcome");
    fireEvent.keyDown(screen.getByLabelText("Kết quả kiểm tra"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Sửa Kết quả kiểm tra" })).toHaveTextContent("C");
    expect(save).toHaveBeenCalledOnce();
  });

  it("preserves decision draft while pending and sends only the plan owner token", async () => {
    let rejectSave!: (error: Error) => void;
    const save = vi.fn(() => new Promise<void>((_resolve, reject) => { rejectSave = reject; }));
    const { rerender } = render(inspection(save));
    fireEvent.keyDown(screen.getByRole("button", { name: "Sửa Số/Tham chiếu QĐKT" }), { key: "Enter" });
    fireEvent.change(screen.getByLabelText("Số/Tham chiếu QĐKT"), { target: { value: "draft decision" } });
    fireEvent.keyDown(screen.getByLabelText("Số/Tham chiếu QĐKT"), { key: "Enter" });
    expect(screen.getByLabelText("Số/Tham chiếu QĐKT")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hủy sửa Số/Tham chiếu QĐKT" })).toBeDisabled();
    expect(save).toHaveBeenCalledExactlyOnceWith({ expected_version: 3, decision_reference: "draft decision" });
    rerender(inspection(save, vi.fn(), { ...workspace, inspection: { ...workspace.inspection, plan_decision_reference: "remote decision" } }));
    await act(async () => rejectSave(Object.assign(new Error("stale"), { status: 409 })));
    expect(screen.getByLabelText("Số/Tham chiếu QĐKT")).toHaveValue("draft decision");
    expect(save).toHaveBeenCalledOnce();
    fireEvent.keyDown(screen.getByLabelText("Số/Tham chiếu QĐKT"), { key: "Escape" });
    expect(screen.getByRole("button", { name: "Sửa Số/Tham chiếu QĐKT" })).toHaveTextContent("remote decision");
  });
});
