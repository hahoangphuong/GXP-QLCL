import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CaseCertificateIssueWorkspace } from "./CaseCertificateIssueWorkspace";
import { CaseDraftSession, useCaseCommandRegistry } from "./CaseDraftSession";
import { CaseFieldMutationRecoveryError } from "./caseFieldMutationRecovery";
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

it("keeps certificate issuance locked when its workspace remounts while pending", async () => {
  let finish!: () => void;
  const issue = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  const view = (show: boolean) => <CaseDraftSession identity="case-A">{show ? <CaseCertificateIssueWorkspace caseId="case-A" readiness={readiness()} onIssue={issue} /> : null}</CaseDraftSession>;
  const { rerender } = render(view(true));
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
  rerender(view(false));
  rerender(view(true));
  expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled();
  expect(issue).toHaveBeenCalledOnce();
  await act(async () => finish());
});

it("keeps issuance locked when the entire Case workspace owner unmounts", async () => {
  let finish!: () => void;
  const issue = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  function Parent({ show }: { show: boolean }) {
    const registry = useCaseCommandRegistry();
    return show ? <CaseDraftSession identity="case-A" commandRegistry={registry}><CaseCertificateIssueWorkspace caseId="case-A" readiness={readiness()} onIssue={issue} /></CaseDraftSession> : null;
  }
  const view = (show: boolean) => <Parent show={show} />;
  const { rerender } = render(view(true));
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
  rerender(view(false));
  rerender(view(true));
  expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled();
  expect(issue).toHaveBeenCalledOnce();
  await act(async () => finish());
});

it("does not allow another issuance after an unknown result", async () => {
  const issue = vi.fn().mockRejectedValue(new CaseFieldMutationRecoveryError("Chưa xác minh kết quả"));
  render(<CaseDraftSession identity="case-A"><CaseCertificateIssueWorkspace caseId="case-A" readiness={readiness()} onIssue={issue} /></CaseDraftSession>);
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
  expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("Chưa xác minh kết quả");
  expect(screen.getByRole("button", { name: "Cấp giấy chứng nhận" })).toBeDisabled();
  expect(issue).toHaveBeenCalledOnce();
});

it("retains the pending issuance lock through Case A to B to A", async () => {
  let finish!: () => void;
  const issue = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  const view = (id: string) => <CaseDraftSession identity={id}><CaseCertificateIssueWorkspace caseId={id} readiness={readiness()} onIssue={issue} /></CaseDraftSession>;
  const { rerender } = render(view("case-A"));
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
  rerender(view("case-B"));
  rerender(view("case-A"));
  expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled();
  expect(issue).toHaveBeenCalledOnce();
  await act(async () => finish());
});

