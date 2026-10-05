import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseApprovalWorkspace } from "./CaseApprovalWorkspace";

function workspace(overrides: Partial<CaseWorkspace["inspection"]> = {}): CaseWorkspace {
  return {
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

describe("CaseApprovalWorkspace", () => {
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
