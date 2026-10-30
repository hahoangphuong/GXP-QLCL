import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import type { CaseWorkspace } from "../../types";
import { CaseInspectionWorkspace } from "./CaseInspectionWorkspace";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function workspace(version = 2, caseId = "case-A"): CaseWorkspace {
  const readiness = { available: true, reason_code: null, required_permissions: [], expected_version: version };
  return { case_summary: { id: caseId, applicable_standard: "WHO-GMP" }, inspection: {
    plan_row_version: version, plan_start_on: null, plan_end_on: null, planning_sheet_name: null,
    plan_decision_reference: `Plan ${caseId} v${version}`, plan_decision_date: null,
    outcome_row_version: version, outcome_result: `Outcome ${caseId} v${version}`, minutes_recorded_on: null, minutes_recorded_time: null, compliance_due_on: null,
    final_evaluation: null, final_evaluation_readiness: { ...readiness, action_key: "finalize_inspection_outcome", label: "Chốt đánh giá cuối cùng" },
    inspection_period_segments: [{ id: "segment", ordinal: 1, started_on: "2026-10-01", ended_on: "2026-10-02" }],
    inspection_period_edit_readiness: { ...readiness, action_key: "edit_inspection_period", label: "Sửa các đợt kiểm tra", mode: "replace" },
    team: { team_id: "team-A", row_version: version, members: [{ id: "member-A", inspector_profile_id: "profile-A", person_id: null, display_name: "Inspector A", role_code: "LEADER", sort_order: 1 }], round_trip_safe: true },
    team_edit_readiness: { ...readiness, action_key: "edit_inspection_team", label: "Sửa đoàn kiểm tra", mode: "replace" },
    approval_submissions: [], approval_actions: [],
  } } as unknown as CaseWorkspace;
}
function setup(value = workspace()) {
  const handlers = { onInspectionPlanSave: vi.fn().mockResolvedValue(undefined), onInspectionOutcomeSave: vi.fn().mockResolvedValue(undefined),
    onInspectionPeriodSegmentsSave: vi.fn().mockResolvedValue(undefined), onInspectionTeamSave: vi.fn().mockResolvedValue(undefined),
    onLoadInspectionTeamIdentityOptions: vi.fn().mockResolvedValue([{ identity_kind: "inspector_profile", inspector_profile_id: "profile-A", person_id: null, display_name: "Inspector A", is_active: true }]), onFinalizeInspectionOutcome: vi.fn().mockResolvedValue(undefined),
    onCreateApprovalSubmission: vi.fn(), onCompleteApprovalSubmission: vi.fn(), onTransitionCase: vi.fn() };
  const view = render(<StrictMode><CaseInspectionWorkspace caseWorkspace={value} {...handlers} /></StrictMode>);
  return { ...view, handlers, refresh: (next: CaseWorkspace) => view.rerender(<StrictMode><CaseInspectionWorkspace caseWorkspace={next} {...handlers} /></StrictMode>) };
}