describe("CaseCertificateIssueWorkspace", () => {
  it("explains when a GMP Case already has an issued certificate without offering another issuance", () => {
    const issue = renderWorkspace(vi.fn(), { ...readiness(false), reason_code: "gmp_case_already_issued" });
    expect(screen.getByText(/Hồ sơ GMP đã có chứng nhận được cấp/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled();
    expect(issue).not.toHaveBeenCalled();
  });
  it.each([
    ["latest_capa_not_accepted", "Vòng khắc phục gần nhất chưa được chấp nhận"],
    ["case_state_not_eligible", "Trạng thái hồ sơ chưa cho phép cấp chứng nhận"],
    ["missing_permission", "Tài khoản không có quyền thực hiện thao tác này"],
  ])("explains backend issuance blocker %s without issuing", (code, message) => {
    const issue = renderWorkspace(vi.fn(), { ...readiness(false), reason_code: code });
    expect(screen.getByText(new RegExp(message))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cấp chứng nhận GxP" })).toBeDisabled();
    expect(issue).not.toHaveBeenCalled();
  });
  it("submits only once before pending renders", async () => {
    let finish!: () => void;
    const issue = renderWorkspace(vi.fn(() => new Promise<void>(resolve => { finish = resolve; })));
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    const button = screen.getByRole("button", { name: "Cấp giấy chứng nhận" });
    act(() => { button.click(); button.click(); });
    expect(issue).toHaveBeenCalledOnce();
    await act(async () => finish());
  });
  it("keeps an issue intent bound to its original type and discards it when the Case changes", () => {
    const issue = vi.fn();
    const { rerender } = render(<CaseCertificateIssueWorkspace caseId="case-1" readiness={readiness()} onIssue={issue} />);
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "original intent" } });
    rerender(<CaseCertificateIssueWorkspace caseId="case-1" readiness={{ ...readiness(), certificate_type: "GLP" }} onIssue={issue} />);
    expect(screen.getByLabelText("Loại GxP")).toHaveTextContent("GMP");
    expect(screen.getByRole("button", { name: "Cấp giấy chứng nhận" })).toBeDisabled();
    rerender(<CaseCertificateIssueWorkspace caseId="case-2" readiness={readiness()} onIssue={issue} />);
    rerender(<CaseCertificateIssueWorkspace caseId="case-1" readiness={readiness()} onIssue={issue} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(issue).not.toHaveBeenCalled();
  });
  it("retains the issue draft but blocks submission when readiness is withdrawn", () => {
    const issue = vi.fn();
    const { rerender } = render(<CaseCertificateIssueWorkspace caseId="case-1" readiness={readiness()} onIssue={issue} />);
    fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
    fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "retained" } });
    rerender(<CaseCertificateIssueWorkspace caseId="case-1" readiness={readiness(false)} onIssue={issue} />);
    expect(screen.getByLabelText("Số GCN")).toHaveValue("retained");
    expect(screen.getByRole("button", { name: "Cấp giấy chứng nhận" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
    expect(issue).not.toHaveBeenCalled();
  });
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

it("retains an unfinished certificate issuance draft and scoped intent across tab remount", async () => {
  const issue = vi.fn().mockResolvedValue(undefined);
  const view = (show: boolean) => <CaseDraftSession identity="case-A">
    {show ? <CaseCertificateIssueWorkspace caseId="case-A" readiness={readiness()} onIssue={issue} /> : null}
  </CaseDraftSession>;
  const { rerender } = render(view(true));
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "119/GCN-QLD" } });
  fireEvent.change(screen.getByLabelText("Ngày cấp"), { target: { value: "2026-11-07" } });
  fireEvent.change(screen.getByLabelText("Ngày hết hạn"), { target: { value: "2029-11-07" } });
  fireEvent.click(screen.getByRole("button", { name: "Thêm phạm vi" }));
  fireEvent.change(screen.getByLabelText("Nội dung phạm vi 1"), { target: { value: "Dây chuyền A" } });
  rerender(view(false));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  rerender(view(true));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByLabelText("Số GCN")).toHaveValue("119/GCN-QLD");
  expect(screen.getByLabelText("Ngày cấp")).toHaveValue("2026-11-07");
  expect(screen.getByLabelText("Ngày hết hạn")).toHaveValue("2029-11-07");
  expect(screen.getByLabelText("Nội dung phạm vi 1")).toHaveValue("Dây chuyền A");
  fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
  await waitFor(() => expect(issue).toHaveBeenCalledOnce());
  expect(issue).toHaveBeenCalledWith(expect.objectContaining({
    case_id: "case-A", certificate_number: "119/GCN-QLD",
    issue_date: "2026-11-07", expiry_date: "2029-11-07",
    scopes: [expect.objectContaining({ scope_text: "Dây chuyền A", sort_order: 0 })],
  }));
});

it("clears the deliberately cancelled issuance draft before a new attempt", () => {
  const view = <CaseDraftSession identity="case-A">
    <CaseCertificateIssueWorkspace caseId="case-A" readiness={readiness()} onIssue={vi.fn()} />
  </CaseDraftSession>;
  render(view);
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "unfinished" } });
  fireEvent.click(screen.getByRole("button", { name: "Thêm phạm vi" }));
  fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  expect(screen.getByLabelText("Số GCN")).toHaveValue("");
  expect(screen.queryByLabelText("Nội dung phạm vi 1")).not.toBeInTheDocument();
});

it("does not leak an issuance intent or draft between canonical Case sessions", () => {
  const issue = vi.fn();
  const view = (caseId: string) => <CaseDraftSession identity={caseId}>
    <CaseCertificateIssueWorkspace caseId={caseId} readiness={readiness()} onIssue={issue} />
  </CaseDraftSession>;
  const { rerender } = render(view("case-A"));
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "Case A" } });
  rerender(view("case-B"));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  expect(screen.getByLabelText("Số GCN")).toHaveValue("");
  rerender(view("case-A"));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(issue).not.toHaveBeenCalled();
});

it("preserves typed certificate fields but does not resend after an unknown write result and tab remount", async () => {
  const issue = vi.fn().mockRejectedValue(new CaseFieldMutationRecoveryError("Không thể xác minh kết quả cấp"));
  const view = (show: boolean) => <CaseDraftSession identity="case-A">
    {show ? <CaseCertificateIssueWorkspace caseId="case-A" readiness={readiness()} onIssue={issue} /> : null}
  </CaseDraftSession>;
  const { rerender } = render(view(true));
  fireEvent.click(screen.getByRole("button", { name: "Cấp chứng nhận GxP" }));
  fireEvent.change(screen.getByLabelText("Số GCN"), { target: { value: "unknown-result" } });
  fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
  expect(await screen.findByText("Không thể xác minh kết quả cấp")).toBeInTheDocument();
  rerender(view(false));
  rerender(view(true));
  expect(screen.getByLabelText("Số GCN")).toHaveValue("unknown-result");
  expect(screen.getByRole("button", { name: "Cấp giấy chứng nhận" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Cấp giấy chứng nhận" }));
  expect(issue).toHaveBeenCalledOnce();
});
