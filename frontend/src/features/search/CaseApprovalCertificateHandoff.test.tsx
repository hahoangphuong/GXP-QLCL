import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseWorkspace } from "../../types";
import { CaseApprovalCertificateHandoff } from "./EventWorkspace";

function workspace(options: { issueAvailable?: boolean; issueType?: string; completed?: string | null; ctCase?: string; hasCt?: boolean } = {}): CaseWorkspace {
  const { issueAvailable = true, issueType = "GMP", completed = "2026-11-10", ctCase = "case-A", hasCt = true } = options;
  return {
    case_summary: { id: "case-A", gxp_type: "GMP" },
    inspection: { approval_submissions: hasCt ? [{
      approval_submission_id: "ct-canonical", stage: "CT", case_id: ctCase, round_no: 3,
      completed_on: completed, pct_submission_id: "pct-canonical",
    }] : [] },
    certificate_issue_readiness: {
      action_key: "issue_certificate", available: issueAvailable, certificate_type: issueType,
      issuance_basis: "inspection_case",
    },
  } as CaseWorkspace;
}

describe("Case CT to Certificate operator handoff", () => {
  it("offers a read-only direct path only when completed CT and canonical issue readiness agree", () => {
    const navigate = vi.fn();
    render(<CaseApprovalCertificateHandoff workspace={workspace()} activeTab="Kiểm tra" onNavigate={navigate} />);
    expect(screen.getByText(/1 trình CT đã hoàn tất/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Đến cấp giấy chứng nhận GxP" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith("Chứng nhận GxP");
  });

  it.each([
    [{ issueAvailable: false }, "backend declines issuance"],
    [{ issueType: "GLP" }, "backend issue type does not match Case"],
    [{ completed: null }, "CT is unfinished"],
    [{ ctCase: "case-other" }, "CT belongs to another Case"],
    [{ hasCt: false }, "no CT exists"],
  ] as const)("does not suggest issuance when %s (%s)", (options, _reason) => {
    const navigate = vi.fn();
    render(<CaseApprovalCertificateHandoff workspace={workspace(options)} activeTab="Kiểm tra" onNavigate={navigate} />);
    expect(screen.queryByRole("button", { name: "Đến cấp giấy chứng nhận GxP" })).not.toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("returns to the exact Case's CT/PCT history even after issue readiness is withdrawn", () => {
    const navigate = vi.fn();
    render(<CaseApprovalCertificateHandoff workspace={workspace({ issueAvailable: false })} activeTab="Chứng nhận GxP" onNavigate={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "Xem lại lịch sử trình PCT / CT" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith("Kiểm tra");
  });

  it("does not surface cross-Case or absent CT lineage on certificate tab", () => {
    const navigate = vi.fn();
    const view = render(<CaseApprovalCertificateHandoff workspace={workspace({ ctCase: "case-other" })} activeTab="Chứng nhận GxP" onNavigate={navigate} />);
    expect(screen.queryByRole("button", { name: "Xem lại lịch sử trình PCT / CT" })).not.toBeInTheDocument();
    view.rerender(<CaseApprovalCertificateHandoff workspace={workspace({ hasCt: false })} activeTab="Chứng nhận GxP" onNavigate={navigate} />);
    expect(screen.queryByRole("button", { name: "Xem lại lịch sử trình PCT / CT" })).not.toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });
});
