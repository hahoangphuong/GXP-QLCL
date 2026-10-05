import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChangeRequestWorkspace } from "../../types";
import { ChangeRequestMutationWorkspace, type ChangeRequestMutationHandlers } from "./ChangeRequestMutationWorkspace";

function buildWorkspace(overrides: Partial<ChangeRequestWorkspace> = {}): ChangeRequestWorkspace {
  return {
    id: "change-1",
    row_version: 7,
    legacy_change_request_id: null,
    site_id: "site-1",
    facility_name: "Nhà máy A",
    company_name: "Công ty A",
    scope_label: "Đổi kho",
    description: "Mô tả cũ",
    submitted_on: "2026-10-01",
    requester_name: "QA",
    state: "under_review",
    handled_on: null,
    handled_by_name: null,
    result_label: null,
    effective_on: null,
    approval_reference: null,
    documents: { items: [] },
    details: [
      {
        change_detail_id: "detail-1",
        legacy_change_detail_id: null,
        classification_id: 1,
        classification_label: "Địa chỉ",
        approval_status: null,
        old_value: "A",
        new_value: "B",
        note: null,
      },
    ],
    action_readiness: [
      { action_key: "edit_change_request", label: "Sửa đề nghị", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 7, target_state: null },
      { action_key: "add_change_detail", label: "Thêm chi tiết", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 7, target_state: null },
      { action_key: "edit_change_detail", label: "Sửa chi tiết", available: true, reason_code: null, required_permissions: ["change_request.edit"], expected_version: 7, target_state: null },
      { action_key: "edit_change_approval", label: "Cập nhật xử lý", available: true, reason_code: null, required_permissions: ["change_request.approve"], expected_version: 7, target_state: null },
      { action_key: "transition_change_request:not-derived", label: "Chấp nhận", available: true, reason_code: null, required_permissions: ["change_request.approve"], expected_version: 7, target_state: "accepted" },
    ],
    ...overrides,
  };
}

function buildHandlers(): ChangeRequestMutationHandlers {
  return {
    onUpdateHeader: vi.fn().mockResolvedValue(undefined),
    onCreateDetail: vi.fn().mockResolvedValue(undefined),
    onUpdateDetail: vi.fn().mockResolvedValue(undefined),
    onUpsertApproval: vi.fn().mockResolvedValue(undefined),
    onTransition: vi.fn().mockResolvedValue(undefined),
  };
}

describe("ChangeRequestMutationWorkspace backend-owned writes", () => {
  it("uses readiness expected_version and sends only changed header fields, with explicit null for a cleared value", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Sửa đề nghị" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Phạm vi thay đổi" }), { target: { value: "Đổi kho mới" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Mô tả thay đổi" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu đề nghị" }));

    await waitFor(() => expect(handlers.onUpdateHeader).toHaveBeenCalledTimes(1));
    expect(handlers.onUpdateHeader).toHaveBeenCalledWith({
      expected_version: 7,
      scope_label: "Đổi kho mới",
      description: null,
    });
  });

  it("keeps edit controls disabled when backend readiness blocks the action", () => {
    const handlers = buildHandlers();
    const workspace = buildWorkspace({
      action_readiness: buildWorkspace().action_readiness.map((item) =>
        item.action_key === "edit_change_request"
          ? { ...item, available: false, reason_code: "missing_permission" }
          : item,
      ),
    });

    render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={workspace} />);

    expect(screen.getByRole("button", { name: "Sửa đề nghị" })).toBeDisabled();
    expect(screen.getByText("Không thể sửa: missing_permission.")).toBeInTheDocument();
  });

  it("creates and updates details with the aggregate readiness token instead of a child-local version", async () => {
    const handlers = buildHandlers();
    const { rerender } = render(<ChangeRequestMutationWorkspace activeTab="Chi tiết" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Thêm chi tiết" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Phân loại thay đổi" }), { target: { value: "Thiết bị" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Thông tin mới" }), { target: { value: "Máy mới" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu chi tiết mới" }));

    await waitFor(() => expect(handlers.onCreateDetail).toHaveBeenCalledTimes(1));
    expect(handlers.onCreateDetail).toHaveBeenCalledWith(expect.objectContaining({
      expected_version: 7,
      classification_label: "Thiết bị",
      new_value: "Máy mới",
    }));

    rerender(<ChangeRequestMutationWorkspace activeTab="Chi tiết" handlers={handlers} workspace={buildWorkspace({ row_version: 8, action_readiness: buildWorkspace().action_readiness.map((item) => ({ ...item, expected_version: 8 })) })} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Thông tin mới" }), { target: { value: "C" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu chi tiết" }));

    await waitFor(() => expect(handlers.onUpdateDetail).toHaveBeenCalledTimes(1));
    expect(handlers.onUpdateDetail).toHaveBeenCalledWith("detail-1", {
      expected_version: 8,
      new_value: "C",
    });
  });

  it("rejects an invalid classification id instead of silently clearing it", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Chi tiết" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Thêm chi tiết" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Mã phân loại thay đổi" }), { target: { value: "not-a-number" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Phân loại thay đổi" }), { target: { value: "Thiết bị" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu chi tiết mới" }));

    expect(handlers.onCreateDetail).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Mã phân loại phải là số nguyên hợp lệ.");
  });

  it("uses backend target_state directly for transitions and never derives state from action_key", async () => {
    const handlers = buildHandlers();
    render(<ChangeRequestMutationWorkspace activeTab="Xử lý" handlers={handlers} workspace={buildWorkspace()} />);

    fireEvent.click(screen.getByRole("button", { name: "Chấp nhận" }));

    await waitFor(() => expect(handlers.onTransition).toHaveBeenCalledTimes(1));
    expect(handlers.onTransition).toHaveBeenCalledWith({
      expected_version: 7,
      target_state: "accepted",
    });
  });

  it("resets an open editor when authoritative row_version changes", () => {
    const handlers = buildHandlers();
    const { rerender } = render(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace()} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa đề nghị" }));
    expect(screen.getByRole("textbox", { name: "Phạm vi thay đổi" })).toBeInTheDocument();

    rerender(<ChangeRequestMutationWorkspace activeTab="Đề nghị" handlers={handlers} workspace={buildWorkspace({ row_version: 8, scope_label: "Authoritative" })} />);

    expect(screen.queryByRole("textbox", { name: "Phạm vi thay đổi" })).not.toBeInTheDocument();
    expect(screen.getByText("Authoritative")).toBeInTheDocument();
  });
});