describe("Inspection editor identity and token ownership", () => {
  async function openSection(view: ReturnType<typeof setup>, section: "plan" | "outcome" | "period" | "team" | "final") {
    if (section === "plan" || section === "outcome") {
      fireEvent.doubleClick(screen.getByRole("button", { name: section === "plan" ? "Sửa Số/Tham chiếu QĐKT" : "Sửa Kết quả kiểm tra" }));
      const input = section === "plan" ? "Số/Tham chiếu QĐKT" : "Kết quả kiểm tra";
      fireEvent.change(screen.getByLabelText(input), { target: { value: "Retained draft" } });
      return { callback: section === "plan" ? view.handlers.onInspectionPlanSave : view.handlers.onInspectionOutcomeSave, input, save: section === "plan" ? "Lưu Số/Tham chiếu QĐKT" : "Lưu Đánh giá kết quả", value: "Retained draft" };
    }
    if (section === "period") {
      fireEvent.click(screen.getByRole("button", { name: "Sửa các đợt kiểm tra" }));
      fireEvent.change(screen.getByLabelText("Từ ngày lần 1"), { target: { value: "2026-10-03" } });
      return { callback: view.handlers.onInspectionPeriodSegmentsSave, input: "Từ ngày lần 1", save: "Lưu các đợt kiểm tra", value: "2026-10-03" };
    }
    if (section === "team") {
      fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
      await screen.findByLabelText("Định danh thành viên 1");
      return { callback: view.handlers.onInspectionTeamSave, input: "Định danh thành viên 1", save: "Lưu đoàn kiểm tra", value: "profile:profile-A" };
    }
    fireEvent.change(screen.getByLabelText("Đánh giá cuối cùng"), { target: { value: "Final draft" } });
    return { callback: view.handlers.onFinalizeInspectionOutcome, input: "Đánh giá cuối cùng", save: "Chốt đánh giá cuối cùng", value: "Final draft" };
  }

  it.each([403, 404, 409, 422, undefined])("keeps each owner's error contract for status %s without retry", async status => {
    for (const section of ["plan", "outcome", "period", "team", "final"] as const) {
      const view = setup();
      const editor = await openSection(view, section);
      editor.callback.mockRejectedValue(Object.assign(new Error("Controlled rejection"), { status }));
      fireEvent.click(screen.getByRole("button", { name: editor.save }));
      await screen.findByRole("alert");
      expect(editor.callback).toHaveBeenCalledOnce();
      expect(editor.callback.mock.calls[0][0]).toEqual(expect.objectContaining({ expected_version: 2 }));
      if (section === "team" && status === 409) expect(screen.queryByLabelText(editor.input)).not.toBeInTheDocument();
      else expect(screen.getByLabelText(editor.input)).toHaveValue(editor.value);
      view.unmount();
    }
  });

  it.each(["plan", "outcome", "period", "team", "final"] as const)("keeps %s pending through refresh without a second command", async section => {
    const view = setup();
    const editor = await openSection(view, section);
    const request = deferred<void>();
    editor.callback.mockImplementation(() => request.promise);
    fireEvent.click(screen.getByRole("button", { name: editor.save }));
    view.refresh(workspace(3));
    expect(screen.getByLabelText(editor.input)).toHaveValue(editor.value);
    expect(screen.getByLabelText(editor.input)).toBeDisabled();
    fireEvent.keyDown(screen.getByLabelText(editor.input), { key: "Escape" });
    expect(screen.getByLabelText(editor.input)).toBeInTheDocument();
    await act(async () => request.reject(Object.assign(new Error("conflict"), { status: 409 })));
    expect(editor.callback).toHaveBeenCalledOnce();
    if (section !== "team") expect(screen.getByLabelText(editor.input)).toHaveValue(editor.value);
    else expect(screen.queryByLabelText(editor.input)).not.toBeInTheDocument();
  });

  it("keeps the team snapshot with its token while identity options are pending", async () => {
    const request = deferred<unknown[]>();
    const view = setup();
    view.handlers.onLoadInspectionTeamIdentityOptions.mockImplementation(() => request.promise);
    fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
    const refreshed = workspace(3);
    refreshed.inspection.team!.members[0].inspector_profile_id = "profile-B";
    view.refresh(refreshed);
    await act(async () => request.resolve([
      { identity_kind: "inspector_profile", inspector_profile_id: "profile-A", person_id: null, display_name: "A" },
      { identity_kind: "inspector_profile", inspector_profile_id: "profile-B", person_id: null, display_name: "B" },
    ]));
    expect(screen.getByLabelText("Định danh thành viên 1")).toHaveValue("profile:profile-A");
    fireEvent.click(screen.getByRole("button", { name: "Lưu đoàn kiểm tra" }));
    await waitFor(() => expect(view.handlers.onInspectionTeamSave).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 2, members: [expect.objectContaining({ inspector_profile_id: "profile-A" })] })));
  });

  it("replaces the editor when the canonical team UUID is replaced within the same Case", async () => {
    const view = setup();
    fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
    await screen.findByLabelText("Định danh thành viên 1");
    const replacement = workspace(2);
    replacement.inspection.team!.team_id = "team-B";
    replacement.inspection.team!.members[0].inspector_profile_id = "profile-B";
    view.refresh(replacement);
    expect(screen.queryByLabelText("Định danh thành viên 1")).not.toBeInTheDocument();
    expect(view.handlers.onInspectionTeamSave).not.toHaveBeenCalled();
  });

  it("does not reenter an open team editor and recapture a refreshed token", async () => {
    const view = setup();
    fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
    await screen.findByLabelText("Định danh thành viên 1");
    view.refresh(workspace(3));
    fireEvent.click(screen.getByRole("button", { name: "Sửa đoàn kiểm tra" }));
    expect(view.handlers.onLoadInspectionTeamIdentityOptions).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Lưu đoàn kiểm tra" }));
    await waitFor(() => expect(view.handlers.onInspectionTeamSave).toHaveBeenCalledWith(expect.objectContaining({ expected_version: 2 })));
  });
  it.each(["plan", "outcome"] as const)("pins the %s draft token through refresh and 409; Cancel/reopen adopts reviewed data", async section => {
    const view = setup();
    const callback = section === "plan" ? view.handlers.onInspectionPlanSave : view.handlers.onInspectionOutcomeSave;
    callback.mockRejectedValue(Object.assign(new Error("conflict"), { status: 409 }));
    const edit = section === "plan" ? "Sửa Số/Tham chiếu QĐKT" : "Sửa Kết quả kiểm tra";
    const input = section === "plan" ? "Số/Tham chiếu QĐKT" : "Kết quả kiểm tra";
    const save = section === "plan" ? "Lưu Số/Tham chiếu QĐKT" : "Lưu Đánh giá kết quả";
    fireEvent.keyDown(screen.getByRole("button", { name: edit }), { key: "F2" });
    fireEvent.change(screen.getByLabelText(input), { target: { value: "Local draft" } });
    view.refresh(workspace(3));
    expect(screen.getByLabelText(input)).toHaveValue("Local draft");
    fireEvent.click(screen.getByRole("button", { name: save }));
    await screen.findByRole("alert");
    expect(callback.mock.calls[0][0]).toEqual(expect.objectContaining({ expected_version: 2 }));
    expect(screen.getByLabelText(input)).toHaveValue("Local draft");
    expect(callback).toHaveBeenCalledOnce();
    fireEvent.keyDown(screen.getByLabelText(input), { key: "Escape" });
    fireEvent.keyDown(screen.getByRole("button", { name: edit }), { key: "F2" });
    expect(screen.getByLabelText(input)).toHaveValue(`${section === "plan" ? "Plan" : "Outcome"} case-A v3`);
    fireEvent.click(screen.getByRole("button", { name: save }));
    await waitFor(() => expect(callback).toHaveBeenCalledTimes(2));
    expect(callback.mock.calls[1][0]).toEqual(expect.objectContaining({ expected_version: 3 }));
  });

  it.each(["period", "team"] as const)("does not upgrade the %s replacement token during an open editor", async section => {
    const view = setup();
    fireEvent.click(screen.getByRole("button", { name: section === "period" ? "Sửa các đợt kiểm tra" : "Sửa đoàn kiểm tra" }));
    if (section === "team") await screen.findByLabelText("Định danh thành viên 1");
    else fireEvent.change(screen.getByLabelText("Từ ngày lần 1"), { target: { value: "2026-10-03" } });
    view.refresh(workspace(3));
    fireEvent.click(screen.getByRole("button", { name: section === "period" ? "Lưu các đợt kiểm tra" : "Lưu đoàn kiểm tra" }));
    const callback = section === "period" ? view.handlers.onInspectionPeriodSegmentsSave : view.handlers.onInspectionTeamSave;
    await waitFor(() => expect(callback).toHaveBeenCalledOnce());
    expect(callback.mock.calls[0][0]).toEqual(expect.objectContaining({ expected_version: 2 }));
  });

  it("pins final-evaluation input to its original readiness token", async () => {
    const view = setup();
    fireEvent.change(screen.getByLabelText("Đánh giá cuối cùng"), { target: { value: "accepted" } });
    view.refresh(workspace(3));
    fireEvent.click(screen.getByRole("button", { name: "Chốt đánh giá cuối cùng" }));
    await waitFor(() => expect(view.handlers.onFinalizeInspectionOutcome).toHaveBeenCalledWith({ expected_version: 2, final_evaluation: "accepted" }));
  });

  it.each(["resolve", "reject"] as const)("replaces Case editors and ignores old pending %s through A → B → A", async completion => {
    const request = deferred<void>();
    const view = setup();
    view.handlers.onInspectionPlanSave.mockImplementation(() => request.promise);
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Số/Tham chiếu QĐKT" }));
    fireEvent.change(screen.getByLabelText("Số/Tham chiếu QĐKT"), { target: { value: "Old A draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu Số/Tham chiếu QĐKT" }));
    view.refresh(workspace(2, "case-B"));
    expect(screen.queryByLabelText("Số/Tham chiếu QĐKT")).not.toBeInTheDocument();
    view.refresh(workspace(2));
    fireEvent.doubleClick(screen.getByRole("button", { name: "Sửa Số/Tham chiếu QĐKT" }));
    fireEvent.change(screen.getByLabelText("Số/Tham chiếu QĐKT"), { target: { value: "New A draft" } });
    await act(async () => completion === "resolve" ? request.resolve() : request.reject(Object.assign(new Error("late"), { status: 409 })));
    expect(screen.getByLabelText("Số/Tham chiếu QĐKT")).toHaveValue("New A draft");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(view.handlers.onInspectionPlanSave).toHaveBeenCalledOnce();
  });
});
