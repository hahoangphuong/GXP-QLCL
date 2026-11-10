import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseDraftSession } from "./CaseDraftSession";
import { CaseApprovalWorkspace } from "./CaseApprovalWorkspace";
import { ApprovalMutationContext } from "./approvalMutationRecovery";

function workspace(overrides: Partial<CaseWorkspace["inspection"]> = {}): CaseWorkspace {
  return {
    case_summary: { id: "case-1" },
    inspection: {
      approval_actions: [],
      approval_submissions: [],
      ...overrides,
    },
  } as CaseWorkspace;
}

const available = (action_key: string, expected_version: number | null = 4) => ({
  action_key,
  label: action_key,
  available: true,
  reason_code: null,
  required_permissions: ["inspection.edit"],
  expected_version,
});

describe("approval canonical recovery draft integrity", () => {
  const pct = (id: string, round: number, completed_on: string | null) => ({
    approval_submission_id: id, case_id: "case-1", row_version: 3, stage: "PCT" as const, round_no: round,
    reference: id, submitted_on: null, submitted_time: null, completed_on, completed_time: null, pct_submission_id: null,
  });

  it("keeps CT creation fields and exact PCT parent immutable while outcome is unverified, including tab remount", () => {
    const onCreate = vi.fn();
    const state = workspace({
      approval_actions: [available("create_approval_ct")],
      approval_submissions: [pct("pct-first", 1, "2026-11-01"), pct("pct-second", 2, "2026-11-06")],
    });
    const editor = (show: boolean, needsReview: boolean) => <CaseDraftSession identity="case-1">
      <ApprovalMutationContext.Provider value={{ pending: false, requiresReview: needsReview }}>
        {show ? <CaseApprovalWorkspace caseWorkspace={state} onCreate={onCreate} onComplete={vi.fn()} /> : null}
      </ApprovalMutationContext.Provider>
    </CaseDraftSession>;
    const view = render(editor(true, false));
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: "CT-ĐÃ-GỬI" } });
    fireEvent.change(screen.getByLabelText("Ngày trình"), { target: { value: "2026-11-08" } });
    fireEvent.change(screen.getByLabelText("Giờ trình"), { target: { value: "10:30" } });
    fireEvent.change(screen.getByLabelText("Lý do tạo trình"), { target: { value: "Đề nghị phê duyệt" } });
    fireEvent.change(screen.getByLabelText("PCT hoàn tất cho CT"), { target: { value: "pct-second" } });
    view.rerender(editor(true, true));
    for (const [name, value] of [["Tham chiếu trình", "CT-ĐÃ-GỬI"], ["Ngày trình", "2026-11-08"], ["Giờ trình", "10:30"], ["Lý do tạo trình", "Đề nghị phê duyệt"]]) {
      expect(screen.getByLabelText(name)).toHaveValue(value);
      expect(screen.getByLabelText(name)).toHaveAttribute("readonly");
    }
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toBeDisabled();
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toHaveValue("pct-second");
    expect(screen.getByRole("button", { name: "Dùng PCT lần 1 để tạo trình CT" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: "OVERWRITTEN" } });
    fireEvent.click(screen.getByRole("button", { name: "Dùng PCT lần 1 để tạo trình CT" }));
    view.rerender(editor(false, true));
    view.rerender(editor(true, true));
    expect(screen.getByLabelText("Tham chiếu trình")).toHaveValue("CT-ĐÃ-GỬI");
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toHaveValue("pct-second");
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("keeps completion date, time, reason and reviewed version immutable while outcome is unverified", () => {
    const onComplete = vi.fn();
    const state = workspace({
      approval_actions: [available("complete_approval:pct-1", 12)],
      approval_submissions: [pct("pct-1", 1, null)],
    });
    const editor = (show: boolean, needsReview: boolean) => <CaseDraftSession identity="case-1">
      <ApprovalMutationContext.Provider value={{ pending: false, requiresReview: needsReview }}>
        {show ? <CaseApprovalWorkspace caseWorkspace={state} onCreate={vi.fn()} onComplete={onComplete} /> : null}
      </ApprovalMutationContext.Provider>
    </CaseDraftSession>;
    const view = render(editor(true, false));
    fireEvent.change(screen.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-11-09" } });
    fireEvent.change(screen.getByLabelText("Giờ hoàn tất trình"), { target: { value: "09:45" } });
    fireEvent.change(screen.getByLabelText("Lý do hoàn tất trình"), { target: { value: "Đã xét duyệt" } });
    view.rerender(editor(true, true));
    for (const [name, value] of [["Ngày hoàn tất trình", "2026-11-09"], ["Giờ hoàn tất trình", "09:45"], ["Lý do hoàn tất trình", "Đã xét duyệt"]]) {
      expect(screen.getByLabelText(name)).toHaveValue(value);
      expect(screen.getByLabelText(name)).toHaveAttribute("readonly");
    }
    expect(screen.getByRole("button", { name: "Hủy nhập hoàn tất PCT lần 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hoàn tất PCT" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Lý do hoàn tất trình"), { target: { value: "OVERWRITTEN" } });
    view.rerender(editor(false, true));
    view.rerender(editor(true, true));
    expect(screen.getByLabelText("Lý do hoàn tất trình")).toHaveValue("Đã xét duyệt");
    expect(screen.getByText(/Thông tin hoàn tất đã nhập được giữ nguyên/)).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("allows edits and parent selection after a definitively rejected request without recovery lock", () => {
    const state = workspace({ approval_actions: [available("create_approval_ct")], approval_submissions: [pct("pct-first", 1, "2026-11-06")] });
    render(<ApprovalMutationContext.Provider value={{ pending: false, requiresReview: false }}>
      <CaseApprovalWorkspace caseWorkspace={state} onCreate={vi.fn()} onComplete={vi.fn()} />
    </ApprovalMutationContext.Provider>);
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: "Có thể sửa" } });
    fireEvent.change(screen.getByLabelText("PCT hoàn tất cho CT"), { target: { value: "pct-first" } });
    expect(screen.getByLabelText("Tham chiếu trình")).not.toHaveAttribute("readonly");
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeEnabled();
  });
});

describe("CaseApprovalWorkspace", () => {
  it("requires a submitted date whenever a time is entered for PCT, without discarding the draft", async () => {
    const onCreate = vi.fn().mockResolvedValue({});
    render(<CaseApprovalWorkspace caseWorkspace={workspace({ approval_actions: [available("create_approval_pct")] })} onCreate={onCreate} onComplete={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Giờ trình"), { target: { value: "09:30" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Cần nhập ngày trình");
    expect(screen.getByRole("button", { name: "Tạo trình PCT" })).toBeDisabled();
    expect(onCreate).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Giờ trình")).toHaveValue("09:30");

    fireEvent.change(screen.getByLabelText("Ngày trình"), { target: { value: "2026-11-08" } });
    expect(screen.queryByText(/Cần nhập ngày trình trước/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình PCT" }));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("PCT", expect.objectContaining({
      submitted_on: "2026-11-08", submitted_time: "09:30", pct_submission_id: null,
    })));
  });

  it("requires a submitted date for CT as well and preserves its exact completed PCT parent", async () => {
    const onCreate = vi.fn().mockResolvedValue({});
    const pct = { approval_submission_id: "pct-2", case_id: "case-1", row_version: 3, stage: "PCT" as const, round_no: 2, reference: "PCT-2", submitted_on: null, submitted_time: null, completed_on: "2026-11-06", completed_time: null, pct_submission_id: null };
    render(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_actions: [available("create_approval_ct")], approval_submissions: [pct],
    })} onCreate={onCreate} onComplete={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("PCT hoàn tất cho CT"), { target: { value: "pct-2" } });
    fireEvent.change(screen.getByLabelText("Giờ trình"), { target: { value: "10:45" } });
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    expect(onCreate).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Ngày trình"), { target: { value: "2026-11-08" } });
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình CT" }));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("CT", expect.objectContaining({
      submitted_on: "2026-11-08", submitted_time: "10:45", pct_submission_id: "pct-2",
    })));
  });

  it("selects the exact completed PCT directly from its history row for a CT without mutation", async () => {
    const onCreate = vi.fn().mockResolvedValue({});
    const pct = (id: string, round: number, completed_on: string | null) => ({
      approval_submission_id: id, case_id: "case-1", row_version: 2, stage: "PCT" as const, round_no: round,
      reference: id, submitted_on: null, submitted_time: null, completed_on, completed_time: null, pct_submission_id: null,
    });
    render(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_actions: [available("create_approval_ct")],
      approval_submissions: [pct("pct-first", 1, "2026-11-01"), pct("pct-incomplete", 2, null), pct("pct-third", 3, "2026-11-07")],
    })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Dùng PCT lần 2 để tạo trình CT" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dùng PCT lần 3 để tạo trình CT" }));
    const selector = screen.getByLabelText("PCT hoàn tất cho CT");
    expect(selector).toHaveValue("pct-third");
    expect(selector).toHaveFocus();
    expect(onCreate).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: "CT theo PCT lần 3" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình CT" }));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("CT", expect.objectContaining({
      pct_submission_id: "pct-third", reference: "CT theo PCT lần 3",
    })));
  });

  it("withdraws the PCT row shortcut when canonical CT creation is no longer available", () => {
    const onCreate = vi.fn();
    const submission = { approval_submission_id: "pct-completed", case_id: "case-1", row_version: 2,
      stage: "PCT" as const, round_no: 1, reference: null, submitted_on: null, submitted_time: null,
      completed_on: "2026-11-07", completed_time: null, pct_submission_id: null };
    const view = render(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_actions: [available("create_approval_ct")], approval_submissions: [submission],
    })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Dùng PCT lần 1 để tạo trình CT" })).toBeEnabled();
    view.rerender(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_actions: [{ ...available("create_approval_ct"), available: false, reason_code: "missing_permission" }],
      approval_submissions: [submission],
    })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Dùng PCT lần 1 để tạo trình CT" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("lets an operator return from a CT to its exact completed PCT and reuse it without creating a submission", () => {
    const onCreate = vi.fn();
    const pct = (id: string, round: number, reference: string) => ({ approval_submission_id: id, case_id: "case-1", row_version: 2, stage: "PCT" as const, round_no: round, reference, submitted_on: null, submitted_time: null, completed_on: "2026-10-01", completed_time: null, pct_submission_id: null });
    render(<CaseApprovalWorkspace caseWorkspace={workspace({ approval_actions: [available("create_approval_ct")], approval_submissions: [pct("pct-1", 1, "PCT-A"), pct("pct-2", 2, "PCT-B"), { ...pct("ct-1", 1, "CT-A"), stage: "CT", pct_submission_id: "pct-2" }] })} onCreate={onCreate} onComplete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Chọn PCT lần 2 cho trình CT" }));
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toHaveValue("pct-2");
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeEnabled();
    expect(onCreate).not.toHaveBeenCalled();
    expect(screen.getByRole("option", { name: /PCT lần 2.*PCT-B/ })).toHaveValue("pct-2");
  });
  it("shows canonical one-to-many PCT/CT lineage and navigates bidirectionally across stage filters without mutation", () => {
    const onCreate = vi.fn();
    const onComplete = vi.fn();
    const pct = (id: string, round: number) => ({
      approval_submission_id: id, case_id: "case-1", row_version: 2,
      stage: "PCT" as const, round_no: round, reference: id,
      submitted_on: null, submitted_time: null, completed_on: "2026-11-02", completed_time: null, pct_submission_id: null,
    });
    const state = workspace({ approval_submissions: [
      pct("pct-one", 1), pct("pct-two", 2),
      { ...pct("ct-a", 1), stage: "CT", pct_submission_id: "pct-two" },
      { ...pct("ct-b", 2), stage: "CT", pct_submission_id: "pct-two" },
      { ...pct("ct-c", 3), stage: "CT", pct_submission_id: "pct-one" },
    ] });
    render(<CaseApprovalWorkspace caseWorkspace={state} onCreate={onCreate} onComplete={onComplete} />);
    const linked = screen.getByLabelText("Các CT của PCT lần 2");
    expect(linked).toHaveTextContent("CT liên kết: 2");
    expect(screen.getByLabelText("Các CT của PCT lần 1")).toHaveTextContent("CT liên kết: 1");

    fireEvent.click(screen.getByRole("button", { name: "PCT (2)" }));
    expect(screen.queryByRole("button", { name: "Xem PCT lần 2 của CT lần 1" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Xem CT lần 1 của PCT lần 2" }));
    expect(screen.getByRole("button", { name: "Tất cả (5)" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("CT lần 1 — ct-a")).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "CT (3)" }));
    fireEvent.click(screen.getByRole("button", { name: "Xem PCT lần 2 của CT lần 2" }));
    expect(screen.getByLabelText("PCT lần 2 — pct-two")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Tất cả (5)" })).toHaveAttribute("aria-pressed", "true");
    expect(onCreate).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("shows missing or incomplete parent without inventing a completed PCT, and blocks CT creation", () => {
    const onCreate = vi.fn();
    const pct = {
      approval_submission_id: "pct-open", case_id: "case-1", row_version: 2, stage: "PCT" as const, round_no: 1,
      reference: null, submitted_on: null, submitted_time: null, completed_on: null, completed_time: null, pct_submission_id: null,
    };
    render(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_submissions: [
        pct,
        { ...pct, approval_submission_id: "ct-linked", stage: "CT", round_no: 1, pct_submission_id: "pct-open" },
        { ...pct, approval_submission_id: "ct-orphan", stage: "CT", round_no: 2, pct_submission_id: "pct-missing" },
      ],
      approval_actions: [{ ...available("create_approval_ct"), available: false, reason_code: "completed_pct_required" }],
    })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Xem PCT lần 1 của CT lần 1" })).toBeEnabled();
    expect(screen.getByText("PCT: pct-missing")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xem PCT lần 1 của CT lần 2" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    expect(screen.getByLabelText("Các CT của PCT lần 1")).toHaveTextContent("CT liên kết: 1");
    fireEvent.click(screen.getByRole("button", { name: "Xem PCT lần 1 của CT lần 1" }));
    expect(screen.getByLabelText("PCT lần 1 — pct-open")).toHaveFocus();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("does not make a foreign Case PCT selectable or navigable, even with a matching parent UUID", () => {
    const onCreate = vi.fn();
    const row = {
      approval_submission_id: "pct-foreign", case_id: "other-case", row_version: 2, stage: "PCT" as const,
      round_no: 1, reference: "Foreign", submitted_on: null, submitted_time: null,
      completed_on: "2026-11-02", completed_time: null, pct_submission_id: null,
    };
    render(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_actions: [available("create_approval_ct")],
      approval_submissions: [
        row,
        { ...row, approval_submission_id: "ct-local", case_id: "case-1", stage: "CT", pct_submission_id: "pct-foreign" },
      ],
    })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    expect(screen.queryByRole("option", { name: /PCT lần 1.*Foreign/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Xem PCT lần 1 của CT lần 1" })).not.toBeInTheDocument();
    expect(screen.getByText("PCT: pct-foreign")).toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("preserves the selected PCT across tab remount without carrying it to another Case", () => {
    const pct = { approval_submission_id: "pct-2", case_id: "case-1", row_version: 2, stage: "PCT" as const, round_no: 2, reference: "PCT-B", submitted_on: null, submitted_time: null, completed_on: "2026-10-01", completed_time: null, pct_submission_id: null };
    const onCreate = vi.fn();
    const editor = (identity: string, show: boolean) => <CaseDraftSession identity={identity}>{show ? <CaseApprovalWorkspace caseWorkspace={workspace({ approval_actions: [available("create_approval_ct")], approval_submissions: [pct] })} onCreate={onCreate} onComplete={vi.fn()} /> : null}</CaseDraftSession>;
    const view = render(editor("case-A", true));
    fireEvent.change(screen.getByLabelText("PCT hoàn tất cho CT"), { target: { value: "pct-2" } });
    view.rerender(editor("case-A", false));
    view.rerender(editor("case-A", true));
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toHaveValue("pct-2");
    view.rerender(editor("case-B", true));
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toHaveValue("");
    view.rerender(editor("case-A", true));
    expect(screen.getByLabelText("PCT hoàn tất cho CT")).toHaveValue("");
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("explains the backend requirement to complete PCT before creating CT", () => {
    const onCreate = vi.fn();
    render(<CaseApprovalWorkspace caseWorkspace={workspace({ approval_actions: [{ ...available("create_approval_ct"), available: false, reason_code: "completed_pct_required" }] })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.getByText(/Cần hoàn tất một lần trình PCT trước khi tạo trình CT/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("does not mutate when backend PCT readiness is unavailable", () => {
    const onCreate = vi.fn();
    render(<CaseApprovalWorkspace caseWorkspace={workspace({ approval_actions: [{ ...available("create_approval_pct"), available: false, reason_code: "missing_permission" }] })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Tạo trình PCT" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình PCT" }));
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("sends the exact PCT request including submitted time and reason", async () => {
    const onCreate = vi.fn().mockResolvedValue({});
    render(<CaseApprovalWorkspace caseWorkspace={workspace({ approval_actions: [available("create_approval_pct")] })} onCreate={onCreate} onComplete={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Tham chiếu trình"), { target: { value: " PCT-01 " } });
    fireEvent.change(screen.getByLabelText("Ngày trình"), { target: { value: "2026-10-01" } });
    fireEvent.change(screen.getByLabelText("Giờ trình"), { target: { value: "09:30" } });
    fireEvent.change(screen.getByLabelText("Lý do tạo trình"), { target: { value: " Trình thẩm định " } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình PCT" }));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("PCT", {
      reference: "PCT-01",
      submitted_on: "2026-10-01",
      submitted_time: "09:30",
      pct_submission_id: null,
      reason: "Trình thẩm định",
    }));
  });

  it("requires an explicit completed PCT parent for CT and uses the selected parent", async () => {
    const onCreate = vi.fn().mockResolvedValue({});
    render(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_actions: [available("create_approval_ct")],
      approval_submissions: [
        { approval_submission_id: "pct-1", case_id: "case-1", row_version: 2, stage: "PCT", round_no: 1, reference: null, submitted_on: null, submitted_time: null, completed_on: "2026-10-01", completed_time: null, pct_submission_id: null },
        { approval_submission_id: "pct-2", case_id: "case-1", row_version: 3, stage: "PCT", round_no: 2, reference: null, submitted_on: null, submitted_time: null, completed_on: "2026-10-02", completed_time: null, pct_submission_id: null },
      ],
    })} onCreate={onCreate} onComplete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Tạo trình CT" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("PCT hoàn tất cho CT"), { target: { value: "pct-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Tạo trình CT" }));
    await waitFor(() => expect(onCreate).toHaveBeenCalledWith("CT", expect.objectContaining({ pct_submission_id: "pct-2" })));
  });

  it("uses backend expected version when completing a submission", async () => {
    const onComplete = vi.fn().mockResolvedValue({});
    render(<CaseApprovalWorkspace caseWorkspace={workspace({
      approval_actions: [available("complete_approval:pct-1", 12)],
      approval_submissions: [{ approval_submission_id: "pct-1", case_id: "case-1", row_version: 1, stage: "PCT", round_no: 1, reference: null, submitted_on: null, submitted_time: null, completed_on: null, completed_time: null, pct_submission_id: null }],
    })} onCreate={vi.fn()} onComplete={onComplete} />);
    fireEvent.change(screen.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-10-03" } });
    fireEvent.change(screen.getByLabelText("Giờ hoàn tất trình"), { target: { value: "14:05" } });
    fireEvent.change(screen.getByLabelText("Lý do hoàn tất trình"), { target: { value: "Đủ điều kiện" } });
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tất PCT" }));
    await waitFor(() => expect(onComplete).toHaveBeenCalledWith("pct-1", {
      expected_version: 12,
      completed_on: "2026-10-03",
      completed_time: "14:05",
      reason: "Đủ điều kiện",
    }));
  });

  it("renders submitted and completed dates and times without inventing a timestamp", () => {
    render(<CaseApprovalWorkspace caseWorkspace={workspace({ approval_submissions: [{ approval_submission_id: "ct-1", case_id: "case-1", row_version: 1, stage: "CT", round_no: 1, reference: null, submitted_on: "2026-10-01", submitted_time: "09:30", completed_on: "2026-10-03", completed_time: "14:05", pct_submission_id: "pct-1" }] })} onCreate={vi.fn()} onComplete={vi.fn()} />);
    expect(screen.getByText(/Ngày trình:.*01-10-2026/)).toBeInTheDocument();
    expect(screen.getByText("Giờ trình: 09:30")).toBeInTheDocument();
    expect(screen.getByText(/Ngày hoàn tất:.*03-10-2026/)).toBeInTheDocument();
    expect(screen.getByText("Giờ hoàn tất: 14:05")).toBeInTheDocument();
    expect(screen.getByText("PCT: pct-1")).toBeInTheDocument();
  });
});


it("keeps completion input and reviewed submission version across tab unmount and refresh", async () => {
  const onComplete = vi.fn().mockResolvedValue({});
  const item = { approval_submission_id: "pct-draft", case_id: "case-1", row_version: 4, stage: "PCT", round_no: 1, reference: null, submitted_on: null, submitted_time: null, completed_on: null, completed_time: null, pct_submission_id: null };
  const editor = (show: boolean, version = 4) => <CaseDraftSession identity="case-A">{show ? <CaseApprovalWorkspace caseWorkspace={workspace({ approval_actions: [available("complete_approval:pct-draft", version)], approval_submissions: [{ ...item, stage: "PCT", row_version: version }] })} onCreate={vi.fn()} onComplete={onComplete} /> : null}</CaseDraftSession>;
  const view = render(editor(true));
  fireEvent.change(screen.getByLabelText("Ngày hoàn tất trình"), { target: { value: "2026-11-01" } });
  view.rerender(editor(false));view.rerender(editor(true, 9));
  expect(screen.getByLabelText("Ngày hoàn tất trình")).toHaveValue("2026-11-01");
  fireEvent.click(screen.getByRole("button", { name: "Hoàn tất PCT" }));
  await waitFor(() => expect(onComplete).toHaveBeenCalledWith("pct-draft", expect.objectContaining({ expected_version: 4, completed_on: "2026-11-01" })));
  await waitFor(() => expect(screen.getByLabelText("Ngày hoàn tất trình")).toHaveValue(""));
});
