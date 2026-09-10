import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CaseCertificateIssueWorkspace } from "./CaseCertificateIssueWorkspace";
import type { CertificateIssueActionReadiness } from "../../types";

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
    fireEvent.click(within(dialog).getByRole("button", { name: "Cấp giấy chứng nhận" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(`${status} failure`);
    expect(onIssue).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog", { name: "Cấp giấy chứng nhận GxP" })).toBeInTheDocument();
  });

  it("cancels without a mutation", () => {
    const onIssue = renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    fireEvent.click(within(screen.getByRole("dialog", { name: "Cấp giấy chứng nhận GxP" })).getByRole("button", { name: "Hủy" }));
    expect(onIssue).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "Cấp giấy chứng nhận GxP" })).not.toBeInTheDocument();
  });
});
