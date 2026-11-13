import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CaseDraftSession } from "./CaseDraftSession";
import { CaseNonissuanceDecisionWorkspace } from "./CaseNonissuanceDecisionWorkspace";

const workspace = (overrides: Record<string, unknown> = {}) => ({
  case_summary: { id: "case-a", row_version: 7, state: "awaiting_certificate_decision" },
  nonissuance_decision: null,
  ...overrides,
}) as never;

function view(value = workspace(), onRecord = vi.fn()) {
  return render(<CaseDraftSession identity="case-a"><CaseNonissuanceDecisionWorkspace caseWorkspace={value} onRecord={onRecord} /></CaseDraftSession>);
}

describe("CaseNonissuanceDecisionWorkspace", () => {
  beforeEach(() => { vi.stubGlobal("confirm", vi.fn(() => true)); });
  it("submits one canonical expected Case version and renders the confirmed record", async () => {
    const onRecord = vi.fn().mockResolvedValue({ case_id: "case-a", decision: { decision_id: "decision-a", case_id: "case-a", decided_on: "2026-11-13", decision_reference: "KCGCN-01", explanation: "Không đáp ứng", recorded_by_user_id: "user-a" } });
    view(workspace(), onRecord);
    fireEvent.change(screen.getByLabelText("Ngày quyết định không cấp"), { target: { value: "2026-11-13" } });
    fireEvent.change(screen.getByLabelText("Số tham chiếu quyết định không cấp"), { target: { value: "KCGCN-01" } });
    fireEvent.change(screen.getByLabelText("Nội dung lý do không cấp"), { target: { value: "Không đáp ứng" } });
    fireEvent.click(screen.getByRole("button", { name: "Ghi nhận quyết định không cấp" }));
    await waitFor(() => expect(onRecord).toHaveBeenCalledWith({ expected_case_version: 7, decided_on: "2026-11-13", decision_reference: "KCGCN-01", explanation: "Không đáp ứng", reason: null }));
    expect(screen.getByText("Bản ghi quyết định; không phải văn bản đã ban hành và không thay đổi trạng thái hồ sơ.")).toBeInTheDocument();
  });

  it("does not offer a second append-only write after canonical record exists", () => {
    view(workspace({ nonissuance_decision: { decision_id: "decision-a", case_id: "case-a", decided_on: "2026-11-13", decision_reference: "KCGCN-01", explanation: "Không đáp ứng", recorded_by_user_id: "user-a" } }));
    expect(screen.queryByRole("button", { name: "Ghi nhận quyết định không cấp" })).not.toBeInTheDocument();
    expect(screen.getByText("KCGCN-01")).toBeInTheDocument();
  });
});
