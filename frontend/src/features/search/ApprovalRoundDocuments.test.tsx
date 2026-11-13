import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CaseDraftSession } from "./CaseDraftSession";
import { ApprovalRoundDocuments } from "./ApprovalRoundDocuments";
import type {
  ApprovalDocumentBindReadiness, ApprovalDocumentReadback, CaseWorkspace,
  InspectionApprovalSubmission,
} from "../../types";

const submission: InspectionApprovalSubmission = {
  approval_submission_id: "pct-2", case_id: "case-a", stage: "PCT",
  round_no: 2, row_version: 3, reference: "PCT2",
  submitted_on: null, submitted_time: null, completed_on: null,
  completed_time: null, pct_submission_id: null,
};
const readiness: ApprovalDocumentBindReadiness = {
  action_key: "bind_approval_document", approval_submission_id: "pct-2",
  stage: "PCT", round_no: 2, expected_version: 3, available: true,
  reason_code: null, required_permissions: ["inspection.edit", "document.read"],
  eligible_document_ids: ["pct-doc-b"],
};
function fixture(caseId = "case-a", override: Record<string, unknown> = {}): CaseWorkspace {
  return {
    case_summary: { id: caseId },
    inspection: {
      approval_document_candidates: [
        { document_id: "pct-doc-a", stage: "PCT", family_code: "INSPECTION_PT_PCT", title: "PCT1", open_available: true, bound_submission_id: "pct-1" },
        { document_id: "pct-doc-b", stage: "PCT", family_code: "INSPECTION_PT_PCT", title: "PCT2", open_available: false, bound_submission_id: null },
        { document_id: "ct-doc", stage: "CT", family_code: "INSPECTION_PT_CT", title: "CT1", open_available: true, bound_submission_id: null },
      ],
      approval_document_links: [],
      approval_document_bind_readiness: [readiness],
      ...override,
    },
  } as unknown as CaseWorkspace;
}
function receipt(caseId = "case-a", documentId = "pct-doc-b"): ApprovalDocumentReadback {
  return {
    case_id: caseId, approval_submission_id: "pct-2",
    stage: "PCT", round_no: 2, row_version: 4,
    links: [{ approval_submission_id: "pct-2", document_id: documentId,
      binding_id: "link-b", stage: "PCT", round_no: 2 }],
  };
}
function view(workspace = fixture(), onBind = vi.fn(), onReadback = vi.fn(), onConfirmed = vi.fn()) {
  return render(<CaseDraftSession identity={workspace.case_summary.id}>
    <ApprovalRoundDocuments workspace={workspace} submission={submission}
      onBind={onBind} onReadback={onReadback} onConfirmed={onConfirmed} />
  </CaseDraftSession>);
}

