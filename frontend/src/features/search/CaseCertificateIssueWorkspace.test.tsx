import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CaseCertificateIssueWorkspace } from "./CaseCertificateIssueWorkspace";
import type { CertificateIssueActionReadiness, CertificateIssueRequest } from "../../types";

function readiness(available = true): CertificateIssueActionReadiness {
  return {
    action_key: "issue_certificate",
    label: "Cấp chứng nhận GxP",
    available,
    reason_code: available ? null : "case_not_eligible",
    required_permissions: ["certificate.issue"],
    certificate_type: "GMP",
    issuance_basis: "inspection_case",
  };
}

function renderWorkspace(onIssue = vi.fn().mockResolvedValue(undefined), action = readiness()) {
  render(<CaseCertificateIssueWorkspace caseId="case-1" onIssue={onIssue} readiness={action} />);
  return onIssue;
}

describe("CaseCertificateIssueWorkspace", () => {
  it("keeps keyboard focus within issuance while every control is pending", async () => {
    let reject!: (error: Error) => void;
    const issue = renderWorkspace(vi.fn(() => new Promise<void>((_, fail) => { reject = fail; })));
    const trigger = screen.getByRole("button", { name: "Cấp chứng nhận GxP" });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Số GCN")).toHaveFocus();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cấp giấy chứng nhận" }));
    expect(dialog).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(dialog).toHaveFocus();
    expect(issue).toHaveBeenCalledOnce();
    await act(async () => reject(new Error("network failure")));
    await within(dialog).findByRole("alert");
    expect(within(dialog).getByLabelText("Số GCN")).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(trigger).toHaveFocus();
  });
  it("renders no issue control without the backend action and disables unavailable actions", () => {
    render(<CaseCertificateIssueWorkspace caseId="case-1" onIssue={vi.fn()} readiness={null} />);
    expect(screen.queryByRole("button", { name: "Cấp chứng nhận GxP" })).not.toBeInTheDocument();

    renderWorkspace(vi.fn(), readiness(false));
    expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled();
    expect(screen.getByText("case_not_eligible")).toBeInTheDocument();
  });

  it("uses the backend type read-only, starts with no scopes, and submits only case-backed data", async () => {
    const onIssue = renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    const dialog = screen.getByRole("dialog", { name: "Cấp giấy chứng nhận GxP" });

    expect(within(dialog).getByLabelText("Loại GxP")).toHaveTextContent("GMP");
    expect(within(dialog).queryByRole("combobox", { name: "Loại GxP" })).not.toBeInTheDocument();
    expect(within(dialog).queryByText(/issuance_basis/i)).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox", { name: "Nội dung phạm vi 1" })).not.toBeInTheDocument();

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Số GCN" }), { target: { value: "GCN-1" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Thêm phạm vi" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Nội dung phạm vi 1" }), { target: { value: "Phạm vi A" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Thêm phạm vi" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Nội dung phạm vi 2" }), { target: { value: "Phạm vi B" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Đưa phạm vi 2 lên" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Xóa phạm vi 2" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Cấp giấy chứng nhận" }));

    await waitFor(() => expect(onIssue).toHaveBeenCalledWith({
      case_id: "case-1",
      certificate_type: "GMP",
      issuance_basis: "inspection_case",
      certificate_number: "GCN-1",
      issue_date: null,
      expiry_date: null,
      scopes: [{ scope_key: null, scope_text: "Phạm vi B", language_code: "vi", sort_order: 0 }],
      reason: null,
    }));
  });

  it.each([403, 409, 422])("keeps the issue form open and shows backend errors (%s)", async (status) => {
    const onIssue = renderWorkspace(vi.fn().mockRejectedValue(Object.assign(new Error(`${status} failure`), { status })));
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    const dialog = screen.getByRole("dialog", { name: "Cấp giấy chứng nhận GxP" });
    fireEvent.change(within(dialog).getByLabelText("Số GCN"), { target: { value: "Retained certificate draft" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Thêm phạm vi" }));
    fireEvent.change(within(dialog).getByLabelText("Nội dung phạm vi 1"), { target: { value: "Explicit certificate scope" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cấp giấy chứng nhận" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(`${status} failure`);
    expect(onIssue).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog", { name: "Cấp giấy chứng nhận GxP" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Số GCN")).toHaveValue("Retained certificate draft");
    expect(within(dialog).getByLabelText("Nội dung phạm vi 1")).toHaveValue("Explicit certificate scope");
  });

  it("retains a draft on network failure without retry", async () => {
    const issue = renderWorkspace(vi.fn().mockRejectedValue(new TypeError("Network unavailable")));
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "Draft network" } });
    fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Số GCN")).toHaveValue("Draft network");
    expect(issue).toHaveBeenCalledOnce();
  });

  it("does not recreate a dialog when a pending issue completes after context unmount", async () => {
    let resolve!: () => void;
    const issue = vi.fn<(payload: CertificateIssueRequest) => Promise<void>>(() => new Promise<void>(done => { resolve = done; }));
    const first = render(<CaseCertificateIssueWorkspace caseId="case-A" readiness={readiness()} onIssue={issue} />);
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
    fireEvent.click(screen.getByRole("button", { name: "Đang cấp..." }));
    expect(issue).toHaveBeenCalledOnce();
    expect(issue.mock.calls[0][0]).toEqual(expect.objectContaining({ case_id: "case-A", scopes: [] }));
    first.unmount();
    render(<CaseCertificateIssueWorkspace caseId="case-B" readiness={readiness(false)} onIssue={vi.fn()} />);
    await act(async () => resolve());
    await waitFor(() => expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("cancels without a mutation", () => {
    const onIssue = renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Cấp giấy chứng nhận GxP" })).getByRole("button", { name: "Hủy" }));
    expect(onIssue).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "Cấp giấy chứng nhận GxP" })).not.toBeInTheDocument();
  });
});