describe("ApprovalRoundDocuments", () => {
  it("selects only backend-eligible UUID for PCT2, not bound PCT1 nor CT family", () => {
    const onBind = vi.fn();
    view(fixture(), onBind);
    const selector = screen.getByRole("combobox", { name: "Chọn tài liệu cho PCT lần 2" });
    expect(screen.queryByRole("option", { name: /PCT1/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /CT1/ })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /PCT2/ })).toHaveValue("pct-doc-b");
    expect(screen.getByText(/chưa có bản mở được/)).toBeInTheDocument();
    expect(screen.getByText(/Liên kết không xác nhận tài liệu đã ký hoặc ban hành/)).toBeInTheDocument();
    expect(onBind).not.toHaveBeenCalled();
  });

  it("shows real bound UUID without inferring issuance or remapping other rounds", () => {
    const state = fixture("case-a", { approval_document_links: [
      { approval_submission_id: "pct-2", document_id: "pct-doc-b", binding_id: "link-b", stage: "PCT", round_no: 2 },
      { approval_submission_id: "pct-1", document_id: "pct-doc-a", binding_id: "link-a", stage: "PCT", round_no: 1 },
    ] });
    view(state);
    expect(screen.getByLabelText("Tài liệu đã liên kết PCT lần 2")).toHaveTextContent("pct-doc-b");
    expect(screen.getByLabelText("Tài liệu đã liên kết PCT lần 2")).not.toHaveTextContent("pct-doc-a");
    expect(screen.queryByText(/đã ban hành thành công/i)).not.toBeInTheDocument();
  });

  it("never submits when canonical readiness denies or version is stale", () => {
    const onBind = vi.fn();
    const r1 = view(fixture("case-a", { approval_document_bind_readiness: [
      { ...readiness, available: false, reason_code: "missing_permission", eligible_document_ids: [] },
    ] }), onBind);
    expect(screen.getByText(/Thiếu quyền chỉnh sửa/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" })).toBeDisabled();
    r1.unmount();
    view(fixture("case-a", { approval_document_bind_readiness: [{ ...readiness, expected_version: 2 }] }), onBind);
    expect(screen.getByText(/Phiên bản lần trình không còn khớp/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" })).toBeDisabled();
    expect(onBind).not.toHaveBeenCalled();
  });

  it("binds exactly once, verifies committed canonical GET then refreshes Case", async () => {
    const deferred: { finish?: (result: { approval_submission_id: string; document_id: string; binding_id: string; created: boolean; row_version: number }) => void } = {};
    const onBind = vi.fn().mockImplementation(() => new Promise(resolve => { deferred.finish = resolve; }));
    const onReadback = vi.fn().mockResolvedValue(receipt());
    const onConfirmed = vi.fn().mockResolvedValue(undefined);
    view(fixture(), onBind, onReadback, onConfirmed);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "pct-doc-b" } });
    const button = screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" });
    fireEvent.click(button); fireEvent.click(button);
    expect(onBind).toHaveBeenCalledTimes(1);
    expect(onBind).toHaveBeenCalledWith("pct-2", { document_id: "pct-doc-b", expected_version: 3 });
    deferred.finish?.({ approval_submission_id: "pct-2", document_id: "pct-doc-b", binding_id: "link-b", created: true, row_version: 4 });
    await waitFor(() => expect(screen.getByText(/Đã xác minh liên kết canonical/)).toBeInTheDocument());
    expect(onReadback).toHaveBeenCalledWith("pct-2");
    expect(onConfirmed).toHaveBeenCalledWith("case-a");
  });

  it("resolves lost POST response via targeted GET with no blind replay", async () => {
    const onBind = vi.fn().mockRejectedValue(new Error("Network interrupted after commit"));
    const onReadback = vi.fn().mockResolvedValue(receipt());
    view(fixture(), onBind, onReadback);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "pct-doc-b" } });
    fireEvent.click(screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" }));
    await waitFor(() => expect(screen.getByText(/Đã xác minh liên kết canonical/)).toBeInTheDocument());
    expect(onBind).toHaveBeenCalledTimes(1);
    expect(onReadback).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Đối chiếu liên kết canonical" })).not.toBeInTheDocument();
  });

  it("retains unknown-outcome lock until the *correct* canonical binding exists", async () => {
    const onBind = vi.fn().mockRejectedValue(new Error("Lost POST result"));
    const onReadback = vi.fn().mockResolvedValueOnce(receipt("case-other"))
      .mockResolvedValueOnce(receipt("case-a", "pct-doc-a"))
      .mockResolvedValueOnce(receipt());
    view(fixture(), onBind, onReadback);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "pct-doc-b" } });
    fireEvent.click(screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Đối chiếu liên kết canonical" })).toBeEnabled());
    expect(screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" })).toBeDisabled();
    expect(screen.getByRole("combobox")).toHaveValue("pct-doc-b");
    fireEvent.click(screen.getByRole("button", { name: "Đối chiếu liên kết canonical" }));
    await waitFor(() => expect(onReadback).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Đối chiếu liên kết canonical" }));
    await waitFor(() => expect(screen.getByText(/Đã xác minh liên kết canonical/)).toBeInTheDocument());
    expect(onBind).toHaveBeenCalledTimes(1);
  });

  it("does not elevate an uncertain response into verified status on forbidden 409", async () => {
    const onBind = vi.fn().mockRejectedValue(Object.assign(new Error("Stale version"), { status: 409 }));
    const onReadback = vi.fn();
    view(fixture(), onBind, onReadback);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "pct-doc-b" } });
    fireEvent.click(screen.getByRole("button", { name: "Liên kết tài liệu với PCT lần 2" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Stale version"));
    expect(onReadback).not.toHaveBeenCalled();
    expect(screen.queryByText(/Đã xác minh liên kết canonical/)).not.toBeInTheDocument();
  });
});
